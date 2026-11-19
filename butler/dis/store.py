"""DIS owns latest observations and contact metadata in the shared database."""

import json
import math
import threading
from uuid import uuid4

from butler.storage import connect_database
from .models import Device, Reading, Record, Observation, PumpSnapshot


class DeviceStore:
    def __init__(self, path=None):
        self._conn = connect_database(path)
        self._lock = threading.RLock()
        self._definitions = {}

    def close(self):
        with self._lock:
            self._conn.close()

    def register(self, devices: tuple[Device, ...]):
        """Configuration owns identity; disable removed devices, discard remapped readings."""
        with self._lock, self._conn:
            self._conn.execute("UPDATE dis_devices SET enabled = 0")
            for device in devices:
                info = {"host": device.host, "kind": device.kind}
                if device.adapter != 'kasa':
                    info.update(adapter=device.adapter, properties=[p.name for p in device.properties], notes=device.notes)
                config = json.dumps(info, sort_keys=True)
                old = self._conn.execute("SELECT config_json FROM dis_devices WHERE device_id=?", (device.device_id,)).fetchone()
                if old and old[0] != config:
                    self._conn.execute("DELETE FROM dis_observations WHERE device_id=?", (device.device_id,))
                    self._conn.execute("DELETE FROM dis_health WHERE device_id=?", (device.device_id,))
                self._conn.execute("""INSERT INTO dis_devices(device_id, name, adapter, config_json, enabled)
                    VALUES (?, ?, ?, ?, 1) ON CONFLICT(device_id) DO UPDATE SET
                    name=excluded.name, adapter=excluded.adapter, config_json=excluded.config_json, enabled=1""",
                    (device.device_id, device.name, device.adapter, config))

        self._definitions = {d.device_id: d for d in devices}

    def record(self, device_id: str, at: float, reading: Reading | PumpSnapshot | None, error: str | None):
        if not math.isfinite(at) or at <= 0:
            raise ValueError("invalid observation timestamp")
        if error not in (None, "timeout", "read_failed", "invalid_reading", "dependency_missing", "authentication_failed"):
            raise ValueError("unsupported contact error")
        if (reading is None) == (error is None):
            raise ValueError("supply either a reading or a failure")
        device = self._definitions.get(device_id)
        if device is None or device.adapter == 'inventory':
            raise ValueError('unknown or non-observable device')
        if isinstance(reading, PumpSnapshot):
            observations, status = reading.observations, reading.status
            contact, success, error, boot = reading.last_contact, reading.last_success, reading.error, reading.boot_id
        else:
            observations = ((Observation('power', reading.power, reading.received_at, str(uuid4()), 'kasa_local_read'),)
                            if reading else ())
            status, contact, success, boot = ('unreachable' if error else 'reachable'), at, (None if error else at), None
        specs = {p.name: p for p in device.properties}
        if len(observations) > 16 or len({o.name for o in observations}) != len(observations):
            raise ValueError('invalid observation batch')
        for observation in observations:
            if observation.name not in specs or not specs[observation.name].accepts(observation.value):
                raise ValueError('invalid property value')
            if not math.isfinite(observation.received_at) or not 0 < observation.received_at <= at + 5:
                raise ValueError('invalid observation timestamp')
        with self._lock, self._conn:
            registered = self._conn.execute("SELECT 1 FROM dis_devices WHERE device_id=? AND enabled=1", (device_id,)).fetchone()
            if not registered:
                raise ValueError("unknown or disabled device")
            self._conn.execute("""INSERT INTO dis_health(device_id, last_attempt, last_success, error, status, boot_id, last_contact)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(device_id) DO UPDATE SET
                last_attempt=excluded.last_attempt,
                last_success=COALESCE(excluded.last_success, dis_health.last_success), error=excluded.error,
                status=excluded.status, boot_id=excluded.boot_id, last_contact=excluded.last_contact
                WHERE excluded.last_attempt >= dis_health.last_attempt""",
                (device_id, at, success, error, status, boot, contact))
            for observation in observations:
                self._conn.execute("""INSERT INTO dis_observations
                    (device_id, property_name, value_json, received_at, evidence_id, source, retained, boot_id, source_sequence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(device_id, property_name) DO UPDATE SET
                    value_json=excluded.value_json, received_at=excluded.received_at, evidence_id=excluded.evidence_id,
                    source=excluded.source, retained=excluded.retained, boot_id=excluded.boot_id,
                    source_sequence=excluded.source_sequence
                    WHERE excluded.received_at > dis_observations.received_at""",
                    (device_id, observation.name, json.dumps(observation.value), observation.received_at,
                     observation.evidence_id, observation.source, int(observation.retained), observation.boot_id, observation.sequence))

    def load(self, devices: tuple[Device, ...]) -> tuple[Record, ...]:
        with self._lock:
            health = {r['device_id']: dict(r) for r in self._conn.execute('SELECT * FROM dis_health')}
            observations = {}
            for r in self._conn.execute('SELECT * FROM dis_observations'):
                observations.setdefault(r['device_id'], []).append(Observation(
                    r['property_name'], json.loads(r['value_json']), r['received_at'], r['evidence_id'],
                    r['source'], bool(r['retained']), r['boot_id'], r['source_sequence']))
        result = []
        for device in devices:
            row = health.get(device.device_id, {})
            result.append(Record(device, tuple(observations.get(device.device_id, ())),
                row.get('last_attempt'), row.get('last_success'), row.get('error'),
                row.get('status', 'unknown'), row.get('boot_id'), row.get('last_contact')))
        return tuple(result)
