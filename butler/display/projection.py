"""Bounded read-only projection of committed service caches for InfoPanel."""

from datetime import datetime


def _value(observation, key):
    return (observation.get('values') or {}).get(key, {}).get('value')


def _member_state(status):
    if status in ('available', 'reachable', 'ready'):
        return 'online'
    if status in ('unavailable', 'unreachable', 'error', 'degraded', 'partial', 'not_configured'):
        return 'error'
    return 'unknown'


def _group(members):
    states = [member['state'] for member in members]
    if 'error' in states:
        state = 'error'
    elif states and all(item == 'online' for item in states):
        state = 'online'
    elif states and all(item == 'offline' for item in states):
        state = 'offline'
    else:
        state = 'unknown'
    errors = [member['name'] for member in members if member['state'] == 'error']
    return {'state': state, 'subtext': 'ERR: ' + ', '.join(errors) if errors else state,
            'members': members}


def project(wcs, dis, ltms, *, now=None):
    """Use service reads only; never poll weather or devices in the request path."""
    now = now or datetime.now().astimezone()
    weather = {'temperature': None, 'conditions': None, 'forecast': None, 'uv_index': None}
    wcs_result = wcs.read('weather', limit=8)
    if wcs_result['ok']:
        observations = wcs_result['observations']
        source_working = any(s['status'] in ('ready', 'partial') for s in wcs_result.get('sources', []))
        current = next((o for o in observations if o['source'] == 'openweather-current'), None) if source_working else None
        uv = next((o for o in observations if o['source'] == 'openweather-onecall-current'), None) if source_working else None
        # A partial poll may leave an older One Call result beside fresh current
        # weather. Do not label that retained UV as immediate.
        if current and uv and datetime.fromisoformat(uv['received_at']) < datetime.fromisoformat(current['received_at']):
            uv = None
        if current:
            temperature = (current.get('values') or {}).get('temperature')
            if temperature:
                weather['temperature'] = {'value': temperature['value'], 'unit': temperature['unit'],
                                          'observed_at': current['observed_at']}
            conditions = _value(current, 'conditions')
            if isinstance(conditions, str):
                weather['conditions'] = ' '.join(conditions.split()[:2])
        if uv:
            value = _value(uv, 'uv_index')
            if value is not None:
                weather['uv_index'] = {'value': value, 'observed_at': uv['observed_at']}
        hourly = wcs.read('weather', limit=8, forecast='hourly') if source_working else {'ok': False}
        samples = list(hourly['observations']) if hourly['ok'] else []
        for offset in range(8, min(hourly['coverage']['total'], 48), 8) if hourly['ok'] else ():
            samples.extend(wcs.read('weather', offset=offset, limit=8, forecast='hourly')['observations'])
        candidates = [o for o in samples if o.get('forecast_at') and
                      datetime.fromisoformat(o['forecast_at']).date() ==
                      now.astimezone(datetime.fromisoformat(o['forecast_at']).tzinfo).date() and
                      o.get('temporal_status') in ('within_forecast_interval', 'future_forecast') and
                      isinstance(_value(o, 'conditions'), str)]
        candidates.sort(key=lambda o: o['forecast_at'])
        if candidates:
            baseline = (_value(current, 'conditions') or '').lower() if current else ''
            changed = next((o for o in candidates if _value(o, 'conditions').lower() != baseline), None)
            chosen = changed or candidates[0]
            at = datetime.fromisoformat(chosen['forecast_at'])
            weather['forecast'] = {'conditions': ' '.join(_value(chosen, 'conditions').split()[:2]),
                                   'starts_at': chosen['forecast_at'] if changed else None,
                                   'timezone': chosen['timezone']}

    dis_result = dis.read(limit=8)
    devices = list(dis_result['devices']) if dis_result['ok'] else []
    for offset in range(8, min(dis_result['coverage']['total'], 64), 8) if dis_result['ok'] else ():
        devices.extend(dis.read(offset=offset, limit=8)['devices'])
    integrated = [d for d in devices if d['adapter'] != 'inventory']
    iot_members = [{'name': d['name'], 'state': _member_state(d['health']['status'])}
                   for d in integrated]
    if not dis_result['ok']:
        iot_members = [{'name': 'DIS', 'state': 'error'}]
    wcs_health = wcs.component_health()
    wcs_state = _member_state(wcs_health['status'])
    if wcs_state == 'online' and any(s['status'] in ('error', 'partial', 'not_configured')
                                     for s in wcs_health.get('sources', [])):
        wcs_state = 'error'
    elif wcs_state == 'online' and any(s['status'] == 'unknown' for s in wcs_health.get('sources', [])):
        wcs_state = 'unknown'
    awareness = [
        {'name': 'WCS', 'state': wcs_state},
        {'name': 'DIS', 'state': _member_state(dis.component_health()['status'])},
        {'name': 'LTMS', 'state': _member_state(ltms.component_health()['status'])},
    ]
    return {'schema_version': 1, 'weather': weather,
            'dynamos': {'awareness': _group(awareness), 'iot': _group(iot_members)}}
