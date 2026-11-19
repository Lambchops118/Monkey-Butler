"""OpenWeather observations. No model, device commands or automatic retries."""

from datetime import datetime, timedelta, timezone
import json
import math
import os
import time
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from butler.services import home_automation as existing
from .models import Batch, Observation


class WeatherFailure(Exception):
    pass


class WeatherReader:
    category = 'weather'

    def __init__(self, poll_seconds=900, get=None):
        self.poll_seconds = poll_seconds
        self.location = existing._normalize_location_query(os.getenv('BUTLER_WEATHER_LOCATION', ''))
        self.units = os.getenv('BUTLER_WEATHER_UNITS', 'imperial').strip().lower()
        self.key = os.getenv('OPEN_WEATHER_API_KEY', '').strip()
        if self.units not in ('imperial', 'metric', 'standard') or len(self.location) > 160:
            raise ValueError('invalid weather configuration')
        self.identity = {'provider': 'openweather-3', 'location': self.location, 'units': self.units,
                         'collection_version': 2}
        self._coordinates = None
        self._get = get or requests.get

    def _request(self, url, params):
        try:
            with self._get(url, params={**params, 'appid': self.key}, timeout=(3, 6), stream=True) as response:
                if response.status_code in (401, 403):
                    raise WeatherFailure('authorization_failed')
                if response.status_code == 429:
                    raise WeatherFailure('rate_limited')
                if response.status_code >= 400:
                    raise WeatherFailure('provider_error')
                chunks, size = [], 0
                for chunk in response.iter_content(8192):
                    size += len(chunk)
                    if size > 262144:
                        raise WeatherFailure('response_too_large')
                    chunks.append(chunk)
                return json.loads(b''.join(chunks))
        except requests.Timeout:
            raise WeatherFailure('timeout') from None
        except requests.RequestException:
            raise WeatherFailure('network_error') from None
        except (ValueError, RecursionError):
            raise WeatherFailure('invalid_response') from None

    def _resolve(self):
        if self._coordinates is None:
            zip_query = existing._extract_zip_query(self.location)
            if zip_query:
                data = self._request(existing.OPENWEATHER_GEOCODING_ZIP_URL,
                                     {'zip': zip_query['zip']+','+zip_query['country']})
            else:
                data = self._request(existing.OPENWEATHER_GEOCODING_DIRECT_URL,
                    {'q': existing._canonicalize_location_name_query(self.location), 'limit': 1})
                if not isinstance(data, list) or not data:
                    raise WeatherFailure('location_not_found')
                data = data[0]
            lat, lon = number(data['lat'], -90, 90), number(data['lon'], -180, 180)
            self._coordinates = {'lat': lat, 'lon': lon}
        return self._coordinates

    def read(self):
        if not self.key or not self.location:
            return Batch((), ('not_configured',))
        observations, errors, hourly = [], [], None
        try:
            coords = self._resolve()
            current = self._request(existing.OPENWEATHER_CURRENT_URL, {**coords, 'units': self.units})
            received = time.time()
            observed = number(current['dt'], 1, received+300)
            offset = int(number(current.get('timezone', 0), -86400+1, 86400-1))
            zone = timezone(timedelta(seconds=offset))
            zone_name = str(zone)
            temperature_unit = {'imperial': 'F', 'metric': 'C', 'standard': 'K'}[self.units]
            values = {}
            main = current['main']
            add(values, 'temperature', main['temp'], temperature_unit, -200, 1000)
            add(values, 'humidity', main['humidity'], '%', 0, 100)
            for name, field, unit, lower, upper in (
                ('feels_like', 'feels_like', temperature_unit, -200, 1000),
                ('pressure', 'pressure', 'hPa', 0, 2000)):
                if main.get(field) is not None:
                    add(values, name, main[field], unit, lower, upper)
            if current.get('wind', {}).get('speed') is not None:
                add(values, 'wind_speed', current['wind']['speed'], 'mph' if self.units == 'imperial' else 'm/s', 0, 1000)
            if current.get('clouds', {}).get('all') is not None:
                add(values, 'cloud_cover', current['clouds']['all'], '%', 0, 100)
            description = (current.get('weather') or [{}])[0].get('description')
            if description:
                if not isinstance(description, str):
                    raise WeatherFailure('invalid_response')
                values['conditions'] = {'value': description, 'unit': None}
            # Current API min/max are spatial ranges, not today's high/low.
            observations.append(Observation(str(uuid4()), 'weather', self.location, 'openweather-current',
                'observation', observed, received, None, None, zone_name, values))
            try:
                daily = self._request(existing.OPENWEATHER_ONECALL_URL,
                    {**coords, 'units': self.units, 'exclude': 'current,minutely,alerts'})
                received_daily = time.time()
                if isinstance(daily.get('timezone'), str):
                    try:
                        zone = ZoneInfo(daily['timezone'])
                        zone_name = daily['timezone']
                    except ZoneInfoNotFoundError:
                        pass  # explicitly labelled fixed UTC offset remains the fallback
                try:
                    hourly = self._hourly(daily.get('hourly'), received_daily, zone_name, temperature_unit)
                except WeatherFailure as exc:
                    errors.append('hourly_'+str(exc))
                except (KeyError, TypeError, ValueError, OverflowError, OSError):
                    errors.append('hourly_invalid_response')
                today = datetime.fromtimestamp(received_daily, zone).date()
                day = next((d for d in daily.get('daily', [])[:8]
                    if datetime.fromtimestamp(number(d['dt'], 1, received_daily+864000), zone).date() == today), None)
                if day is None:
                    raise WeatherFailure('forecast_unavailable')
                start = datetime.combine(today, datetime.min.time(), tzinfo=zone)
                end = datetime.combine(today+timedelta(days=1), datetime.min.time(), tzinfo=zone)
                forecast = {}
                add(forecast, 'high', day['temp']['max'], temperature_unit, -200, 1000)
                add(forecast, 'low', day['temp']['min'], temperature_unit, -200, 1000)
                if forecast['low']['value'] > forecast['high']['value']:
                    raise WeatherFailure('invalid_response')
                if day.get('pop') is not None:
                    add(forecast, 'precipitation_probability', number(day['pop'], 0, 1)*100, '%', 0, 100)
                if day.get('uvi') is not None:
                    add(forecast, 'uv_index', day['uvi'], None, 0, 100)
                # daily.dt is the target day, not the forecast issue timestamp.
                observations.append(Observation(str(uuid4()), 'weather', self.location, 'openweather-daily',
                    'forecast', None, received_daily, start.timestamp(), end.timestamp(), zone_name, forecast, resolution='daily'))
            except WeatherFailure as exc:
                errors.append('daily_'+str(exc))
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                errors.append('daily_invalid_response')
        except WeatherFailure as exc:
            errors.append(str(exc))
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            errors.append('invalid_response')
        return Batch(tuple(observations), tuple(errors), hourly)

    def _hourly(self, data, received, zone_name, temperature_unit):
        if not isinstance(data, list) or not 1 <= len(data) <= 48:
            raise WeatherFailure('unavailable')
        result, previous = [], None
        for hour in data:
            target = number(hour['dt'], received-7200, received+49*3600)
            if previous is not None and target-previous != 3600:
                raise WeatherFailure('invalid_response')
            previous = target
            values = {}
            add(values, 'temperature', hour['temp'], temperature_unit, -200, 1000)
            if hour.get('pop') is not None:
                add(values, 'precipitation_probability', number(hour['pop'], 0, 1)*100, '%', 0, 100)
            description = (hour.get('weather') or [{}])[0].get('description')
            if description:
                if not isinstance(description, str):
                    raise WeatherFailure('invalid_response')
                values['conditions'] = {'value': description, 'unit': None}
            result.append(Observation(str(uuid4()), 'weather', self.location, 'openweather-hourly',
                'forecast', None, received, target, target+3600, zone_name, values, resolution='hourly'))
        return tuple(result)


def number(value, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise WeatherFailure('invalid_response')
    return value


def add(values, name, value, unit, lower, upper):
    values[name] = {'value': number(value, lower, upper), 'unit': unit}
