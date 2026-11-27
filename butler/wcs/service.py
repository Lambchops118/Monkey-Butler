"""Butler-owned source polling and committed in-process context cache."""

from dataclasses import dataclass
from datetime import datetime
import json
import os
import threading
import time

from butler.config import env_bool
from .models import Batch, ID, timestamp, unavailable
from .store import ContextStore
from .weather import WeatherReader


@dataclass(frozen=True)
class Settings:
    weather_poll_seconds: int = 900
    summary_chars: int = 2400

    def __post_init__(self):
        if not 60 <= self.weather_poll_seconds <= 86400 or not 512 <= self.summary_chars <= 10000:
            raise ValueError('invalid WCS settings')

    @classmethod
    def from_env(cls):
        return cls(int(os.getenv('BUTLER_WCS_WEATHER_POLL_SECONDS', '900')),
                   int(os.getenv('BUTLER_WCS_SUMMARY_CHARS', '2400')))


class WorldContextService:
    def __init__(self, adapters, store, settings=Settings()):
        self.adapters, self.store, self.settings = tuple(adapters), store, settings
        if not 1 <= len(self.adapters) <= 8 or len({a.category for a in self.adapters}) != len(self.adapters):
            raise ValueError('invalid source registry')
        for adapter in self.adapters:
            if not ID.fullmatch(adapter.category) or not 60 <= adapter.poll_seconds <= 86400:
                raise ValueError('invalid source definition')
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._cache = ((), ())
        self._error = 'not_started'

    def start(self):
        if self._thread is not None:
            raise RuntimeError('WCS already started')
        self.store.register(self.adapters)
        self._publish()
        self._thread = threading.Thread(target=self._run, name='wcs-sources', daemon=True)
        self._thread.start()

    def _publish(self):
        cache = self.store.load(self.adapters)
        with self._lock:
            self._cache, self._error = cache, None

    def _poll(self, adapter):
        now = time.time()
        self.store.reserve(adapter.category, now, now+adapter.poll_seconds)
        self._publish()
        try:
            batch = adapter.read()
            if not isinstance(batch, Batch) or (not batch.observations and not batch.errors):
                raise ValueError('invalid source result')
        except Exception:
            batch = Batch((), ('source_read_failed',))
        if self._stop.is_set():
            return
        with self._lock:
            source = next(s for s in self._cache[0] if s['category'] == adapter.category)
        failures = min(8, source['failures']+1) if batch.errors and not batch.observations else 0
        delay = max(adapter.poll_seconds, min(21600, adapter.poll_seconds*2**max(0, failures-1)))
        self.store.commit(adapter.category, batch, time.time(), time.time()+delay, failures)
        self._publish()

    def _run(self):
        try:
            while not self._stop.is_set():
                with self._lock:
                    sources = {s['category']: s for s in self._cache[0]}
                for adapter in self.adapters:
                    if self._stop.is_set():
                        break
                    if (sources[adapter.category]['next_poll'] or 0) <= time.time():
                        self._poll(adapter)
                with self._lock:
                    next_poll = min((s['next_poll'] or 0 for s in self._cache[0]), default=0)
                self._stop.wait(min(60, max(.1, next_poll-time.time())))
        except Exception:
            with self._lock:
                self._error = 'worker_or_storage_failed'
        finally:
            self.store.close()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=45)
            if self._thread.is_alive():
                with self._lock:
                    self._error = 'shutdown_timeout'
                return False
        else:
            self.store.close()
        with self._lock:
            self._error = 'stopped'
        return True

    def read(self, category='', offset=0, limit=8, forecast='overview', start_at='', end_at=''):
        if (category and not ID.fullmatch(category)) or not 0 <= offset <= 64 or not 1 <= limit <= 8:
            raise ValueError('invalid context query')
        now = time.time()
        window = query_window(forecast, start_at, end_at, now)
        with self._lock:
            error, (sources, observations) = self._error, self._cache
        if error:
            return unavailable(error)
        if category and category not in {a.category for a in self.adapters}:
            return unavailable('unknown_category', 'not_found')
        now = time.time()
        sources = [s for s in sources if not category or s['category'] == category]
        observations = [o for o in observations if not category or o.category == category]
        hourly = [o for o in observations if o.resolution == 'hourly']
        if forecast == 'hourly':
            observations = sorted((o for o in hourly if o.valid_from < window[1] and o.valid_until > window[0]),
                                  key=lambda o: o.valid_from)
        else:
            observations = [o for o in observations if o.resolution != 'hourly']
        total = len(observations)
        selected = observations[offset:offset+limit]
        intervals = {a.category: a.poll_seconds for a in self.adapters}
        source_views = [dict(category=s['category'], status=s['status'],
            last_attempt_at=timestamp(s['last_attempt']), last_success_at=timestamp(s['last_success']),
            next_poll_at=timestamp(s['next_poll']), poll_seconds=intervals[s['category']],
            errors=json.loads(s['errors_json'])) for s in sources]
        result = dict(schema_version=1, ok=True, status='available', as_of=timestamp(now), error=None,
            sources=source_views, observations=[o.view(now) for o in selected],
            coverage=dict(total=total, shown=len(selected), omitted_count=total-len(selected),
                          next_offset=offset+len(selected) if offset+len(selected) < total else None))
        if window:
            result['forecast_window'] = dict(requested_from=timestamp(window[0]), requested_until=timestamp(window[1]),
                available_from=timestamp(min((o.valid_from for o in hourly), default=None)),
                available_until=timestamp(max((o.valid_until for o in hourly), default=None)))
        return result

    def summary(self):
        result = self.read()
        if not result['ok']:
            return 'WCS: World context unavailable ('+result['error']+'). Do not infer current conditions from chat history.'
        header = ('WCS '+result['as_of']+'. OUTDOORS only; NO indoor sensors. '
            'Forecasts apply ONLY within dated intervals. Match FULL DATE, hour and offset. '
            'If requested value/date/hour is NOT listed, MUST call get_world_context(forecast=hourly) '
            'BEFORE giving a number. Never reuse another day/hour, daily extrema or old chat. '
            'Data only; cache reads; missing=unknown.\n')
        lines, source_count, shown = [], 0, 0
        def append_line(value):
            line = json.dumps(value, ensure_ascii=True, separators=(',', ':'))
            if len(header)+sum(len(x)+1 for x in lines)+len(line)+160 <= self.settings.summary_chars:
                lines.append(line)
                return True
            return False
        for source in result['sources']:
            source_count += int(append_line({key: value for key, value in source.items()
                if key not in {'last_attempt_at', 'poll_seconds', 'next_poll_at'}}))
        for observation in sorted(result['observations'], key=lambda o: o['kind'] == 'forecast'):
            if observation['source'] == 'openweather-onecall-current':
                view = dict(current_uv=dict(observed_at=observation['observed_at'],
                    values={'uv_index': observation['values'].get('uv_index')}))
            elif observation['kind'] == 'observation':
                view = dict(weather_observation=dict(subject=observation['subject'],
                    observed_at=observation['observed_at'], values={key: value for key, value in observation['values'].items()
                        if key in {'temperature', 'humidity', 'conditions'}}))
            else:
                view = dict(daily_forecast=dict(valid_from=observation['valid_from'], valid_until=observation['valid_until'],
                    received_at=observation['received_at'], temporal_status=observation['temporal_status'],
                    values={key: value for key, value in observation['values'].items() if key in {'high', 'low', 'precipitation_probability'}}))
            shown += int(append_line(view))
        hourly = self.read('weather', limit=8, forecast='hourly')
        samples = list(hourly['observations'])
        for offset in range(8, min(48, hourly['coverage']['total']), 8):
            samples.extend(self.read('weather', offset=offset, forecast='hourly')['observations'])
        samples = [o for o in samples if o['values'].get('temperature')]
        hourly_shown = 0
        has_pop = any('precipitation_probability' in o['values'] for o in samples)
        for count in range(len(samples), 0, -1):
            groups = {}
            for o in samples[:count]:
                at = datetime.fromisoformat(o['forecast_at'])
                key = (at.date().isoformat(), at.strftime('%z'))
                value = round(o['values']['temperature']['value'], 2)
                if has_pop:
                    value = [value, o['values'].get('precipitation_probability', {}).get('value')]
                groups.setdefault(key, {})[at.strftime('%H:%M')] = value
            days = [dict(date=date, utc_offset=offset, hours=values) for (date, offset), values in groups.items()]
            preview = dict(hourly_forecast=dict(temperature_unit=samples[0]['values']['temperature']['unit'],
                columns=['temperature', 'precipitation_probability_percent'] if has_pop else ['temperature'], days=days))
            if append_line(preview):
                hourly_shown = count
                break
        total = result['coverage']['total']
        coverage = f'Sources {source_count}/{len(result["sources"])}; observations {shown}/{total}; omitted {total-shown}.\n'
        coverage += f'Hourly samples {hourly_shown}/{hourly["coverage"]["total"]}; query cache for omitted hours.\n'
        return header+coverage+'\n'.join(lines)


