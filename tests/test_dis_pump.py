"""Passive waterer contracts: no hardware or model calls."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from butler.dis.pump import PumpReader, definition, TOPIC_BASE
from butler.dis.service import DeviceInformationService, configured_devices
from butler.dis.store import DeviceStore


class PumpTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.reader = PumpReader(definition(), clock=lambda: self.now)
        self.reader.connection(True)

    def send(self, stream, payload, seq=1, boot='boot-a', retained=False):
        return self.reader.handle(TOPIC_BASE+'/'+stream, json.dumps(dict(
            event_id=f'{boot}-{stream}-{seq}', boot_id=boot, sequence=seq, payload=payload)).encode(), retained)

    def state(self, **kw):
        return self.send('state', {f'relay_{i}': i == 1 for i in range(1, 5)}, **kw)

    def test_live_duplicates_reboot_and_late_packets(self):
        self.assertTrue(self.state())
        self.assertFalse(self.state())
        self.assertTrue(self.send('heartbeat', {'uptime_ms': 5}, seq=10))
        self.assertTrue(self.state(seq=2))  # sequence is checked per stream
        self.assertTrue(self.send('heartbeat', {'uptime_ms': 0}, boot='boot-b'))
        self.assertFalse(self.state(seq=3))
        self.assertEqual(self.reader.read().boot_id, 'boot-b')

    def test_retained_is_never_liveness_and_heartbeat_does_not_redate_relays(self):
        self.state(retained=True)
        self.assertEqual(self.reader.read().status, 'unknown')
        received = self.reader.read().observations[0].received_at
        self.now += 10
        self.send('heartbeat', {'uptime_ms': 10})
        snapshot = self.reader.read()
        self.assertEqual(snapshot.status, 'reachable')
        self.assertTrue(snapshot.observations[0].retained)
        self.assertEqual(snapshot.observations[0].received_at, received)
        self.now += 121
        self.assertEqual(self.reader.read().error, 'heartbeat_expired')
        self.reader.connection(False)
        self.assertEqual(self.reader.read().status, 'unknown')

    def test_invalid_messages_and_last_will(self):
        self.assertFalse(self.send('state', {'relay_1': True}))
        self.assertFalse(self.send('heartbeat', {'uptime_ms': True}))
        self.assertFalse(self.reader.handle(TOPIC_BASE+'/command', b'{}'))
        self.state()
        self.assertTrue(self.send('health', {'online': True, 'rssi': None, 'firmware_version': 'test'}))
        self.assertTrue(self.send('health', {'online': False, 'reason': 'last_will'}, seq=None))
        self.assertEqual(self.reader.read().status, 'unreachable')
        self.assertTrue(self.send('heartbeat', {'uptime_ms': 20}, seq=2))
        self.assertEqual(self.reader.read().status, 'reachable')

    def test_store_projection_retained_restart_and_new_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DeviceStore(Path(tmp)/'test.sqlite3')
            svc = DeviceInformationService((definition(),), store, self.reader)
            store.register(svc.devices)
            svc._records = store.load(svc.devices)
            svc._error = None
            def commit():
                svc._accept('quad_pump', time.monotonic(), self.reader.read(), None)
                return svc.read()['devices'][0]['properties']['relay_1']
            try:
                self.state(retained=True)
                self.send('heartbeat', {'uptime_ms': 1})
                self.assertIsNone(commit()['value'])
                self.now += .01
                self.state(seq=2)
                self.assertIs(commit()['value'], True)
                self.now += .01
                self.send('heartbeat', {'uptime_ms': 0}, boot='new-boot')
                self.assertIsNone(commit()['value'])
                svc._verified.clear()  # a new process never requalifies persisted evidence
                self.assertIsNone(svc.read()['devices'][0]['properties']['relay_1']['value'])
            finally:
                store.close()

    def test_inventory_is_explicit_and_never_polled(self):
        with patch('butler.dis.service.smart_plugs._load_devices', return_value={}):
            devices = configured_devices()
        inventory = tuple(d for d in devices if d.adapter == 'inventory')
        self.assertEqual(len(inventory), 6)
        with tempfile.TemporaryDirectory() as tmp:
            store = DeviceStore(Path(tmp)/'test.sqlite3')
            svc = DeviceInformationService(inventory, store, self.reader)
            store.register(inventory)
            svc._records, svc._error = store.load(inventory), None
            try:
                self.assertEqual(svc._due, {})
                self.assertTrue(all(d['health']['status'] == 'not_integrated' and not d['properties'] for d in svc.read()['devices']))
                self.assertIn('jeep-wrangler', svc.summary())
            finally:
                store.close()

    def test_mqtt_subscribes_to_exact_topics_without_publishing(self):
        from unittest.mock import MagicMock
        from butler.dis.pump import TOPICS
        client = MagicMock()
        reader = PumpReader(definition(), client_factory=lambda **kw: client)
        reader.start(lambda: None)
        reader._on_connect(client, None, None, 0, None)
        client.subscribe.assert_called_once_with([(topic, 1) for topic in TOPICS])
        client.publish.assert_not_called()
        client.will_set.assert_not_called()
        reader.stop()
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

    def test_passive_and_inventory_refresh_never_wait_or_query(self):
        from butler.dis import service
        from unittest.mock import MagicMock
        with patch('butler.dis.service.smart_plugs._load_devices', return_value={}):
            devices = configured_devices()
        with tempfile.TemporaryDirectory() as tmp:
            store = DeviceStore(Path(tmp)/'test.sqlite3')
            svc = DeviceInformationService(devices, store, self.reader)
            store.register(devices)
            svc._records, svc._error = store.load(devices), None
            try:
                svc.refresh = MagicMock(side_effect=AssertionError('blocking refresh'))
                with patch.object(service, '_service', svc):
                    self.assertEqual(service.read_devices('quad_pump', refresh=True)['refresh']['status'], 'passive_source_no_query')
                    self.assertEqual(service.read_devices('kitchen-screen', refresh=True)['refresh']['status'], 'not_integrated')
                text = svc.summary()
                self.assertIn('shown 7/7', text)
                self.assertLessEqual(len(text), svc.settings.summary_chars)
            finally:
                store.close()
