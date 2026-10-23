"""Windows communications-mode capture with observable system AEC.

This module keeps all PyWinRT imports lazy so dependency-light tests and
non-Windows processes can still import the voice package.  The selected capture
and render endpoints are explicit.  If Windows does not report an active AEC
effect, or if automatic reference selection would point at a different default
render endpoint, initialization fails closed.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable


FrameCallback = Callable[[bytes], None]


def normalize_audio_graph_pcm(
    pcm: bytes,
    *,
    samples_per_quantum: int,
    channels: int,
) -> bytes:
    """Convert AudioGraph's native float32 frame-node output to PCM16."""
    expected_samples = samples_per_quantum * channels
    if len(pcm) != expected_samples * 4:
        return pcm

    import numpy as np

    floats = np.frombuffer(pcm, dtype=np.float32)
    return (np.clip(floats, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


@dataclass(frozen=True)
class WindowsAudioEndpoints:
    capture_id: str
    render_id: str


@dataclass(frozen=True)
class WindowsAecEvidence:
    capture_id: str
    render_id: str
    effect_types: tuple[str, ...]
    aec_enabled: bool
    aec_state_settable: bool
    reference_mode: str


@dataclass(frozen=True)
class WindowsAudioEndpointInfo:
    endpoint_id: str
    flow: str
    friendly_name: str
    active: bool


EndpointDescriber = Callable[[str], "WindowsAudioEndpointInfo | None"]
ActiveNameCounter = Callable[[str, str], int]

_MMDEVICE_ROOT = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio"
_FLOW_KEYS = {"capture": "Capture", "render": "Render"}
_FLOW_PREFIXES = {"{0.0.1.00000000}": "capture", "{0.0.0.00000000}": "render"}
_PKEY_DEVICE_DESCRIPTION = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
_PKEY_INTERFACE_FRIENDLY_NAME = "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"
_DEVICE_STATE_ACTIVE = 0x1


def parse_mmdevice_endpoint_id(endpoint_id: str) -> tuple[str, str] | None:
    """Split a WinRT endpoint ID into (flow, endpoint GUID), or None."""
    parts = str(endpoint_id or "").split("#")
    if len(parts) < 3:
        return None
    prefix, brace_dot, guid = parts[2].partition("}.")
    flow = _FLOW_PREFIXES.get(prefix + "}")
    if flow is None or not brace_dot or not guid.startswith("{"):
        return None
    return flow, guid


def describe_windows_audio_endpoint(endpoint_id: str) -> WindowsAudioEndpointInfo | None:
    """Read an endpoint's flow, friendly name and state from MMDevices.

    The friendly name follows Windows' own "Description (Interface)" form, e.g.
    "Echo Cancelling Speakerphone (reSpeaker XVF3800 4-Mic Array)". Returns None
    when the ID is malformed or Windows no longer knows the endpoint.
    """
    parsed = parse_mmdevice_endpoint_id(endpoint_id)
    if parsed is None:
        return None
    flow, guid = parsed
    try:
        import winreg
    except ImportError:  # pragma: no cover - platform guard
        return None
    key_path = rf"{_MMDEVICE_ROOT}\{_FLOW_KEYS[flow]}\{guid}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            state, _ = winreg.QueryValueEx(key, "DeviceState")
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, key_path + r"\Properties"
        ) as properties:
            description = _read_string(winreg, properties, _PKEY_DEVICE_DESCRIPTION)
            interface = _read_string(winreg, properties, _PKEY_INTERFACE_FRIENDLY_NAME)
    except OSError:
        return None
    name = f"{description} ({interface})" if interface else description
    return WindowsAudioEndpointInfo(
        endpoint_id=endpoint_id,
        flow=flow,
        friendly_name=name,
        active=int(state) == _DEVICE_STATE_ACTIVE,
    )


def count_active_windows_audio_endpoints_named(flow: str, friendly_name: str) -> int:
    """Count active endpoints of one flow whose friendly name matches."""
    try:
        import winreg
    except ImportError:  # pragma: no cover - platform guard
        return 0
    wanted = friendly_name.strip().casefold()
    prefix = next(p for p, f in _FLOW_PREFIXES.items() if f == flow)
    count = 0
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, rf"{_MMDEVICE_ROOT}\{_FLOW_KEYS[flow]}"
        ) as root:
            index = 0
            while True:
                try:
                    guid = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                info = describe_windows_audio_endpoint(
                    rf"\\?\SWD#MMDEVAPI#{prefix}.{guid}#"
                )
                if info and info.active and info.friendly_name.casefold() == wanted:
                    count += 1
    except OSError:
        return 0
    return count


