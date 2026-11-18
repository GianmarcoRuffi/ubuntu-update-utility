#!/usr/bin/python3
"""Unprivileged phase: per-user Flatpak, archives, inventory and recovery."""
import fcntl
import json
import shlex
import os
from pathlib import Path
try:
    from .paths import data_home,state_home,config_home,cache_home,app_roots
except ImportError:
    from paths import data_home,state_home,config_home,cache_home,app_roots
import re
import shutil
import subprocess
import sys
import tempfile
try:
    from .runtime import Session, Cancelled
    from .archives import discover, update
    from . import sources
except ImportError:
    from runtime import Session, Cancelled
    from archives import discover, update
    import sources


def restore_archive(current, backup, home):
    try:
        from .catalog import CATALOG
    except ImportError:
        from catalog import CATALOG
    def executable(root):
        data = json.loads((root/'utility-version.json').read_text())
        if not isinstance(data,dict) or not isinstance(data.get('name'),str):
            raise ValueError('Manifest di recupero non valido')
        entry = data.get('entrypoint') or CATALOG.get(data.get('name'),{}).get('entrypoint')
        if not isinstance(entry,str):
            raise ValueError('Eseguibile precedente non identificabile')
        relative = Path(entry)
        path = root/relative
        if relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or not os.access(path,os.X_OK):
            raise ValueError('Eseguibile di recupero assente o non avviabile')
        return relative

    current_entry, previous_entry = executable(current), executable(backup)
    changes = {}
    if current_entry != previous_entry:
        for launcher in (data_home(home)/'applications').glob('*.desktop'):
            if launcher.is_symlink():
                continue
            text = launcher.read_bytes().decode('utf-8')
            lines = []
            for line in text.splitlines(keepends=True):
                if line.startswith('Exec='):
                    match = re.match(r'Exec=("(?:[^"\\]|\\.)*"|[^\s]+)(.*)',line,re.S)
                    if match and shlex.split(match[1]) == [str(current/current_entry)]:
                        quoted = str(current/previous_entry).replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace(chr(96),'\\'+chr(96))
                        line = 'Exec="'+quoted+'"'+match[2]
                lines.append(line)
            updated = ''.join(lines)
            if updated != text:
                changes[launcher] = updated
    with tempfile.TemporaryDirectory(prefix='.restore-',dir=current.parent) as folder, \
            tempfile.TemporaryDirectory(prefix='.restore-',dir=(next(iter(changes)).parent if changes else current.parent)) as launchers:
        swap = Path(folder)/'current'
        staged = {}
        for index,(launcher,text) in enumerate(changes.items()):
            new, old = Path(launchers)/f'{index}.new', Path(launchers)/f'{index}.old'
            new.write_bytes(text.encode());shutil.copymode(launcher,new);shutil.copy2(launcher,old)
            staged[launcher] = (new,old)
        current.rename(swap)
        try:
            backup.rename(current)
        except BaseException:
            swap.rename(current)
            raise
        replaced = []
        try:
            for launcher,(new,_) in staged.items():
                new.replace(launcher);replaced.append(launcher)
            swap.rename(backup)
        except BaseException:
            for launcher in reversed(replaced):
                staged[launcher][1].replace(launcher)
            current.rename(backup);swap.rename(current)
            raise


def restore(s, home):
    for current in [p for root in app_roots(home) if root.exists() for p in root.iterdir()]:
        if current.name.endswith('.previous') or current.name.startswith('.'): continue
        backup=current.with_name(current.name+'.previous')
        if current.is_symlink() or backup.is_symlink() or not backup.is_dir(): continue
        if s.confirm('Ripristinare '+current.name+'?', 'Scambia la versione attiva con quella precedente. Chiudere prima l’applicazione.'):
            try:
                from .archives import running_under
            except ImportError:
                from archives import running_under
            if running_under(current):
                s.result(current.name,'intervento richiesto','Applicazione aperta.'); continue
            try:
                restore_archive(current, backup, home)
            except (OSError, ValueError, RuntimeError) as error:
                s.result(current.name,'intervento richiesto',str(error));continue
            s.result(current.name,'ripristinato')

    try:
        from . import profiles
        from .inventory import identify
        from .providers import verify_appimage
        from .archives import running_under
    except ImportError:
        import profiles
        from inventory import identify
        from providers import verify_appimage
        from archives import running_under
    records = profiles.load(home)
    locations = {}
    if any(record.get('version') and not record.get('recovery_path') for record in records.values()):
        from importlib import import_module
        inventory = import_module('.inventory', __package__) if __package__ else import_module('inventory')
        locations = {item.id:item.path for item in inventory.discover(home)
                     if Path(item.path).suffix.lower()=='.appimage'}
    for identifier,record in records.items():
        value=record.get('recovery_path') or (locations.get(identifier) if record.get('version') else None)
        if not value:continue
        path=Path(value);backup=path.with_name(path.name+'.previous')
        if identify(path)!=identifier or path.is_symlink() or backup.is_symlink():continue
        if not path.is_file() or not backup.is_file():continue
        if any(p.stat().st_uid!=os.getuid() for p in (path,backup)):continue
        try: verify_appimage(path);verify_appimage(backup)
        except (OSError,ValueError) as error:
            s.result(path.name,'intervento richiesto',str(error));continue
        if running_under(path):
            s.result(path.name,'intervento richiesto','Chiudere l’AppImage prima del recupero.');continue
        if s.confirm('Ripristinare '+path.name+'?',str(path)+'\nScambia il file attivo con la copia precedente.'):
            with tempfile.TemporaryDirectory(prefix='.restore-',dir=path.parent) as temp:
                temporary=Path(temp)/'current';path.rename(temporary)
                try:backup.rename(path)
                except BaseException:temporary.rename(path);raise
                try: temporary.rename(backup)
                except BaseException:
                    path.rename(backup);temporary.rename(path);raise
                updated=dict(record,recovery_path=str(path),version=record.get('previous_version',''),
                             previous_version=record.get('version',''))
                try: profiles.save(identifier,updated,home)
                except (OSError,ValueError) as error:
                    path.rename(temporary);backup.rename(path);temporary.rename(backup)
                    s.result(path.name,'errore',str(error));continue
            s.result(path.name,'ripristinato')


