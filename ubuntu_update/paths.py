"""XDG locations with defaults and compatibility for pre-XDG utility data."""
import os
from pathlib import Path


def location(variable,fallback):
    value=os.environ.get(variable,'')
    return Path(value) if value and Path(value).is_absolute() else Path(fallback)


def data_home(home=None):return location('XDG_DATA_HOME',Path(home or Path.home())/'.local/share')
def state_home(home=None):return location('XDG_STATE_HOME',Path(home or Path.home())/'.local/state')
def cache_home(home=None):return location('XDG_CACHE_HOME',Path(home or Path.home())/'.cache')
def config_home(home=None):return location('XDG_CONFIG_HOME',Path(home or Path.home())/'.config')

def app_roots(home=None):
    home=Path(home or Path.home())
    values=[data_home(home)/'ubuntu-update-utility/apps',home/'.local/share/ubuntu-update-utility/apps']
    return list(dict.fromkeys(values))
