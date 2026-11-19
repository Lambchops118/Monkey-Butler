"""Read the main process cache; MCP children never poll or open WCS storage."""

import http.client
import json
import os
from urllib.parse import urlencode
from pydantic import TypeAdapter
from .models import ReadResult, unavailable

_RESULT = TypeAdapter(ReadResult)


def read_information(category='', offset=0, limit=8, forecast='overview', start_at='', end_at='') -> ReadResult:
    try:
        port = int(os.getenv('TEXT_AGENT_PORT', '8420'))
        if not 1 <= port <= 65535:
            raise ValueError('invalid port')
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
        try:
            headers = {}
            token = os.getenv('TEXT_AGENT_API_TOKEN', '').strip()
            if token:
                headers['Authorization'] = 'Bearer '+token
            query = urlencode(dict(category=category, offset=offset, limit=limit, forecast=forecast, start_at=start_at, end_at=end_at))
            connection.request('GET', '/wcs/context?'+query, headers=headers)
            response = connection.getresponse()
            data = response.read(32769)
            if response.status != 200 or len(data) > 32768:
                return unavailable('main_service_read_failed')
            return _RESULT.validate_python(json.loads(data), strict=True)
        finally:
            connection.close()
    except (OSError, ValueError, http.client.HTTPException, RecursionError):
        return unavailable('main_service_unavailable')
