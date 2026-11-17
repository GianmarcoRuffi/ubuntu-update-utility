#!/usr/bin/python3
"""Unprivileged phase: per-user Flatpak, archives, inventory and recovery."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
try:
    from .runtime import Session, Cancelled
    from .archives import discover, update
    from . import sources
except ImportError:
    from runtime import Session, Cancelled
    from archives import discover, update
    import sources


def special_apps(s, home, name):
    if name=='XAMPP' and Path('/opt/lampp').exists():
        page=sources.fetch('https://www.apachefriends.org/download.html').decode()
        versions=sorted(set(re.findall(r'xampp-linux-x64-([0-9.]+)-[0-9]+-installer.run',page)))
        s.result('XAMPP','intervento richiesto',('Versioni Linux pubblicate: '+', '.join(versions) if versions else 'Nessun installer Linux identificabile nella pagina ufficiale; disponibilità non verificabile automaticamente.')+
                 '\nMigrazione assistita richiesta per preservare database e progetti. https://www.apachefriends.org/faq_linux.html')
    if name=='Gpick' and (home/'.local/bin/gpick').exists():
        release=sources.release('thezbyg/gpick')
        s.result('Gpick personalizzato','intervento richiesto','Release: '+release['tag_name']+
                 '\nIl binario locale richiede verifica della provenienza e ricompilazione. '+release['html_url'])


def inventory(s, home):
    known=('postman','jmeter','audacity','forge','gpick','forticlient','teams','dbeaver','docker','chrome','github')
    files=list((home/'.local/share/applications').glob('*.desktop'))
    paths=[]
    for file in files:
        text=file.read_text(errors='replace')
        commands=re.findall(r'^Exec=(.*)$',text,re.M)
        if commands and not any(name in commands[0].lower() for name in known):
            if '/opt/' in commands[0] or str(home) in commands[0]: paths.append(file.stem)
    for folder in (home/'Applications',home/'.local/opt',Path('/opt')):
        if folder.exists():
            for entry in folder.iterdir():
                if not any(name in entry.name.lower() for name in known) and entry.name != 'lampp': paths.append(str(entry))
    if paths: s.result('Altre applicazioni','verifica manuale','\n'.join(sorted(set(paths))))


def restore(s, home):
    base=home/'.local/share/ubuntu-update-utility/apps'
    for current in base.iterdir() if base.exists() else []:
        if current.name.endswith('.previous') or current.name.startswith('.'): continue
        backup=current.with_name(current.name+'.previous')
        if not backup.is_dir(): continue
        if s.confirm('Ripristinare '+current.name+'?', 'Scambia la versione attiva con quella precedente. Chiudere prima l’applicazione.'):
            try:
                from .archives import running_under
            except ImportError:
                from archives import running_under
            if running_under(current):
                s.result(current.name,'intervento richiesto','Applicazione aperta.'); continue
            temporary=current.with_name('.swap-'+current.name)
            current.rename(temporary)
            try: backup.rename(current)
            except BaseException:
                temporary.rename(current); raise
            temporary.rename(backup)
            s.result(current.name,'ripristinato')


def main():
    if sys.argv[1:] not in ([],['--apply'],['--restore']): return 2
    if os.geteuid()==0: return 1
    apply=sys.argv[1:]==['--apply']; restoring=sys.argv[1:]==['--restore']
    home=Path.home(); s=Session()
    state=home/'.local/state/ubuntu-update-utility'; state.mkdir(parents=True,exist_ok=True)
    with open(state/'user.lock','w') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if restoring:
                restore(s,home)
                if not s.results: s.result('Recupero','nessun aggiornamento','Nessuna versione precedente disponibile.')
            else:
                tasks=[]
                if shutil.which('flatpak'):
                    def flatpak():
                        if apply:
                            s.command(['/usr/bin/flatpak','update','--user','-y'])
                            s.command(['/usr/bin/flatpak','uninstall','--user','--unused','-y'])
                        else: s.command(['/usr/bin/flatpak','remote-ls','--user','--updates'])
                        s.result('Flatpak utente','aggiornato' if apply else 'controllato')
                    tasks.append(('Flatpak utente',flatpak))
                for item in discover(home): tasks.append((item['name'],lambda i=item:update(s,i,apply,home)))
                tasks.extend([('XAMPP',lambda:special_apps(s,home,'XAMPP')),('Gpick',lambda:special_apps(s,home,'Gpick')),('Inventario',lambda:inventory(s,home))])
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