def clean_user(s,home):
    if shutil.which('flatpak'):
        s.command(['/usr/bin/flatpak','uninstall','--user','--unused','-y'])
    removed=0
    # Only abandoned staging folders owned by this utility; never backups.
    for path in [p for root in app_roots(home) for p in root.glob('.staging-*')]:
        if path.is_dir() and not path.is_symlink(): shutil.rmtree(path); removed+=1
    cache=cache_home(home)/'ubuntu-update-utility'
    if cache.is_dir() and not cache.is_symlink(): shutil.rmtree(cache); removed+=1
    s.result('Pulizia utente','pulito',f'{removed} directory temporanee/cache eliminate. Copie di recupero conservate.')


def main():
    if sys.argv[1:] not in ([],['--apply'],['--restore'],['--selected'],['--clean'],['--system']): return 2
    if os.geteuid()==0: return 1
    mode=sys.argv[1] if sys.argv[1:] else '--check'
    apply=mode in ('--apply','--selected','--system'); restoring=mode=='--restore'
    selected=None
    if mode=='--selected':
        try:
            from .selection import read_selection
        except ImportError:
            from selection import read_selection
        try: selected=read_selection()
        except (ValueError,TypeError): return 2
    home=Path.home(); s=Session()
    state=state_home(home)/'ubuntu-update-utility'; state.mkdir(parents=True,exist_ok=True)
    with open(state/'user.lock','w') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if restoring:
                restore(s,home)
                if not s.results: s.result('Recupero','nessun aggiornamento','Nessuna versione precedente disponibile.')
            else:
                tasks=[]
                if shutil.which('flatpak') and mode=='--apply':
                    def flatpak():
                        if apply:
                            s.command(['/usr/bin/flatpak','update','--user','-y'])
                            if mode=='--apply': s.command(['/usr/bin/flatpak','uninstall','--user','--unused','-y'])
                        else: s.command(['/usr/bin/flatpak','remote-ls','--user','--updates'])
                        s.result('Flatpak utente','aggiornato' if apply else 'controllato')
                    tasks.append(('Flatpak utente',flatpak))
                if mode=='--selected' and any(i.startswith('archive:') for i in selected):
                    # Backward-compatible IDs from an older GUI, never emitted by new scans.
                    for item in discover(home):
                        if 'archive:'+item['name'] in selected:tasks.append((item['name'],lambda i=item:update(s,i,True,home)))
                if mode in ('--check','--apply') or mode=='--selected' and any(i.startswith('install:') for i in selected):
                    try:
                        from .inventory import discover as inventory_discover
                        from .standalone import process as standalone_process
                        from .catalog import DEBS
                    except ImportError:
                        from inventory import discover as inventory_discover
                        from standalone import process as standalone_process
                        from catalog import DEBS
                    s.emit('stage',category='Inventario applicazioni',index=0,total=1)
                    for installation in inventory_discover(home,on_error=lambda path,error:s.result('Inventario','intervento richiesto',path+': '+error)):
                        if selected is None or installation.id in selected:
                            tasks.append((installation.name,lambda i=installation:standalone_process(s,i,apply,home)))
                if mode in ('--check','--selected') and shutil.which('flatpak'):
                    try:
                        from .flatpaks import process as flatpak_process
                    except ImportError:
                        from flatpaks import process as flatpak_process
                    tasks.append(('Flatpak user',lambda:flatpak_process(s,'user',selected)))
                if mode=='--clean': tasks=[('Pulizia utente',lambda:clean_user(s,home))]
                for index,(name, action) in enumerate(tasks):
                    s.checkpoint(); s.emit('stage',category=name,index=index,total=len(tasks))
                    try: action()
                    except Cancelled: raise
                    except Exception as error: s.result(name,'errore',str(error))
            s.emit('summary',results=s.results,reboot=Path('/var/run/reboot-required').exists())
            return int(any(i['status']=='errore' for i in s.results))
        except Cancelled:
            s.result('Sessione','saltato','Annullata tra operazioni.'); return 0
        except BlockingIOError:
            s.result('Sessione','errore','Un’altra sessione utente è in corso.'); return 1

if __name__=='__main__': sys.exit(main())
