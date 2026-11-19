"""Cross-domain persistence, startup and migration boundaries on real SQLite."""

import concurrent.futures
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from butler import storage
from butler.jobs import JobStore
from butler.launcher import maintenance
from butler.memory import MemoryStore
from butler.phone.store import PhoneCallStore
from butler.storage_schema import TABLE_OWNERS


def add_call(store, call_id='call-1'):
    return store.create_call(call_id=call_id, provider='test',
        direction='outbound', remote_number='+15555550123', status='completed')


class UnifiedStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'butler.sqlite3'
        patch = mock.patch.dict('os.environ', {'BUTLER_DB_PATH': str(self.path)})
        patch.start()
        self.addCleanup(patch.stop)

    def store(self, factory):
        store = factory()
        self.addCleanup(store.close)
        return store

    def test_all_defaults_share_one_file_and_survive_reopen(self):
        memory, jobs, phone = [self.store(f) for f in (MemoryStore, JobStore, PhoneCallStore)]
        self.assertEqual({s.db_path for s in (memory, jobs, phone)}, {self.path})
        exchange = [{'role': 'assistant', 'tool_calls': [{'id': 'c1',
            'type': 'function', 'function': {'name': 'read_test', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'c1', 'content': '{"power":"off"}'}]
        memory.record_turn('owner', 'check lamp', 'Lamp off.', tool_messages=exchange)
        memory.upsert_fact('user', 'units', 'metric')
        job = jobs.create_job(session_id='owner', source='test', request_text='work')
        add_call(phone)
        reopened = self.store(MemoryStore)
        self.assertEqual(reopened.search_facts('units')[0].value, 'metric')
        self.assertTrue(any(m.get('role') == 'tool' for m in reopened.get_recent_messages('owner')))
        self.assertEqual(self.store(JobStore).get_job(job.job_id).request_text, 'work')
        self.assertEqual(self.store(PhoneCallStore).get_call('call-1').status, 'completed')
        self.assertEqual({r[0] for r in memory._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}, set(TABLE_OWNERS))

    def test_clear_conversation_preserves_other_owners_and_database(self):
        memory, jobs, phone = [self.store(f) for f in (MemoryStore, JobStore, PhoneCallStore)]
        memory.record_turn('owner', 'hello', 'hi')
        memory.upsert_fact('user', 'units', 'metric')
        job = jobs.create_job(session_id='owner', source='test', request_text='keep')
        jobs.add_event(job_id=job.job_id, session_id='owner', event_type='queued', message='keep')
        add_call(phone)
        maintenance.clear_all_memory(log=lambda *_: None)
        self.assertTrue(self.path.exists())
        self.assertEqual(memory.list_session_ids(), [])
        self.assertEqual(memory.search_facts('units'), [])
        self.assertIsNotNone(jobs.get_job(job.job_id))
        self.assertEqual(jobs._conn.execute('SELECT count(*) FROM job_events').fetchone()[0], 1)
        self.assertIsNotNone(phone.get_call('call-1'))
        self.assertEqual(memory._conn.execute('SELECT count(*) FROM butler_schema_migrations').fetchone()[0], 1)

    def test_history_only_clear_preserves_saved_facts_and_calls(self):
        memory, phone = self.store(MemoryStore), self.store(PhoneCallStore)
        memory.record_turn('owner', 'hello', 'hi')
        memory.upsert_fact('user', 'units', 'metric')
        add_call(phone)
        maintenance.clear_chat_history(log=lambda *_: None)
        self.assertEqual(memory.list_session_ids(), [])
        self.assertEqual(memory.search_facts('units')[0].value, 'metric')
        self.assertIsNotNone(phone.get_call('call-1'))

    def test_parallel_first_open_and_writes_do_not_lose_rows(self):
        def work(index):
            factory = (MemoryStore, JobStore, PhoneCallStore)[index % 3]
            store = factory()
            try:
                if index % 3 == 0:
                    store.record_turn(f'session-{index}', 'hello', 'hi')
                elif index % 3 == 1:
                    store.create_job(session_id='owner', source='test', request_text=str(index))
                else:
                    add_call(store, f'call-{index}')
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(work, range(18)))
        connection = storage.connect_database()
        try:
            for table in ('conversation_sessions', 'jobs', 'phone_calls'):
                self.assertEqual(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 6)
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(connection.execute('PRAGMA busy_timeout').fetchone()[0], 5000)
        finally:
            connection.close()

    def test_failed_domain_write_releases_shared_writer_lock(self):
        jobs, memory = self.store(JobStore), self.store(MemoryStore)
        with self.assertRaises(sqlite3.IntegrityError):
            jobs.add_event(job_id='missing', session_id='owner', event_type='bad', message='bad')
        memory._conn.execute('PRAGMA busy_timeout = 100')
        memory.upsert_fact('user', 'after_error', 'saved')
        self.assertFalse(jobs._conn.in_transaction)

    def test_contended_write_times_out_and_can_be_retried_after_unlock(self):
        memory, jobs = self.store(MemoryStore), self.store(JobStore)
        memory._conn.execute('PRAGMA busy_timeout = 50')
        jobs._conn.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                memory.upsert_fact('user', 'units', 'metric')
            self.assertFalse(memory._conn.in_transaction)
        finally:
            jobs._conn.rollback()
        memory.upsert_fact('user', 'units', 'metric')
        self.assertEqual(memory.search_facts('units')[0].value, 'metric')

    def test_migration_failure_rolls_back_ddl_and_ledger(self):
        storage.initialize_database()
        migrations = storage.MIGRATIONS + ((2, 'broken', (
            'CREATE TABLE should_rollback (id INTEGER)', 'INVALID SQL')),)
        with mock.patch.object(storage, 'MIGRATIONS', migrations):
            with self.assertRaises(storage.DatabaseError):
                storage.initialize_database()
        connection = storage.connect_database()
        try:
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='should_rollback'"
            ).fetchone())
            self.assertEqual(connection.execute('SELECT max(version) FROM butler_schema_migrations').fetchone()[0], 1)
        finally:
            connection.close()

    def test_rejects_newer_changed_or_missing_schema_without_repairing(self):
        for change in (
            "INSERT INTO butler_schema_migrations VALUES (99, 'future', 'x', 'now')",
            "UPDATE butler_schema_migrations SET checksum='changed'",
            'DROP TABLE phone_call_events',
        ):
            path = Path(self.tmp.name) / f'case-{len(change)}.sqlite3'
            storage.initialize_database(path)
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute(change)
            with self.assertRaises(storage.DatabaseError):
                storage.initialize_database(path)

    def test_legacy_files_and_environment_are_not_imported_or_selected(self):
        old = Path(self.tmp.name) / 'talos_memory.sqlite3'
        with closing(sqlite3.connect(old)) as connection, connection:
            connection.execute('CREATE TABLE facts (value TEXT)')
            connection.execute("INSERT INTO facts VALUES ('old')")
        original = old.read_bytes()
        with mock.patch.dict('os.environ', {'BUTLER_MEMORY_DB_PATH': str(old),
                'BUTLER_JOBS_DB_PATH': str(old), 'BUTLER_PHONE_DB_PATH': str(old)}):
            memory = self.store(MemoryStore)
            self.assertEqual(memory.db_path, self.path)
            self.assertEqual(memory.search_facts('old'), [])
        self.assertEqual(old.read_bytes(), original)
        with self.assertRaisesRegex(storage.DatabaseError, 'Legacy stores are not imported'):
            storage.initialize_database(old)

    def test_readonly_dashboard_connection_cannot_create_or_write(self):
        with self.assertRaises(sqlite3.OperationalError):
            storage.connect_readonly(self.path)
        self.assertFalse(self.path.exists())
        storage.initialize_database()
        connection = storage.connect_readonly(self.path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute('DELETE FROM conversation_sessions')
        finally:
            connection.close()

    def test_startup_stops_before_workers_when_database_fails(self):
        from butler import main
        with mock.patch.object(main, 'initialize_database', side_effect=storage.DatabaseError('broken')), \
             mock.patch.object(main.threading, 'Thread') as thread, \
             mock.patch.object(main.text_agent_server, 'start_text_agent_server') as server:
            with self.assertRaisesRegex(storage.DatabaseError, 'broken'):
                main.main()
        thread.assert_not_called()
        server.assert_not_called()

    def test_path_is_stable_and_global_memory_override_is_rejected(self):
        with mock.patch.dict('os.environ', {'BUTLER_DB_PATH': 'db/custom.sqlite3'}):
            self.assertEqual(storage.database_path(), storage.REPO_ROOT / 'db/custom.sqlite3')
        with mock.patch.dict('os.environ', {'BUTLER_DB_PATH': ':memory:'}):
            with self.assertRaises(storage.DatabaseError):
                storage.database_path()
        connection = storage.connect_database(':memory:')
        connection.close()


if __name__ == '__main__':
    unittest.main()
