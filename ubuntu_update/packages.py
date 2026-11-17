"""Standalone DEB updates using an immutable source catalogue."""
from pathlib import Path
import re
import subprocess
import tempfile
try:
    from . import sources
except ImportError:
    import sources

try:
    from .catalog import DEBS
except ImportError:
    from catalog import DEBS
PACKAGES = tuple(sorted(DEBS))


def installed(package):
    p = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${db:Status-Abbrev}\t${Version}', package], capture_output=True, text=True)
    return p.stdout.split('\t',1)[1] if p.returncode == 0 and p.stdout.startswith('ii ') else None


def repository_managed(package):
    result = subprocess.run(['/usr/bin/apt-cache', 'policy', package], capture_output=True, text=True)
    return bool(re.search(r'^\s+\d+ https?://', result.stdout, re.M))


def app_running(package):
    needles = {'docker-desktop': ('/opt/docker-desktop/',), 'dbeaver-ce': ('/usr/share/dbeaver/', '/usr/share/dbeaver-ce/'),
               'github-desktop': ('/usr/lib/github-desktop/', '/opt/github-desktop/'), 'teams-for-linux': ('/opt/teams-for-linux/',)}[package]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            executable = str((proc/'exe').resolve(strict=True))
            if any(executable.startswith(n) for n in needles): return True
        except (OSError, RuntimeError): continue
    return False


def update_package(s, package, apply):
    version = installed(package)
    if version is None:
        s.result(package,'saltato','Applicazione non installata.'); return
    if repository_managed(package):
        s.result(package, 'gestito da APT', version); return
    arch = subprocess.check_output(['/usr/bin/dpkg','--print-architecture'], text=True).strip()
    source = sources.package_source(package, arch)
    if source['version'] and not sources.newer(source['version'], version):
        s.result(package, 'nessun aggiornamento', version); return
    if not apply:
        s.candidate('deb:'+package,package,version,source['version'],'Standalone')
        s.result(package, 'aggiornamento disponibile' if source['version'] else 'verifica pacchetto richiesta',
                 f"{version} → {source['version'] or 'ultima versione del produttore'}\n{source['page']}"); return
    if app_running(package):
        s.result(package, 'intervento richiesto', 'Chiudere l’applicazione prima di aggiornarla.'); return
    with tempfile.TemporaryDirectory(prefix='ubuntu-update-deb-', dir='/var/tmp') as directory:
        target = Path(directory)/source['name']
        sources.fetch(source['url'], target, limit=2*1024**3)
        if source['sha256']: sources.verify(target, source['sha256'])
        fields = subprocess.check_output(['/usr/bin/dpkg-deb','-f',str(target),'Package','Version','Architecture'], text=True)
        metadata = dict(line.split(': ',1) for line in fields.splitlines())
        if metadata.get('Package') != package or metadata.get('Architecture') not in (arch,'all'):
            raise ValueError('Identità o architettura del pacchetto errata')
        candidate = metadata['Version']
        if not sources.newer(candidate, version):
            s.result(package, 'nessun aggiornamento', version); return
        if source['version'] and source['version'] not in candidate:
            raise ValueError('Versione pacchetto diversa da quella pubblicata')
        # Prevent dependency removals and any implicit upgrade of the VPN.
        args = ['/usr/bin/apt-get','-o','DPkg::Lock::Timeout=60','--no-remove']
        plan = subprocess.run(args+['-s','install',str(target)], capture_output=True,text=True)
        if plan.returncode or re.search(r'^(?:Remv|Purg) ',plan.stdout,re.M):
            s.result(package,'intervento richiesto',plan.stdout+plan.stderr); return
        if not source['sha256'] and not s.confirm('Installare '+package+'?',
                f"{version} → {candidate}\n{source['page']}\nIl produttore non fornisce un digest nell’indice usato. Download HTTPS verificato; confermare la fonte."):
            s.result(package,'saltato'); return
        s.command(args+['-y','-o','Dpkg::Options::=--force-confold','install',str(target)])
        if installed(package) != candidate: raise RuntimeError('Verifica della versione installata fallita')
        s.emit('completed',id='deb:'+package)
        s.result(package,'aggiornato',candidate)
