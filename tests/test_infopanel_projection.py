import unittest
from datetime import datetime, timezone
from unittest import mock

from butler.display.projection import project
from butler.ltms import service as ltms_service
import test_wcs as wcs_fixtures


class ProjectionTests(unittest.TestCase):
    def test_ltms_health_distinguishes_workers_and_degradation(self):
        worker = mock.Mock()
        worker.is_alive.return_value = True
        service = mock.Mock(thread=worker, intake_thread=worker, error=None)
        service.stop_event.is_set.return_value = False
        with mock.patch.object(ltms_service, '_service', service):
            self.assertEqual(ltms_service.component_health()['status'], 'available')
            service.error = 'embedding_unavailable_lexical_fallback'
            self.assertEqual(ltms_service.component_health()['status'], 'degraded')
            worker.is_alive.return_value = False
            self.assertEqual(ltms_service.component_health()['status'], 'unavailable')

    def test_current_uv_is_distinct_observation(self):
        now = datetime.now(timezone.utc).timestamp()
        payload = {'timezone': 'America/New_York', 'current': {'dt': now - 60, 'uvi': 4.2},
                   'daily': [{'dt': now, 'temp': {'min': 40, 'max': 60}}]}
        reader, _ = wcs_fixtures.WeatherTests().make(now=now, daily=payload)
        batch = reader.read()
        self.assertEqual(batch.errors, ())
        uv = next(o for o in batch.observations if o.source == 'openweather-onecall-current')
        self.assertEqual(uv.values['uv_index']['value'], 4.2)
        self.assertEqual(uv.observed_at, now - 60)

    def test_weather_and_dynamo_projection(self):
        now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        current = {'source': 'openweather-current', 'observed_at': now.isoformat(), 'received_at': now.isoformat(),
                   'values': {'temperature': {'value': 44, 'unit': 'F'},
                              'conditions': {'value': 'light rain', 'unit': None}}}
        uv = {'source': 'openweather-onecall-current', 'observed_at': now.isoformat(), 'received_at': now.isoformat(),
              'values': {'uv_index': {'value': 3.5, 'unit': None}}}
        hour = {'forecast_at': '2026-11-26T13:00:00+00:00', 'timezone': 'UTC',
                'temporal_status': 'future_forecast',
                'values': {'conditions': {'value': 'scattered clouds', 'unit': None}}}
        wcs = mock.Mock()
        wcs.read.side_effect = [{'ok': True, 'observations': [current, uv], 'sources': [{'status': 'ready'}]},
                                {'ok': True, 'observations': [hour], 'coverage': {'total': 1}}]
        wcs.component_health.return_value = {'status': 'available', 'sources': [{'status': 'ready'}]}
        dis = mock.Mock()
        dis.read.return_value = {'ok': True, 'devices': [
            {'name': 'Coffee plug', 'adapter': 'kasa', 'health': {'status': 'reachable'}},
            {'name': 'Plant waterer', 'adapter': 'pump_mqtt', 'health': {'status': 'unreachable'}},
            {'name': 'Printer', 'adapter': 'inventory', 'health': {'status': 'not_integrated'}}],
            'coverage': {'total': 3}}
        dis.component_health.return_value = {'status': 'available'}
        ltms = mock.Mock()
        ltms.component_health.return_value = {'status': 'degraded'}
        result = project(wcs, dis, ltms, now=now)
        self.assertEqual(result['weather']['temperature']['value'], 44)
        self.assertEqual(result['weather']['uv_index']['value'], 3.5)
        self.assertEqual(result['weather']['forecast']['starts_at'], hour['forecast_at'])
        self.assertEqual(result['dynamos']['iot']['subtext'], 'ERR: Plant waterer')
        self.assertEqual(result['dynamos']['awareness']['subtext'], 'ERR: LTMS')


if __name__ == '__main__':
    unittest.main()
