"""Read-only device tools, backed by the one DIS owner in the main process."""

import asyncio
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from butler.dis import client
from butler.dis.models import ReadResult


def register(server: FastMCP) -> None:
    @server.tool()
    async def list_device_information(
        offset: Annotated[int, Field(ge=0, le=64)] = 0,
        limit: Annotated[int, Field(ge=1, le=8)] = 8,
    ) -> ReadResult:
        """Read configured DIS devices and latest observed power/communication health.
        Read-only, cached: performs no physical command. Results include as-of,
        per-property age/current/stale/unknown, evidence and explicit pagination.
        Includes Kasa lights/plugs, passive waterer telemetry and explicitly
        not_integrated inventory records. A coffee plug
        cannot report brewing and relay power does not prove illumination.
        Unavailable is a failure, not an empty/healthy household."""
        return await asyncio.to_thread(client.read_information, offset=offset, limit=limit)

    @server.tool()
    async def get_device_information(
        device_id: Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9_.-]{0,63}$')],
        refresh: bool = False,
    ) -> ReadResult:
        """Read one DIS device by exact configured ID. Use refresh=true for an
        immediate Kasa read-only check (bounded five-second wait). Passive MQTT
        devices cannot be queried; inventory entries have no live interface.
        Refresh completion means a read attempt finished, not necessarily success;
        inspect health, error and property status. Timed-out refreshes may still
        complete in the background. Unknown IDs return not_found; offline state
        preserves the last observation as stale. Never controls the device."""
        return await asyncio.to_thread(client.read_information, device_id=device_id, refresh=refresh)