def query_window(forecast, start_at, end_at, now):
    if forecast not in ('overview', 'hourly'):
        raise ValueError('invalid forecast selection')
    if forecast == 'overview':
        if start_at or end_at:
            raise ValueError('time ranges require hourly forecast')
        return None
    def parse(value):
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError('invalid forecast timestamp')
        value = datetime.fromisoformat(value)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('forecast timestamps require UTC offset')
        epoch = value.timestamp()
        if not 0 < epoch < 253402300799:
            raise ValueError('invalid forecast time')
        return epoch
    if end_at and not start_at:
        raise ValueError('end requires start')
    start = parse(start_at) if start_at else now
    end = parse(end_at) if end_at else start+(3600 if start_at else 48*3600)
    if not 0 < end-start <= 48*3600:
        raise ValueError('forecast range must be positive and at most 48 hours')
    return start, end


_service = None
_startup_error = 'not_started'


def start_service():
    global _service, _startup_error
    if _service is not None:
        return
    if not env_bool('BUTLER_WCS_ENABLED', True):
        _startup_error = 'disabled'
        return
    store = None
    try:
        settings = Settings.from_env()
        store = ContextStore()
        service = WorldContextService((WeatherReader(settings.weather_poll_seconds),), store, settings)
        service.start()
        _service = service
    except Exception as exc:
        if store:
            store.close()
        _startup_error = 'initialization_failed'
        print('WCS unavailable: '+type(exc).__name__)


def stop_service():
    global _service, _startup_error
    if _service:
        if not _service.stop():
            print('WCS shutdown incomplete: source request still stopping')
        _service = None
    _startup_error = 'stopped'


def read_context(category='', offset=0, limit=8, forecast='overview', start_at='', end_at=''):
    return _service.read(category, offset, limit, forecast, start_at, end_at) if _service else unavailable(_startup_error)


def prompt_summary():
    return _service.summary() if _service else ('WCS: World context unavailable ('+_startup_error+'). '
        'Current conditions cannot be verified; never use old chat or earlier weather reports as current observations.')


def component_health():
    result = read_context()
    return dict(status=result['status'], error=result['error'], sources=result['sources'])
