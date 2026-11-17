"""Upgrade an already installed package from a user-selected DEB snapshot."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
try:
    from .packages import installed
    from .sources import newer
    from .runtime import Cancelled
except ImportError:
    from packages import installed
    from sources import newer
    from runtime import Cancelled


def apply(session,request,caller_uid):
    if not isinstance(request,dict) or not {'package','path'}<=set(request) or set(request)-{'package','path','sha256','version'}: raise ValueError('Richiesta non valida')
    if any(not isinstance(value,str) for value in request.values()):raise ValueError('Valori della richiesta non validi')
    package,path=request['package'],request['path']
    if not isinstance(package,str) or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+',package): raise ValueError('Nome pacchetto non valido')
    if not isinstance(path,str) or not Path(path).is_absolute(): raise ValueError('Percorso non valido')
    current=installed(package)
    if current is None: raise ValueError('Il pacchetto selezionato non è installato')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=caller_uid or info.st_size>2*1024**3:
            raise ValueError('Selezionare un file DEB normale appartenente al proprio utente')
        with tempfile.TemporaryDirectory(prefix='ubuntu-update-deb-',dir='/var/tmp') as directory:
            target=Path(directory)/'selected.deb'
            if shutil.disk_usage(directory).free<info.st_size+128*1024**2:raise OSError('Spazio insufficiente per preparare il DEB')
            with target.open('xb') as destination:
                total=0
                while chunk:=source.read(1024**2):
                    total+=len(chunk)
                    if total>2*1024**3:raise ValueError('Il file DEB è troppo grande')
                    destination.write(chunk)
            if request.get('sha256'):
                try:
                    from .sources import verify
                except ImportError:
                    from sources import verify
                verify(target,request['sha256'])
            fields=subprocess.check_output(['/usr/bin/dpkg-deb','-f',str(target),'Package','Version','Architecture'],text=True)
            data=dict(line.split(': ',1) for line in fields.splitlines())
            arch=subprocess.check_output(['/usr/bin/dpkg','--print-architecture'],text=True).strip()
            if data.get('Package')!=package or data.get('Architecture') not in (arch,'all'): raise ValueError('Prodotto o architettura del DEB non corrispondenti')
            expected=request.get('version','')
            actual=data.get('Version','').split(':')[-1]
            if expected and actual!=expected and not actual.startswith(expected+'-') and not actual.startswith(expected+'+'):
                raise ValueError('Versione del DEB diversa da quella richiesta')
            if not newer(data['Version'],current): raise ValueError('Il DEB non contiene una versione più recente')
            base=['/usr/bin/apt-get','-o','DPkg::Lock::Timeout=60','--no-remove']
            simulation=subprocess.run(base+['-s','install',str(target)],capture_output=True,text=True,env=dict(os.environ,LC_ALL='C'))
            if simulation.returncode or re.search(r'^(Remv|Purg) ',simulation.stdout,re.M): raise ValueError('Dipendenze da verificare manualmente: '+simulation.stdout+simulation.stderr)
            if not session.confirm('Installare '+package+' '+data['Version']+'?',f'Versione attuale: {current}\nFile selezionato: {path}\n'+simulation.stdout):
                session.result(package,'saltato');return False
            session.command(base+['-y','-o','Dpkg::Options::=--force-confold','install',str(target)])
            if installed(package)!=data['Version']: raise RuntimeError('Verifica della versione installata fallita')
            session.result(package,'aggiornato',data['Version']);return True


def main(session):
    if os.geteuid()!=0 or not os.environ.get('PKEXEC_UID','').isdigit(): return 1
    import fcntl
    with open('/run/ubuntu-update-utility.lock','w') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            line=sys.stdin.readline(65537)
            if len(line)>65536: raise ValueError('Richiesta troppo grande')
            return 0 if apply(session,json.loads(line),int(os.environ['PKEXEC_UID'])) else 1
        except Cancelled:
            session.result('Installazione DEB','saltato','Operazione annullata.');return 130
        except Exception as error:
            session.result('Installazione DEB','errore',str(error));return 1
