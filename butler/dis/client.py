"""MCP child -> existing main HTTP service. No database owner or poller here."""

import http.client
import json
import os
from pydantic import TypeAdapter
from urllib.parse import urlencode

from .models import ReadResult, unavailable

_RESULT = TypeAdapter(ReadResult)


def read_information(device_id: str = '', offset: int = 0, limit: int = 8, refresh: bool = False) -> ReadResult:
    try:
        port = int(os.getenv('TEXT_AGENT_PORT', '8420'))
        if not 1 <= port <= 65535:
            raise ValueError('invalid port')
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=6)
        try:
            headers = {}
            token = os.getenv('TEXT_AGENT_API_TOKEN', '').strip()
            if token:
                headers['Authorization'] = 'Bearer ' + token
            query = urlencode({'device_id': device_id, 'offset': offset, 'limit': limit,
                               'refresh': '1' if refresh else '0'})
            connection.request('GET', '/dis/devices?' + query, headers=headers)
            response = connection.getresponse()
            data = response.read(32769)
            if response.status != 200 or len(data) > 32768:
                return unavailable('main_service_read_failed')
            result = json.loads(data)
            if not isinstance(result, dict) or result.get('schema_version') != 1 or type(result.get('ok')) is not bool:
                return unavailable('invalid_main_response')
            return _RESULT.validate_python(result, strict=True)
        finally:
            connection.close()
    except (OSError, ValueError, http.client.HTTPException):
        return unavailable('main_service_unavailable')
