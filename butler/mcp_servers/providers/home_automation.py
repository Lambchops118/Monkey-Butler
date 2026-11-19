from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from butler.services import home_automation as actions


def register(server: FastMCP) -> None:
    """Register the existing home automation tools on a FastMCP server."""

    @server.tool()
    def get_current_datetime() -> str:
        """Get the current local date, time, year, and timezone for Butler."""
        return actions.get_current_datetime()

    @server.tool()
    def get_current_weather(location: str = "") -> str:
        """Get the current weather, temperature, humidity, UV index, and related details.

        Leave location blank to use the configured home location. Only pass a
        location when the user explicitly names a different city, zip code, or
        place.
        """
        return actions.get_current_weather(location)
