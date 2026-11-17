"""Selection identifiers are data; workers reconstruct operations from catalogues."""
import json
import re
import sys

ARCHIVES = {'Postman', 'JMeter', 'Audacity standalone', 'Forge'}
DEBS = {'docker-desktop', 'dbeaver-ce', 'github-desktop', 'teams-for-linux'}


def read_selection(stream=None):
    line = (stream or sys.stdin).readline(65537)
    if len(line) > 65536:
        raise ValueError('Selezione troppo grande')
    data = json.loads(line)
    if not isinstance(data, dict) or set(data) != {'selected'} or not isinstance(data['selected'], list):
        raise ValueError('Selezione non valida')
    selected = set()
    for value in data['selected']:
        if not isinstance(value, str):
            raise ValueError('Identificatore non valido')
        prefix, separator, name = value.partition(':')
        valid = separator and (
            prefix == 'archive' and name in ARCHIVES or
            prefix == 'deb' and name in DEBS or
            prefix == 'snap' and re.fullmatch(r'[a-z0-9][a-z0-9-]*', name)
        )
        if not valid:
            raise ValueError('Applicazione non riconosciuta')
        selected.add(value)
    return selected
