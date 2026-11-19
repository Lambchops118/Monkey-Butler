"""Passive subscriber for the existing canonical waterer. Never publishes."""

from collections import deque
import json
import os
import threading
import time
from uuid import uuid4

from .models import Device, Observation, PropertySpec, PumpSnapshot


DEVICE_ID = 'quad_pump'
TOPIC_BASE = 'home/irrigation/quad_pump'
TOPICS = tuple(TOPIC_BASE + '/' + suffix for suffix in ('state', 'health', 'heartbeat'))
PROPERTIES = tuple(PropertySpec(f'relay_{i}', 'boolean', True) for i in range(1, 5)) + (
    PropertySpec('firmware_version', 'string'), PropertySpec('uptime_ms', 'integer', unit='ms'),
    PropertySpec('wifi_connected', 'boolean'), PropertySpec('mqtt_connected', 'boolean'),
    PropertySpec('rssi', 'integer', unit='dBm'),
)


def definition():
    host = os.getenv('BUTLER_DIS_MQTT_HOST', '').strip() or os.getenv('BUTLER_DISPLAY_MQTT_HOST', '').strip() or '192.168.1.160'
    return Device(DEVICE_ID, 'Plant watering controller', host, 'waterer',
                  adapter='pump_mqtt', properties=PROPERTIES, stale_seconds=360, health_seconds=120,
                  notes='Reports controller/relay state only; water flow and fuse sensing are not verified.')


class PumpReader:
    """Callbacks maintain a bounded source view; only DIS's owner writes SQLite."""
    def __init__(self, device, clock=time.time, client_factory=None):
        self.device, self.clock, self.client_factory = device, clock, client_factory
        self._lock = threading.Lock()
        self._client = None
        self._notify = lambda: None
        self._connected = False
        self._boot = None
        self._retired_boots = deque(maxlen=16)
        self._sequences = {}
        self._observations = {}
        self._last_live = None
        self._last_contact = None
        self._offline = False
        self._error = None

    def start(self, notify):
        self._notify = notify
        try:
            import paho.mqtt.client as mqtt
            factory = self.client_factory or mqtt.Client
            self._client = factory(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id='butler-dis-' + uuid4().hex[:12], protocol=mqtt.MQTTv311)
            self._client.connect_timeout = 3
            self._client.reconnect_delay_set(1, 30)
            username = os.getenv('BUTLER_DIS_MQTT_USERNAME', '').strip()
            if username:
                self._client.username_pw_set(username, os.getenv('BUTLER_DIS_MQTT_PASSWORD', ''))
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message
            port = int(os.getenv('BUTLER_DIS_MQTT_PORT', '1883'))
            if not 1 <= port <= 65535:
                raise ValueError('invalid broker port')
            self._client.connect_async(self.device.host, port, keepalive=30)
            self._client.loop_start()
        except Exception:
            with self._lock:
                self._error = 'broker_unavailable'
            self._notify()

    def stop(self):
        client, self._client = self._client, None
        if client:
            try:
                client.disconnect()
            finally:
                client.loop_stop()

    def _on_connect(self, client, userdata, flags, reason, properties):
        if reason != 0:
            self.connection(False)
            return
        self.connection(True)
        client.subscribe([(topic, 1) for topic in TOPICS])

    def _on_disconnect(self, client, userdata, flags, reason, properties):
        self.connection(False)

    def connection(self, connected):
        with self._lock:
            self._connected = connected
            self._last_live = None  # reconnect/replay alone cannot prove liveness
            self._offline = False
            self._error = None if connected else 'broker_unavailable'
        self._notify()

    def _on_message(self, client, userdata, message):
        self.handle(message.topic, message.payload, bool(message.retain))

    def handle(self, topic: str, raw: bytes, retained: bool = False) -> bool:
        """Validate exact topic/schema before changing any state or freshness."""
        if topic not in TOPICS or len(raw) > 8192:
            return False
        try:
            body = json.loads(raw)
            boot, event_id, payload = body['boot_id'], body['event_id'], body['payload']
            if not all(isinstance(v, str) and 1 <= len(v) <= 64 and v.isascii() and v.isprintable() for v in (boot, event_id)):
                return False
            if not isinstance(payload, dict):
                return False
            stream = topic.rsplit('/', 1)[-1]
            will = stream == 'health' and payload.get('online') is False and payload.get('reason') == 'last_will'
            sequence = body.get('sequence')
            if not will and (type(sequence) is not int or not 0 < sequence < 2**63):
                return False
            values = {}
            if stream == 'state':
                for i in range(1, 5):
                    key = f'relay_{i}'
                    if type(payload.get(key)) is not bool:
                        return False
                    values[key] = payload[key]
            elif stream == 'health':
                if type(payload.get('online')) is not bool:
                    return False
                for spec in PROPERTIES:
                    if not spec.primary and spec.name in payload:
                        if spec.name == 'rssi' and payload[spec.name] is None:
                            continue  # firmware explicitly reports unsupported RSSI as null
                        if not spec.accepts(payload[spec.name]):
                            return False
                        values[spec.name] = payload[spec.name]
            elif stream == 'heartbeat':
                if type(payload.get('uptime_ms')) is not int or not 0 <= payload['uptime_ms'] < 2**63:
                    return False
                values['uptime_ms'] = payload['uptime_ms']
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            return False
        now = self.clock()
        with self._lock:
            if boot in self._retired_boots:
                return False
            if retained:
                # Store a retained state as evidence only. Never overwrite a
                # live observation, switch live boot identity or renew health.
                if self._boot is not None and boot != self._boot:
                    return False
                if will and self._last_live is None:
                    self._offline = True
                for key, value in values.items():
                    if key not in self._observations:
                        self._observations[key] = Observation(key, value, now, event_id,
                            'pump_mqtt', True, boot, sequence)
            else:
                if self._boot != boot:
                    if self._boot is not None:
                        self._retired_boots.append(self._boot)
                    self._boot = boot
                    self._sequences.clear()
                    self._last_live = None
                if not will:
                    if sequence <= self._sequences.get(stream, 0):
                        return False
                    self._sequences[stream] = sequence
                self._last_contact = now
                if will or (stream == 'health' and payload['online'] is False):
                    self._offline = True
                else:
                    self._offline = False
                    self._last_live = now
                for key, value in values.items():
                    self._observations[key] = Observation(key, value, now, event_id,
                        'pump_mqtt', False, boot, sequence)
        self._notify()
        return True

    def read(self, device=None) -> PumpSnapshot:
        with self._lock:
            if not self._connected:
                status, error = 'unknown', self._error or 'broker_unavailable'
            elif self._offline:
                status, error = 'unreachable', 'source_offline'
            elif self._last_live is None:
                status, error = 'unknown', 'awaiting_live_message'
            elif self.clock() - self._last_live > self.device.health_seconds:
                status, error = 'unreachable', 'heartbeat_expired'
            else:
                status, error = 'reachable', None
            return PumpSnapshot(tuple(self._observations.values()), status,
                self._last_contact, self._last_live, error, self._boot)
