"""Hourly forecast persistence, temporal queries and same-request collection."""

from dataclasses import replace
from datetime import datetime, timezone
import json
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

from butler.wcs.models import Batch, Observation
from butler.wcs.store import ContextStore
from butler.wcs.service import WorldContextService, query_window
from test_wcs import Reader, observation
import test_wcs as fixtures


def hours(now, count=48):
    base = int(now//3600)*3600
    return tuple(Observation(f'hour-{i}', 'weather', 'Test town', 'openweather-hourly',
        'forecast', None, now, base+i*3600, base+(i+1)*3600, 'America/New_York',
        {'temperature': {'value': 38+i, 'unit': 'F'}}, resolution='hourly') for i in range(count))


class HourlyTests(unittest.TestCase):
    def make(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        reader = Reader()
        svc = WorldContextService((reader,), ContextStore(Path(tmp.name)/'butler.sqlite3'))
        self.addCleanup(svc.stop)
        svc.store.register(svc.adapters)
        svc._publish()
        return svc, reader

    def test_same_api_request_provides_48_hourly_samples(self):
        reader, get = fixtures.WeatherTests().make()
        batch = reader.read()
        self.assertEqual(batch.errors, ())
        self.assertEqual(len(batch.hourly), 48)
        self.assertEqual(get.call_count, 3)  # geocode/current/onecall, not another endpoint
        self.assertNotIn('hourly', get.call_args.kwargs['params']['exclude'].split(','))
        self.assertEqual(batch.hourly[0].resolution, 'hourly')
        self.assertEqual(batch.hourly[0].values['temperature']['value'], 38)

    def test_missing_or_bad_hourly_data_preserves_current_and_daily(self):
        for data in ([], [{'dt': time.time(), 'temp': True}],
                     [{'dt': time.time(), 'temp': 1}]*2):
            reader, get = fixtures.WeatherTests().make(daily={'daily': [{'dt': time.time(), 'temp': {'max': 60, 'min': 40}}], 'hourly': data})
            batch = reader.read()
            self.assertIsNone(batch.hourly)
            self.assertEqual(len(batch.observations), 2)
            self.assertTrue(any(e.startswith('hourly_') for e in batch.errors))

    def test_daily_failure_does_not_discard_valid_hourly(self):
        reader, get = fixtures.WeatherTests().make(daily={'daily': []})
        batch = reader.read()
        self.assertEqual(len(batch.hourly), 48)
        self.assertEqual(batch.errors, ('daily_forecast_unavailable',))

    def test_future_hourly_values_are_available_and_expired_are_historical(self):
        now = time.time()
        hour = hours(now)[2]
        view = hour.view(now)
        self.assertEqual(view['temporal_status'], 'future_forecast')
        self.assertTrue(view['values'])
        old = hour.view(hour.valid_until)
        self.assertEqual(old['values'], {})
        self.assertTrue(old['last_reported_values'])

    def test_store_replaces_series_atomically_and_failure_retains_previous(self):
        svc, reader = self.make()
        now = time.time()
        reader.batch = Batch((observation(),), hourly=hours(now))
        svc._poll(reader)
        original = svc.read('weather', forecast='hourly')
        self.assertEqual(original['coverage']['total'], 48)
        self.assertEqual(len(original['observations']), 8)
        reader.batch = Batch((observation(),), ('hourly_unavailable',))
        svc._poll(reader)
        self.assertEqual(svc.read('weather', forecast='hourly')['observations'], original['observations'])
        reader.batch = Batch((observation(),), hourly=hours(now+3600, 24))
        svc._poll(reader)
        self.assertEqual(svc.read('weather', forecast='hourly')['coverage']['total'], 24)
        svc._publish()  # round-trip through the actual DB preserves the new series
        self.assertEqual(svc.read('weather', forecast='hourly')['coverage']['total'], 24)

    def test_exact_hour_range_cache_only_and_pagination(self):
        svc, reader = self.make()
        now = time.time()
        data = hours(now)
        reader.batch = Batch((observation(),), hourly=data)
        svc._poll(reader)
        target = datetime.fromtimestamp(data[8].valid_from, timezone.utc).isoformat()
        with mock.patch.object(svc.store, 'load', side_effect=AssertionError('database')), \
             mock.patch.object(reader, 'read', side_effect=AssertionError('network')):
            result = svc.read('weather', forecast='hourly', start_at=target)
            self.assertEqual(result['coverage']['total'], 1)
            self.assertEqual(result['observations'][0]['values']['temperature']['value'], 46)
            self.assertEqual(svc.read()['coverage']['total'], 1)  # overview excludes hourly rows
            self.assertEqual(svc.read('weather', offset=8, forecast='hourly')['coverage']['next_offset'], 16)
            self.assertLessEqual(len(svc.summary()), svc.settings.summary_chars)
        empty = svc.read('weather', forecast='hourly', start_at='2030-01-01T08:00:00-05:00')
        self.assertEqual(empty['observations'], [])
        self.assertIsNotNone(empty['forecast_window']['available_until'])

    def test_time_ranges_require_offsets_and_have_bounded_lengths(self):
        for start, end in (('2026-11-19T08:00:00', ''), ('', '2026-11-19T09:00:00Z'),
                           ('2026-11-19T08:00:00Z', '2026-11-19T07:00:00Z'),
                           ('2026-11-19T08:00:00Z', '2026-11-22T08:00:00Z')):
            with self.assertRaises(ValueError):
                query_window('hourly', start, end, time.time())
        a = query_window('hourly', '2026-11-01T01:00:00-04:00', '', time.time())
        b = query_window('hourly', '2026-11-01T01:00:00-05:00', '', time.time())
        self.assertEqual(b[0]-a[0], 3600)  # repeated DST hour stays unambiguous

    def test_config_change_removes_old_hourly_forecasts(self):
        svc, reader = self.make()
        reader.batch = Batch((observation(),), hourly=hours(time.time()))
        svc._poll(reader)
        reader.identity = {'location': 'Other place'}
        svc.store.register(svc.adapters)
        svc._publish()
        self.assertEqual(svc.read('weather', forecast='hourly')['observations'], [])

    def test_batch_rejects_oversize_duplicate_and_wrong_resolution(self):
        data = hours(time.time())
        for invalid in (data+(data[-1],), (data[0], data[0]), (observation(),)):
            with self.assertRaises(ValueError):
                Batch((), hourly=invalid)

    def test_forecast_at_fixed_offset_and_repeated_dst_hour(self):
        hour = hours(time.time())[0]
        fixed = replace(hour, timezone='UTC-05:00').view(time.time())
        self.assertTrue(fixed['forecast_at'].endswith('-05:00'))
        a = datetime.fromisoformat('2026-11-01T01:00:00-04:00').timestamp()
        first = replace(hour, valid_from=a, valid_until=a+3600).view(a-1)
        second = replace(hour, valid_from=a+3600, valid_until=a+7200).view(a-1)
        self.assertTrue(first['forecast_at'].endswith('01:00:00-04:00'))
        self.assertTrue(second['forecast_at'].endswith('01:00:00-05:00'))

    def test_failed_series_replacement_rolls_back_delete_and_inserts(self):
        import sqlite3
        svc, reader = self.make()
        now = time.time()
        data = hours(now, 3)
        svc.store.commit('weather', Batch((observation(),), hourly=data), now, now+900)
        svc.store._conn.execute("CREATE TRIGGER fail_hour BEFORE INSERT ON wcs_hourly_forecasts BEGIN SELECT RAISE(ABORT, 'test write failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            svc.store.commit('weather', Batch((observation(),), hourly=hours(now+3600, 2)), now, now+900)
        svc._publish()
        result = svc.read('weather', forecast='hourly')
        self.assertEqual(result['coverage']['total'], 3)
        self.assertEqual(result['observations'][0]['observation_id'], data[0].observation_id)

    def test_full_temperature_timeline_fits_default_summary_with_weather_details(self):
        svc, reader = self.make()
        now = time.time()
        current = observation(values={
            'temperature': {'value': 40.96, 'unit': 'F'}, 'humidity': {'value': 66, 'unit': '%'},
            'feels_like': {'value': 38.2, 'unit': 'F'}, 'pressure': {'value': 1032, 'unit': 'hPa'},
            'wind_speed': {'value': 3.44, 'unit': 'mph'}, 'cloud_cover': {'value': 0, 'unit': '%'},
            'conditions': {'value': 'clear sky', 'unit': None}})
        daily = observation(kind='forecast', source='openweather-daily', observed_at=None,
            valid_from=now-3600, valid_until=now+23*3600, resolution='daily', values={
            'high': {'value': 68.22, 'unit': 'F'}, 'low': {'value': 35.44, 'unit': 'F'},
            'precipitation_probability': {'value': 0, 'unit': '%'}, 'uv_index': {'value': 2.57, 'unit': None}})
        data = tuple(replace(o, values={'temperature': {'value': 38.12+i/100, 'unit': 'F'},
            'precipitation_probability': {'value': i, 'unit': '%'}})
                     for i, o in enumerate(hours(now)))
        reader.batch = Batch((current, daily), hourly=data)
        svc._poll(reader)
        text = svc.summary()
        self.assertLessEqual(len(text), svc.settings.summary_chars)
        self.assertIn('Hourly samples 48/48', text)
        self.assertIn('observations 2/2', text)

    def test_collection_upgrade_preserves_observations_but_invalidates_old_poll_schedule(self):
        svc, reader = self.make()
        svc._poll(reader)
        saved = svc.read()['observations']
        self.assertGreater(svc._cache[0][0]['next_poll'], time.time())
        reader.identity = {**reader.identity, 'collection_version': 2}
        svc.store.register(svc.adapters)
        svc._publish()
        self.assertIsNone(svc._cache[0][0]['next_poll'])
        self.assertEqual(svc.read()['observations'], saved)
        self.assertEqual(svc.read()['sources'][0]['status'], 'unknown')
        reader.batch = Batch((observation(),), hourly=hours(time.time()))
        svc.start()
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            if svc.read('weather', forecast='hourly')['coverage']['total']:
                break
            time.sleep(.01)
        self.assertEqual(svc.read('weather', forecast='hourly')['coverage']['total'], 48)

    def test_same_collection_version_preserves_failure_backoff_on_restart(self):
        svc, reader = self.make()
        reader.identity = {**reader.identity, 'collection_version': 2}
        svc.store.register(svc.adapters)
        reader.batch = Batch((), ('timeout',))
        svc._poll(reader)
        saved = svc._cache[0][0]['next_poll']
        svc.store.register(svc.adapters)
        svc._publish()
        self.assertEqual(svc._cache[0][0]['next_poll'], saved)
        self.assertEqual(svc.read()['sources'][0]['status'], 'error')
