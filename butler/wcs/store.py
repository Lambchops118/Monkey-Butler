"""WCS owns latest observations and durable source poll schedules only."""

from dataclasses import asdict
import json
import threading

from butler.storage import connect_database
from .models import Observation


class ContextStore:
    def __init__(self, path=None):
        self._conn = connect_database(path)
        self._lock = threading.RLock()

    def close(self):
        with self._lock:
            self._conn.close()

    def register(self, adapters):
        with self._lock, self._conn:
            for adapter in adapters:
                config = json.dumps(adapter.identity, sort_keys=True)
                row = self._conn.execute('SELECT config_json FROM wcs_sources WHERE category=?', (adapter.category,)).fetchone()
                if row and row[0] != config:
                    previous = json.loads(row[0])
                    old_identity = {k: v for k, v in previous.items() if k != 'collection_version'}
                    new_identity = {k: v for k, v in adapter.identity.items() if k != 'collection_version'}
                    if old_identity == new_identity:
                        # Same place/units, enhanced collection contract: preserve
                        # evidence, but do not inherit an old collector's schedule.
                        self._conn.execute("UPDATE wcs_sources SET config_json=?, status='unknown', next_poll=NULL, errors_json='[]', failures=0 WHERE category=?",
                                           (config, adapter.category))
                    else:
                        self._conn.execute('DELETE FROM wcs_observations WHERE category=?', (adapter.category,))
                        self._conn.execute('DELETE FROM wcs_sources WHERE category=?', (adapter.category,))
                self._conn.execute("INSERT OR IGNORE INTO wcs_sources(category, config_json, status) VALUES (?, ?, 'unknown')",
                                   (adapter.category, config))

    def reserve(self, category, at, next_poll):
        # Commit before network access; restart cannot immediately duplicate a poll.
        with self._lock, self._conn:
            self._conn.execute("UPDATE wcs_sources SET status='unknown', last_attempt=?, next_poll=? WHERE category=?", (at, next_poll, category))

    def commit(self, category, batch, at, next_poll, failures=0):
        if any(o.category != category for o in batch.observations + (batch.hourly or ())):
            raise ValueError('category mismatch')
        status = 'partial' if batch.errors and batch.observations else 'error' if batch.errors else 'ready'
        if batch.errors == ('not_configured',):
            status = 'not_configured'
        with self._lock, self._conn:
            self._conn.execute('UPDATE wcs_sources SET status=?, errors_json=?, next_poll=?, failures=?, last_success=CASE WHEN ? THEN ? ELSE last_success END WHERE category=?',
                (status, json.dumps(batch.errors), next_poll, failures, bool(batch.observations), at, category))
            for o in batch.observations:
                self._conn.execute('''INSERT INTO wcs_observations(category, subject, kind, observed_at, received_at, data_json)
                    VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(category, subject, kind) DO UPDATE SET
                    observed_at=excluded.observed_at, received_at=excluded.received_at, data_json=excluded.data_json
                    WHERE COALESCE(excluded.observed_at, excluded.received_at) >= COALESCE(wcs_observations.observed_at, wcs_observations.received_at)''',
                    (category, o.subject, o.kind, o.observed_at, o.received_at, json.dumps(asdict(o), allow_nan=False)))
            if batch.hourly is not None:
                self._conn.execute('DELETE FROM wcs_hourly_forecasts WHERE category=?', (category,))
                self._conn.executemany('INSERT INTO wcs_hourly_forecasts(category,valid_from,data_json) VALUES (?,?,?)',
                    [(category, o.valid_from, json.dumps(asdict(o), allow_nan=False)) for o in batch.hourly])
            count = self._conn.execute('SELECT count(*) FROM wcs_observations WHERE category=?', (category,)).fetchone()[0]
            if count > 8:
                raise ValueError('source observation limit exceeded')

    def load(self, adapters):
        with self._lock:
            sources, observations = [], []
            for adapter in adapters:
                row = self._conn.execute('SELECT * FROM wcs_sources WHERE category=?', (adapter.category,)).fetchone()
                if row:
                    sources.append(dict(row))
                rows = self._conn.execute('SELECT data_json FROM wcs_observations WHERE category=? ORDER BY kind, subject LIMIT 8', (adapter.category,))
                observations.extend(Observation(**json.loads(row[0])) for row in rows)
                rows = self._conn.execute('SELECT data_json FROM wcs_hourly_forecasts WHERE category=? ORDER BY valid_from LIMIT 48', (adapter.category,))
                observations.extend(Observation(**json.loads(row[0])) for row in rows)
            return tuple(sources), tuple(observations)
