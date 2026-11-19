"""Small typed DIS contracts. No arbitrary device payloads enter the store."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
import time
from typing import Literal, NotRequired, TypedDict


ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
MAX_DEVICES = 64
Scalar = bool | int | float | str


@dataclass(frozen=True)
class PropertySpec:
    name: str
    value_type: Literal['boolean', 'integer', 'string']
    primary: bool = False
    unit: str | None = None

    def accepts(self, value):
        return ((self.value_type == 'boolean' and type(value) is bool)
                or (self.value_type == 'integer' and type(value) is int and abs(value) < 2**63)
                or (self.value_type == 'string' and isinstance(value, str) and 0 < len(value) <= 100
                    and all(ord(c) >= 32 for c in value)))


class PropertyView(TypedDict):
    # value is usable CURRENT state only; historical evidence is separate.
    value: Scalar | None
    last_observed_value: Scalar | None
    status: Literal['current', 'stale', 'unknown']
    age_seconds: float | None
    observed_at: str | None
    received_at: str | None
    source: str | None
    evidence_id: str | None
    unit: NotRequired[str | None]
    retained: NotRequired[bool]
    boot_id: NotRequired[str | None]
    source_sequence: NotRequired[int | None]


class HealthView(TypedDict):
    status: Literal['reachable', 'unreachable', 'unknown', 'not_integrated']
    last_attempt_at: str | None
    last_success_at: str | None
    error: str | None
    last_contact_at: NotRequired[str | None]


class Capabilities(TypedDict):
    observed: list[str]
    meaning: Literal['relay_power', 'plug_power', 'controller_telemetry', 'inventory_only']
    physical_outcome_verified: bool


class DeviceView(TypedDict):
    device_id: str
    name: str
    kind: str
    adapter: str
    refresh_pending: bool
    capabilities: Capabilities
    health: HealthView
    properties: dict[str, PropertyView]
    notes: NotRequired[str]


class Coverage(TypedDict):
    total: int
    shown: int
    omitted_count: int
    truncated: bool
    offset: NotRequired[int]
    next_offset: NotRequired[int | None]


class ErrorInfo(TypedDict):
    code: str


class RefreshInfo(TypedDict):
    completed: bool
    status: str


class ReadResult(TypedDict):
    schema_version: Literal[1]
    ok: bool
    status: Literal['available', 'unavailable', 'not_found']
    as_of: str
    error: ErrorInfo | None
    devices: list[DeviceView]
    coverage: Coverage
    refresh: NotRequired[RefreshInfo]


@dataclass(frozen=True)
class Device:
    device_id: str
    name: str
    host: str
    kind: str
    adapter: Literal['kasa', 'pump_mqtt', 'inventory'] = 'kasa'
    properties: tuple[PropertySpec, ...] = (PropertySpec('power', 'boolean', True),)
    stale_seconds: float | None = None
    health_seconds: float | None = None
    notes: str = ''

    def __post_init__(self):
        if not ID_PATTERN.fullmatch(self.device_id):
            raise ValueError("invalid device id")
        if not self.name or len(self.name) > 100 or any(ord(c) < 32 for c in self.name):
            raise ValueError("invalid device name")
        if not ID_PATTERN.fullmatch(self.kind) or len(self.host) > 255:
            raise ValueError("invalid device definition")
        if self.adapter not in ('kasa', 'pump_mqtt', 'inventory'):
            raise ValueError('unsupported adapter')
        if self.adapter != 'inventory' and not self.host:
            raise ValueError('missing endpoint')
        if self.adapter == 'kasa' and self.kind not in ('light', 'appliance'):
            raise ValueError('invalid Kasa device kind')
        if len(self.properties) > 16 or len({p.name for p in self.properties}) != len(self.properties):
            raise ValueError('invalid property declarations')
        for prop in self.properties:
            if not ID_PATTERN.fullmatch(prop.name) or prop.value_type not in ('boolean', 'integer', 'string'):
                raise ValueError('invalid property declaration')
        if len(self.notes) > 160 or any(ord(c) < 32 for c in self.notes):
            raise ValueError('invalid device notes')


@dataclass(frozen=True)
class Reading:
    power: bool
    received_at: float

    def __post_init__(self):
        if type(self.power) is not bool or not math.isfinite(self.received_at) or self.received_at <= 0:
            raise ValueError("invalid power observation")


@dataclass(frozen=True)
class Observation:
    name: str
    value: Scalar
    received_at: float
    evidence_id: str
    source: str
    retained: bool = False
    boot_id: str | None = None
    sequence: int | None = None


@dataclass(frozen=True)
class PumpSnapshot:
    observations: tuple[Observation, ...]
    status: Literal['reachable', 'unreachable', 'unknown']
    last_contact: float | None
    last_success: float | None
    error: str | None
    boot_id: str | None


@dataclass(frozen=True)
class Record:
    device: Device
    observations: tuple[Observation, ...]
    last_attempt: float | None
    last_success: float | None
    error: str | None
    health_status: str = 'unknown'
    boot_id: str | None = None
    last_contact: float | None = None

    @property
    def reading(self):
        """Compatibility view of the Kasa power observation, not another store."""
        power = next((o for o in self.observations if o.name == 'power'), None)
        return Reading(power.value, power.received_at) if power else None


def timestamp(value: float | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds") if value is not None else None


def unavailable(reason: str) -> ReadResult:
    return {'schema_version': 1, 'ok': False, 'status': 'unavailable',
            'as_of': timestamp(time.time()), 'error': {'code': reason}, 'devices': [],
            'coverage': {'total': 0, 'shown': 0, 'omitted_count': 0, 'truncated': False}}