def _read_string(winreg, key, name: str) -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value or "").strip()


class EndpointPinMismatch(RuntimeError):
    """The pinned endpoints are not the current defaults and cannot be followed."""

    def __init__(self, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.details = details


@dataclass(frozen=True)
class EndpointResolution:
    endpoints: WindowsAudioEndpoints
    capture: str
    render: str
    details: dict[str, object]

    @property
    def reenumerated(self) -> bool:
        return "reenumerated" in (self.capture, self.render)


def resolve_pinned_windows_audio_endpoints(
    pinned: WindowsAudioEndpoints,
    defaults: WindowsAudioEndpoints,
    *,
    capture_name: str = "",
    render_name: str = "",
    describe: EndpointDescriber = describe_windows_audio_endpoint,
    count_active_named: ActiveNameCounter = count_active_windows_audio_endpoints_named,
) -> EndpointResolution:
    """Accept the pinned pair, or follow a re-enumeration of the same devices.

    Windows can re-register an unchanged physical device under a new MMDevice
    ID. A side whose pin no longer matches the default is followed only when a
    pinned friendly name is configured for it, the old pinned endpoint is no
    longer active, the new default is active and carries exactly that name, and
    no other active endpoint of the same flow does. Anything else, including
    the owner choosing a different default device, still fails closed. The AEC
    effect itself is verified separately by ``query_windows_aec``.
    """
    details: dict[str, object] = {}
    failures: list[str] = []
    outcomes: dict[str, str] = {}
    resolved: dict[str, str] = {}
    for flow, pinned_id, default_id, expected in (
        ("capture", pinned.capture_id, defaults.capture_id, capture_name),
        ("render", pinned.render_id, defaults.render_id, render_name),
    ):
        details[f"{flow}_pinned_id"] = pinned_id
        details[f"{flow}_default_id"] = default_id
        if pinned_id == default_id:
            outcomes[flow] = "pinned"
            resolved[flow] = pinned_id
            continue
        reason = _reenumeration_refusal(
            flow, pinned_id, default_id, expected.strip(), describe,
            count_active_named, details,
        )
        details[f"{flow}_resolution"] = reason or "reenumerated"
        if reason:
            failures.append(f"{flow}: {reason}")
            continue
        outcomes[flow] = "reenumerated"
        resolved[flow] = default_id
    if failures:
        raise EndpointPinMismatch(
            "Pinned Windows audio endpoint identity does not match the current "
            "default capture/render pair (" + "; ".join(failures) + ").",
            details,
        )
    details.setdefault("capture_resolution", outcomes["capture"])
    details.setdefault("render_resolution", outcomes["render"])
    return EndpointResolution(
        endpoints=WindowsAudioEndpoints(
            capture_id=resolved["capture"], render_id=resolved["render"]
        ),
        capture=outcomes["capture"],
        render=outcomes["render"],
        details=details,
    )


def _reenumeration_refusal(
    flow: str,
    pinned_id: str,
    default_id: str,
    expected: str,
    describe: EndpointDescriber,
    count_active_named: ActiveNameCounter,
    details: dict[str, object],
) -> str | None:
    default_info = describe(default_id)
    details[f"{flow}_default_name"] = default_info.friendly_name if default_info else None
    if not expected:
        return "pin differs from default and no pinned endpoint name is configured"
    details[f"{flow}_pinned_name"] = expected
    pinned_info = describe(pinned_id)
    if pinned_info is not None and pinned_info.active:
        return "pinned endpoint is still active; the default device was changed"
    if default_info is None or not default_info.active or default_info.flow != flow:
        return "current default endpoint is not an active endpoint of this flow"
    if default_info.friendly_name.casefold() != expected.casefold():
        return "current default endpoint name differs from the pinned name"
    if count_active_named(flow, default_info.friendly_name) != 1:
        return "pinned name is not unique among active endpoints"
    return None


def get_default_windows_audio_endpoints() -> WindowsAudioEndpoints:
    """Return the full MMDevice IDs used by WinRT, not unstable PyAudio indexes."""
    try:
        from winrt.windows.media.devices import AudioDeviceRole, MediaDevice
    except ImportError as exc:  # pragma: no cover - platform/dependency guard
        raise RuntimeError(
            "Windows audio support requires the pinned PyWinRT voice dependencies."
        ) from exc

    return WindowsAudioEndpoints(
        capture_id=MediaDevice.get_default_audio_capture_id(AudioDeviceRole.DEFAULT),
        render_id=MediaDevice.get_default_audio_render_id(AudioDeviceRole.DEFAULT),
    )


def query_windows_aec(
    endpoints: WindowsAudioEndpoints,
) -> WindowsAecEvidence:
    """Query communications-mode effects and bind/verify the render reference."""
    try:
        from winrt.windows.media import AudioProcessing
        from winrt.windows.media.capture import MediaCategory
        from winrt.windows.media.effects import (
            AudioEffectState,
            AudioEffectType,
            AudioEffectsManager,
        )
    except ImportError as exc:  # pragma: no cover - platform/dependency guard
        raise RuntimeError(
            "Windows AEC discovery requires the pinned PyWinRT voice dependencies."
        ) from exc

    manager = AudioEffectsManager.create_audio_capture_effects_manager_with_mode(
        endpoints.capture_id,
        MediaCategory.COMMUNICATIONS,
        AudioProcessing.DEFAULT,
    )
    effects = tuple(manager.get_audio_capture_effects())
    effect_types = tuple(effect.audio_effect_type.name for effect in effects)
    aec = next(
        (
            effect
            for effect in effects
            if effect.audio_effect_type == AudioEffectType.ACOUSTIC_ECHO_CANCELLATION
        ),
        None,
    )
    if aec is None:
        return WindowsAecEvidence(
            capture_id=endpoints.capture_id,
            render_id=endpoints.render_id,
            effect_types=effect_types,
            aec_enabled=False,
            aec_state_settable=False,
            reference_mode="unavailable",
        )

    if aec.state != AudioEffectState.ON and aec.can_set_state:
        aec.set_state(AudioEffectState.ON)
    enabled = aec.state == AudioEffectState.ON
    configuration = aec.acoustic_echo_cancellation_configuration
    if configuration is not None:
        configuration.set_echo_cancellation_render_endpoint(endpoints.render_id)
        reference_mode = "explicit"
    else:
        defaults = get_default_windows_audio_endpoints()
        if defaults.render_id != endpoints.render_id:
            raise RuntimeError(
                "Windows AEC does not expose reference control and the pinned "
                "render endpoint is not the current default."
            )
        reference_mode = "system_default_verified"

    return WindowsAecEvidence(
        capture_id=endpoints.capture_id,
        render_id=endpoints.render_id,
        effect_types=effect_types,
        aec_enabled=enabled,
        aec_state_settable=bool(aec.can_set_state),
        reference_mode=reference_mode,
    )


class WindowsAecCapture:
    """Long-lived AudioGraph capture source producing echo-cleaned PCM.

    The AudioGraph callback only copies one fixed quantum and invokes the
    supplied callback. Callers must keep that callback bounded and non-blocking.
    """

    def __init__(
        self,
        endpoints: WindowsAudioEndpoints,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        bits_per_sample: int = 16,
        desired_frame_ms: int = 10,
        startup_timeout: float = 10.0,
        endpoint_poll_seconds: float = 1.0,
    ) -> None:
        if sample_rate <= 0 or channels <= 0 or bits_per_sample <= 0:
            raise ValueError("Windows capture format values must be positive.")
        if desired_frame_ms <= 0:
            raise ValueError("desired_frame_ms must be positive.")
        self.endpoints = endpoints
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.bits_per_sample = int(bits_per_sample)
        self.desired_frame_ms = int(desired_frame_ms)
        self.startup_timeout = float(startup_timeout)
        self.endpoint_poll_seconds = max(0.1, float(endpoint_poll_seconds))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_frame: FrameCallback | None = None
        self._error: str | None = None
        self._frames = 0
        self._pcm_bytes = 0
        self._callback_errors = 0
        self._samples_per_quantum: int | None = None
        self._native_frame_bytes: int | None = None
        self._evidence: WindowsAecEvidence | None = None

    def start(self, on_frame: FrameCallback) -> None:
        if not callable(on_frame):
            raise TypeError("on_frame must be callable")
        with self._lock:
            if self._thread is not None:
                raise RuntimeError("Windows AEC capture is already started.")
            self._on_frame = on_frame
            self._stop.clear()
            self._ready.clear()
            self._error = None
            self._evidence = query_windows_aec(self.endpoints)
            if not self._evidence.aec_enabled:
                raise RuntimeError(
                    "The selected Windows capture endpoint does not report active AEC."
                )
            self._thread = threading.Thread(
                target=self._thread_main,
                name="butler-windows-aec-capture",
                daemon=True,
            )
            self._thread.start()

        if not self._ready.wait(timeout=max(0.1, self.startup_timeout)):
            self.stop()
            raise RuntimeError("Timed out starting the Windows AEC AudioGraph.")
        with self._lock:
            error = self._error
        if error:
            self.stop()
            raise RuntimeError(error)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))
        with self._lock:
            self._thread = None
            self._on_frame = None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "frames": self._frames,
                "pcm_bytes": self._pcm_bytes,
                "callback_errors": self._callback_errors,
                "samples_per_quantum": self._samples_per_quantum,
                "native_frame_bytes": self._native_frame_bytes,
                "error": self._error,
                "evidence": asdict(self._evidence) if self._evidence else None,
            }

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run_graph())
        except BaseException as exc:  # noqa: BLE001 - surfaced through snapshot/start
            with self._lock:
                self._error = f"{type(exc).__name__}: {exc}"[:1000]
            self._ready.set()

    async def _run_graph(self) -> None:
        try:
            from winrt.windows.devices.enumeration import DeviceInformation
            from winrt.windows.media import AudioBufferAccessMode, AudioProcessing
            from winrt.windows.media.audio import (
                AudioGraph,
                AudioGraphCreationStatus,
                AudioGraphSettings,
                AudioDeviceNodeCreationStatus,
                QuantumSizeSelectionMode,
            )
            from winrt.windows.media.capture import MediaCategory
            from winrt.windows.media.mediaproperties import AudioEncodingProperties
            from winrt.windows.media.render import AudioRenderCategory
        except ImportError as exc:  # pragma: no cover - platform/dependency guard
            raise RuntimeError(
                "Windows AudioGraph capture requires the pinned PyWinRT dependencies."
            ) from exc

        capture_device = await DeviceInformation.create_from_id_async(
            self.endpoints.capture_id
        )
        render_device = await DeviceInformation.create_from_id_async(
            self.endpoints.render_id
        )
        if capture_device is None or render_device is None:
            raise RuntimeError("A pinned Windows audio endpoint is unavailable.")

        encoding = AudioEncodingProperties.create_pcm(
            self.sample_rate,
            self.channels,
            self.bits_per_sample,
        )
        settings = AudioGraphSettings(AudioRenderCategory.COMMUNICATIONS)
        settings.primary_render_device = render_device
        settings.desired_render_device_audio_processing = AudioProcessing.DEFAULT
        settings.encoding_properties = encoding
        settings.quantum_size_selection_mode = QuantumSizeSelectionMode.CLOSEST_TO_DESIRED
        settings.desired_samples_per_quantum = round(
            self.sample_rate * self.desired_frame_ms / 1000
        )

        graph_result = await AudioGraph.create_async(settings)
        if graph_result.status != AudioGraphCreationStatus.SUCCESS:
            raise RuntimeError(
                "Windows AudioGraph creation failed: "
                f"{graph_result.status.name} ({graph_result.extended_error})."
            )
        graph = graph_result.graph
        capture_node = None
        output_node = None
        quantum_token = None
        try:
            capture_result = (
                await graph.create_device_input_node_with_format_on_device_async(
                    MediaCategory.COMMUNICATIONS,
                    encoding,
                    capture_device,
                )
            )
            if capture_result.status != AudioDeviceNodeCreationStatus.SUCCESS:
                raise RuntimeError(
                    "Windows communications capture creation failed: "
                    f"{capture_result.status.name} "
                    f"({capture_result.extended_error})."
                )
            capture_node = capture_result.device_input_node
            output_node = graph.create_frame_output_node_with_format(encoding)
            capture_node.add_outgoing_connection(output_node)

            def on_quantum_started(_sender, _args) -> None:
                frame = output_node.get_frame()
                if frame is None:
                    return
                try:
                    with frame:
                        with frame.lock_buffer(AudioBufferAccessMode.READ) as buffer:
                            with buffer.create_reference() as reference:
                                pcm = bytes(memoryview(reference)[: buffer.length])
                    if not pcm:
                        return
                    native_frame_bytes = len(pcm)
                    samples_per_quantum = self._samples_per_quantum
                    if samples_per_quantum is not None:
                        pcm = normalize_audio_graph_pcm(
                            pcm,
                            samples_per_quantum=samples_per_quantum,
                            channels=self.channels,
                        )
                    with self._lock:
                        callback = self._on_frame
                        if self._native_frame_bytes is None:
                            self._native_frame_bytes = native_frame_bytes
                        self._frames += 1
                        self._pcm_bytes += len(pcm)
                    if callback is not None:
                        try:
                            callback(pcm)
                        except Exception:
                            with self._lock:
                                self._callback_errors += 1
                except Exception as exc:
                    with self._lock:
                        self._callback_errors += 1
                        if self._error is None:
                            self._error = f"AudioGraph callback: {type(exc).__name__}: {exc}"[
                                :1000
                            ]

            quantum_token = graph.add_quantum_started(on_quantum_started)
            with self._lock:
                self._samples_per_quantum = int(graph.samples_per_quantum)
            graph.start()
            self._ready.set()

            next_endpoint_check = time.monotonic() + self.endpoint_poll_seconds
            while not self._stop.is_set():
                await asyncio.sleep(0.05)
                if time.monotonic() < next_endpoint_check:
                    continue
                next_endpoint_check = time.monotonic() + self.endpoint_poll_seconds
                defaults = get_default_windows_audio_endpoints()
                evidence = self._evidence
                if (
                    evidence is not None
                    and evidence.reference_mode == "system_default_verified"
                    and defaults.render_id != self.endpoints.render_id
                ):
                    raise RuntimeError(
                        "Default Windows render endpoint changed; disabling AEC capture."
                    )
                if defaults.capture_id != self.endpoints.capture_id:
                    raise RuntimeError(
                        "Default Windows capture endpoint changed; disabling AEC capture."
                    )
        finally:
            self._stop.set()
            if quantum_token is not None:
                graph.remove_quantum_started(quantum_token)
            graph.stop()
            if output_node is not None:
                output_node.close()
            if capture_node is not None:
                capture_node.close()
            graph.close()
            self._ready.set()
