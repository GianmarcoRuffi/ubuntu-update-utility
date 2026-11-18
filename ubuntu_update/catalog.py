"""Built-in adapters. Discovery and user configuration are not limited to these."""
CATALOG = {
    'Postman': {'format': 'archive', 'entrypoint': 'Postman', 'homepage': 'https://www.postman.com/downloads/'},
    'JMeter': {'format': 'archive', 'entrypoint': 'bin/jmeter', 'homepage': 'https://jmeter.apache.org/download_jmeter.cgi'},
    'Audacity standalone': {'format': 'archive', 'entrypoint': 'AppRun', 'homepage': 'https://github.com/audacity/audacity'},
    'Forge': {'format': 'archive', 'entrypoint': 'forge-adventure.sh', 'homepage': 'https://github.com/Card-Forge/forge'},
    'docker-desktop': {'format': 'deb'},
    'discord': {'format': 'deb'},
    'dbeaver-ce': {'format': 'deb'},
    'github-desktop': {'format': 'deb'},
    'teams-for-linux': {'format': 'deb'},
}
ARCHIVES = frozenset(name for name, spec in CATALOG.items() if spec['format'] == 'archive')
DEBS = frozenset(name for name, spec in CATALOG.items() if spec['format'] == 'deb')
