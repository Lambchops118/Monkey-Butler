"""Typed read tools for the existing main process's WCS cache."""

import asyncio
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from butler.wcs import client
from butler.wcs.models import ReadResult


def register(server: FastMCP):
    @server.tool()
    async def get_world_context(
        category: Annotated[str, Field(pattern=r'^$|^[a-z0-9][a-z0-9_.-]{0,63}$')] = '',
        offset: Annotated[int, Field(ge=0, le=64)] = 0,
        limit: Annotated[int, Field(ge=1, le=8)] = 8,
        forecast: Literal['overview', 'hourly'] = 'overview',
        start_at: Annotated[str, Field(max_length=40)] = '',
        end_at: Annotated[str, Field(max_length=40)] = '',
    ) -> ReadResult:
        """Read cached timestamped World Context observations. Only local outdoor
        weather is currently integrated: temperature, humidity and daily forecast
        when available. Set forecast=hourly for cached hourly samples (up to 48h),
        including temperature, conditions and precipitation_probability percent.
        start_at/end_at must be ISO dates/times WITH timezone offset, e.g.
        2026-11-19T08:00:00-05:00. Returns hourly buckets overlapping [start,end), max range 48h.
        Start alone selects one hour; no range selects upcoming 48h. Use pagination.
        Check forecast_window/coverage: no sample means unavailable, never infer
        a specific-hour temperature from daily high/low. Hour samples are predictions
        at forecast_at (timestamp with UTC offset) / valid_from (UTC); no
        interpolation. Match the FULL DATE, hour and offset. Never substitute an adjacent hour
        or the same clock hour on a different date. Retrieve any requested date/hour
        absent from the automatic preview before giving a numeric answer. Overview returns current/daily only.
        Empty category reads all; weather selects weather.
        Never polls an API, controls a device or schedules notifications. Values
        describe observed_at, not guaranteed conditions now; forecasts apply only
        to their explicit valid interval/timezone. Future hourly values are forecasts,
        not current observations; expired values are historical. Outside a daily interval values is
        empty, with historical numbers in last_reported_values, not today's forecast.
        Check temporal_status, source errors and dates.
        Saved observations may remain available during source failures; ok means
        the cache was read, not that the source or every observation is current.
        Unknown categories return not_found; pagination reports omitted records."""
        return await asyncio.to_thread(client.read_information, category, offset, limit, forecast, start_at, end_at)
