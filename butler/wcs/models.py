"""Bounded observation contracts; receipt and real-world times stay separate."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import math
import re
import time
from typing import Literal, NotRequired, TypedDict

ID = re.compile(r'[a-z0-9][a-z0-9_.-]{0,63}\Z')


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds') if value is not None else None


class Measurement(TypedDict):
    value: float | str
    unit: str | None


class ObservationView(TypedDict):
    observation_id: str
    category: str
    subject: str
    source: str
    kind: Literal['observation', 'forecast']
    observed_at: str | None
    received_at: str
    age_seconds: float | None
    valid_from: str | None
    valid_until: str | None
    timezone: str
    values: dict[str, Measurement]
    temporal_status: Literal['observed', 'within_forecast_interval', 'outside_forecast_interval', 'future_forecast']
    resolution: Literal['point', 'daily', 'hourly']
    forecast_at: NotRequired[str]
    last_reported_values: NotRequired[dict[str, Measurement]]


class SourceView(TypedDict):
    category: str
    status: Literal['ready', 'partial', 'error', 'unknown', 'not_configured']
    last_attempt_at: str | None
    last_success_at: str | None
    next_poll_at: str | None
    poll_seconds: int
    errors: list[str]


class Coverage(TypedDict):
    total: int
    shown: int
    omitted_count: int
    next_offset: int | None


class ForecastWindow(TypedDict):
    requested_from: str
    requested_until: str
    available_from: str | None
    available_until: str | None


class ReadResult(TypedDict):
    schema_version: Literal[1]
    ok: bool
    status: Literal['available', 'unavailable', 'not_found']
    as_of: str
    error: str | None
    sources: list[SourceView]
    observations: list[ObservationView]
    coverage: Coverage
    forecast_window: NotRequired[ForecastWindow]


def unavailable(code, status='unavailable') -> ReadResult:
    return dict(schema_version=1, ok=False, status=status, as_of=timestamp(time.time()), error=code,
                sources=[], observations=[], coverage=dict(total=0, shown=0, omitted_count=0, next_offset=None))


@dataclass(frozen=True)
class Observation:
    observation_id: str
    category: str
    subject: str
    source: str
    kind: Literal['observation', 'forecast']
    observed_at: float | None
    received_at: float
    valid_from: float | None
    valid_until: float | None
    timezone: str
    values: dict[str, Measurement]
    resolution: Literal['point', 'daily', 'hourly'] = 'point'

    def __post_init__(self):
        if not all(ID.fullmatch(v) for v in (self.category, self.source)):
            raise ValueError('invalid source identity')
        if self.kind not in ('observation', 'forecast') or not 1 <= len(self.observation_id) <= 64:
            raise ValueError('invalid observation identity')
        for text, limit in ((self.subject, 160), (self.timezone, 80)):
            if not text or len(text) > limit or not text.isprintable():
                raise ValueError('invalid text')
        for value in (self.observed_at, self.received_at, self.valid_from, self.valid_until):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 253402300799):
                raise ValueError('invalid time')
        if self.received_at is None or (self.observed_at is not None and self.observed_at > self.received_at + 300):
            raise ValueError('invalid observation time')
        if self.kind == 'forecast' and (self.valid_from is None or self.valid_until is None or self.valid_until <= self.valid_from):
            raise ValueError('forecast needs a valid interval')
        if self.resolution not in ('point', 'daily', 'hourly'):
            raise ValueError('invalid time resolution')
        if self.resolution == 'hourly' and (self.kind != 'forecast' or self.valid_until-self.valid_from != 3600):
            raise ValueError('invalid hourly period')
        if not 1 <= len(self.values) <= 16:
            raise ValueError('invalid measurement count')
        for key, measurement in self.values.items():
            if not ID.fullmatch(key) or set(measurement) != {'value', 'unit'}:
                raise ValueError('invalid measurement')
            value, unit = measurement['value'], measurement['unit']
            if isinstance(value, str):
                if not value or len(value) > 160 or not value.isprintable():
                    raise ValueError('invalid measurement text')
            elif type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e9:
                raise ValueError('invalid measurement number')
            if unit is not None and (not isinstance(unit, str) or len(unit) > 16 or not unit.isprintable()):
                raise ValueError('invalid unit')

    def view(self, now):
        result = asdict(self)
        for key in ('observed_at', 'received_at', 'valid_from', 'valid_until'):
            result[key] = timestamp(result[key])
        result['age_seconds'] = round(max(0, now-self.observed_at), 1) if self.observed_at else None
        result['temporal_status'] = 'observed'
        if self.kind == 'forecast':
            try:
                zone = ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                try:
                    zone = datetime.fromisoformat('2000-01-01T00:00:00'+self.timezone.removeprefix('UTC')).tzinfo or timezone.utc
                except ValueError:
                    zone = timezone.utc
            result['forecast_at'] = datetime.fromtimestamp(self.valid_from, zone).isoformat(timespec='seconds')
            applicable = (now < self.valid_until if self.resolution == 'hourly'
                          else self.valid_from <= now < self.valid_until)
            result['temporal_status'] = 'within_forecast_interval' if applicable else 'outside_forecast_interval'
            if applicable and self.valid_from > now:
                result['temporal_status'] = 'future_forecast'
            if not applicable:
                result['last_reported_values'] = result['values']
                result['values'] = {}
        return result


@dataclass(frozen=True)
class Batch:
    observations: tuple[Observation, ...]
    errors: tuple[str, ...] = ()
    hourly: tuple[Observation, ...] | None = None

    def __post_init__(self):
        if len(self.observations) > 8 or len({(o.subject, o.kind) for o in self.observations}) != len(self.observations):
            raise ValueError('invalid batch')
        if self.hourly is not None:
            if len(self.hourly) > 48 or len({o.valid_from for o in self.hourly}) != len(self.hourly):
                raise ValueError('invalid hourly batch')
            if any(o.resolution != 'hourly' for o in self.hourly):
                raise ValueError('invalid hourly resolution')
        if len(self.errors) > 4 or any(not ID.fullmatch(e) for e in self.errors):
            raise ValueError('invalid error codes')
