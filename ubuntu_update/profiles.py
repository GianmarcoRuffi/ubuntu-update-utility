"""User-owned associations for assisted discovery; no executable commands."""
import json
import os
from pathlib import Path
try:
    from .paths import data_home,state_home,config_home,app_roots
except ImportError:
    from paths import data_home,state_home,config_home,app_roots
import tempfile
from urllib.parse import urlsplit


def config_path(home=None):
    base=config_home(home)
    return base/'ubuntu-update-utility/sources.json'


def load(home=None):
    try:
        data=json.loads(config_path(home).read_text())
        return {key:value for key,value in data.items() if isinstance(value,dict) and all(isinstance(v,str) for v in value.values())} if isinstance(data,dict) else {}
    except (OSError,ValueError): return {}


def validate_url(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Usa un indirizzo HTTPS senza credenziali.')
    import ipaddress
    try: ipaddress.ip_address(parsed.hostname)
    except ValueError: pass
    else: raise ValueError('Usa il nome del sito ufficiale, non un indirizzo IP.')
    if parsed.hostname in ('localhost','localhost.localdomain') or '.' not in parsed.hostname:
        raise ValueError('Indirizzo del sito non valido.')
    return url


def deb_url(record):
    if record.get('deb_url'):
        return record['deb_url']
    if record.get('repository') or record.get('manifest'):
        return ''
    homepage = record.get('homepage', '')
    return homepage if urlsplit(homepage).path.lower().endswith('.deb') else ''


def validate(record):
    allowed={'homepage','repository','version','provider','asset','channel','entrypoint','manifest','deb_url','recovery_path','previous_version'}
    if not isinstance(record,dict) or not all(isinstance(v,str) for v in record.values()):raise ValueError('Valori della fonte non validi')
    if set(record)-allowed: raise ValueError('Campo della fonte non consentito')
    for key in ('homepage','manifest','deb_url'):
        if record.get(key): validate_url(record[key])
    if record.get('provider','github') not in ('github','json','appcast'):raise ValueError('Tipo di fonte non supportato')

def save(identifier,record,home=None):
    import re
    if not re.fullmatch(r'install:[0-9a-f]{64}',identifier):raise ValueError('Installazione non valida')
    validate(record)
    data=load(home);data[identifier]=record
    path=config_path(home);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
        json.dump(data,stream,ensure_ascii=False,indent=2);temporary=Path(stream.name)
    temporary.chmod(0o600);temporary.replace(path)
