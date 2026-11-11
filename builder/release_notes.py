"""Reviewed, source-bound text for the existing WhatsApp template; never code."""
import json
import re


def notification_summary(raw, source):
    if not re.fullmatch(r'[a-f0-9]{40}', source):
        raise ValueError('Exact release source required')
    if len(raw.encode('utf-8')) > 262144:
        raise ValueError('Release notes exceed size limit')
    data = json.loads(raw)
    if (not isinstance(data, dict) or set(data) != {'schema', 'application', 'sources'}
            or type(data['schema']) is not int or data['schema'] != 1
            or data['application'] != 'TourMaps GO+' or not isinstance(data['sources'], dict)):
        raise ValueError('Reviewed release notes schema required')
    changes = data['sources'].get(source)
    if not isinstance(changes, list) or not 1 <= len(changes) <= 12:
        raise ValueError('Current source has no reviewed release changes; no new delivery')
    for value in changes:
        if (not isinstance(value, str) or value != value.strip() or not 10 <= len(value) <= 180
                or re.search(r'[\x00-\x1f\x7f]|https?://', value, re.I)
                or re.fullmatch(r'cambios integrados(?: del equipo)?[.!]?', value, re.I)):
            raise ValueError('Concrete single-line release changes required')
    summary = '; '.join(changes)
    if not 20 <= len(summary) <= 700:
        raise ValueError('WhatsApp release summary must fit the existing template')
    return summary
