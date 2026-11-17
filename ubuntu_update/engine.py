#!/usr/bin/python3
"""Installed, root-owned helper. Only fixed operations are available."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
try:
    from .runtime import Session, Cancelled
except ImportError:
    from runtime import Session, Cancelled


def protected_change(output):
    return any(line.startswith(('Inst forticlient', 'Remv ', 'Purg ')) for line in output.splitlines())


def capture(args):
    result = subprocess.run(args, capture_output=True, text=True, env=dict(os.environ, LC_ALL='C'))
    if result.returncode: raise RuntimeError(result.stderr.strip() or f'codice {result.returncode}')
    return result.stdout


def kernel_versions_to_keep():
    from functools import cmp_to_key
    running=os.uname().release
    output=capture(['/usr/bin/dpkg-query','-W','-f=${Package} ${db:Status-Abbrev}\n','linux-image-*'])
    versions=[]
    for line in output.splitlines():
        fields=line.split()
        if len(fields)>1 and fields[1]=='ii':
            value=fields[0].removeprefix('linux-image-').removeprefix('unsigned-')
            if re.match(r'[0-9]',value): versions.append(value)
    def compare(left,right):
        if left==right: return 0
        return 1 if subprocess.run(['/usr/bin/dpkg','--compare-versions',left,'gt',right],capture_output=True).returncode==0 else -1
    alternatives=sorted((v for v in versions if v!=running),key=cmp_to_key(compare))
    keep={running}
    if alternatives: keep.add(alternatives[-1])
    return keep


def cleanup_plan(output, keep_kernels=None):
    removed=re.findall(r'^(?:Remv|Purg) (\S+)',output,re.M)
    forbidden=False
    for package in removed:
        name=package.split(':',1)[0]
        if name.startswith(('forticlient','ubuntu-update-utility')): forbidden=True
        if name.startswith(('linux-image','linux-headers','linux-modules')):
            if keep_kernels is None or not re.search(r'-[0-9]',name): forbidden=True
            elif any(name.endswith('-'+version) or name.endswith('-'+version.rsplit('-',1)[0]) for version in keep_kernels): forbidden=True
    return removed,forbidden


def apt_update(s,clean_after=True):
    with tempfile.TemporaryDirectory(prefix='ubuntu-update-', dir='/run') as directory:
        prefs = Path(directory)/'preferences'
        original = Path('/etc/apt/preferences')
        prefs.write_text((original.read_text() if original.exists() else '')+'\nPackage: forticlient*\nPin: version *\nPin-Priority: -1\n')
        base = ['/usr/bin/apt-get', '-o', 'DPkg::Lock::Timeout=60', '-o', 'Dir::Etc::preferences='+str(prefs)]
        s.command(base+['-o', 'APT::Update::Error-Mode=any', 'update'])
        plan = capture(base+['-s', '--with-new-pkgs', 'upgrade'])
        s.emit('log',text=plan)
        if protected_change(plan):
            s.result('APT', 'intervento richiesto', plan); return
        s.command(base+['-y', '--with-new-pkgs', '-o', 'Dpkg::Options::=--force-confold', 'upgrade'])
        s.result('APT', 'aggiornato')
        if clean_after: apt_cleanup(s,base)

def apt_cleanup(s,base=None):
    base=base or ['/usr/bin/apt-get','-o','DPkg::Lock::Timeout=60']
    plan = capture(base+['-s', 'autoremove', '--purge'])
    removed, forbidden = cleanup_plan(plan,kernel_versions_to_keep())
    if forbidden:
        s.result('Pulizia APT', 'intervento richiesto', 'Proposta contenente kernel o pacchetti protetti.\n'+plan)
    elif removed and s.confirm('Rimuovere i pacchetti inutilizzati?', plan):
        # apt-get itself refuses essential removals without an additional flag.
        s.command(base+['-y', 'autoremove', '--purge'])
        s.result('Pulizia APT', 'aggiornato')
    else: s.result('Pulizia APT', 'saltato' if removed else 'nessun aggiornamento')
    s.command(base+['clean'])
    s.result('Cache APT','pulito','Cache dei pacchetti di installazione eliminata.')


def drivers(s, apply=True):
    output = capture(['/usr/bin/ubuntu-drivers', 'devices'])
    recommended = re.findall(r'^\s*driver\s*:\s*(\S+).*recommended', output, re.M)
    for package in recommended:
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', package): continue
        installed = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${db:Status-Abbrev}', package], capture_output=True, text=True)
        if installed.stdout.startswith('ii'): continue
        if not apply:
            s.result('Driver','aggiornamento disponibile',output); continue
        if s.confirm('Installare il driver raccomandato?', output+'\nPacchetto: '+package+'\nSecure Boot può richiedere la registrazione MOK al riavvio.'):
            plan=capture(['/usr/bin/apt-get','-s','--no-remove','install',package])
            if protected_change(plan):
                s.result('Driver','intervento richiesto',plan); continue
            s.command(['/usr/bin/apt-get','-o','DPkg::Lock::Timeout=60','-y','--no-remove','-o','Dpkg::Options::=--force-confold','install',package])
            s.result('Driver', 'aggiornato', package)
        else: s.result('Driver', 'saltato', package)
    if not any(item['category']=='Driver' for item in s.results): s.result('Driver','nessun aggiornamento')


def firmware(s):
    s.command(['/usr/bin/fwupdmgr', 'refresh'], accepted=(0, 2))
    result = subprocess.run(['/usr/bin/fwupdmgr', 'get-updates'], capture_output=True, text=True)
    if result.returncode == 2:
        s.result('Firmware', 'nessun aggiornamento', result.stdout); return
    if result.returncode: raise RuntimeError(result.stderr or result.stdout)
    if s.confirm('Installare gli aggiornamenti firmware?', result.stdout+'\nCollegare l’alimentazione. Potrebbe essere necessario un riavvio; non verrà eseguito automaticamente.'):
        s.command(['/usr/bin/fwupdmgr', 'update', '--assume-yes', '--no-reboot-check'], accepted=(0,2))
        s.result('Firmware', 'aggiornato')
    else: s.result('Firmware', 'saltato')


def forticlient(s, apply):
    result = subprocess.run(['/usr/bin/dpkg-query','-W','-f=${db:Status-Abbrev} ${Version}','forticlient'],capture_output=True,text=True)
    if not result.stdout.startswith('ii '):
        s.result('FortiClient','saltato','Applicazione non installata.'); return
    policy=capture(['/usr/bin/apt-cache','policy','forticlient'])
    if not re.search(r'^\s+\d+ https?://',policy,re.M):
        s.result('FortiClient','verifica manuale','Escluso dagli aggiornamenti automatici. Nessun repository configurato; controllare la versione compatibile sul portale Fortinet. https://www.fortinet.com/support/product-downloads'); return
    candidate=re.search(r'Candidate: (\S+)',policy)
    current=result.stdout.split()[-1]
    if not candidate or candidate[1] in (current,'(none)'):
        s.result('FortiClient','nessun aggiornamento','Escluso dall’aggiornamento automatico.'); return
    if not apply:
        s.result('FortiClient','intervento richiesto',policy); return
    if s.confirm('Aggiornare FortiClient?',policy+'\nPuò interrompere la VPN. Questa scelta vale soltanto per questa esecuzione.'):
        args=['/usr/bin/apt-get','-o','DPkg::Lock::Timeout=60','--no-remove']
        s.command(args+['-y','-o','Dpkg::Options::=--force-confold','install','forticlient='+candidate[1]])
        s.result('FortiClient','aggiornato',candidate[1])
    else: s.result('FortiClient','saltato')


def snap_update(s, apply, selected=None):
    if not apply:
        output=capture(['/usr/bin/snap','refresh','--list'])
        listing=capture(['/usr/bin/snap','list'])
        current={fields[0]:fields[1] for line in listing.splitlines()[1:] if len(fields:=line.split())>=2}
        held={fields[0] for line in listing.splitlines()[1:] if len(fields:=line.split())>=6 and 'held' in fields[-1]}
        for line in output.splitlines()[1:]:
            fields=line.split()
            if len(fields)<3 or fields[0] in held or not re.fullmatch(r'[a-z0-9][a-z0-9-]*',fields[0]): continue
            s.candidate('snap:'+fields[0],fields[0],current.get(fields[0],''),fields[1],'Snap')
        s.emit('log',text=output)
        return
    import datetime
    hold=subprocess.run(['/usr/bin/snap','get','system','refresh.hold'],capture_output=True,text=True)
    value=hold.stdout.strip()
    if value:
        try:
            held=value=='forever' or datetime.datetime.fromisoformat(value.replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
        except ValueError: held=True
        if held:
            s.result('Snap','saltato','Aggiornamenti sospesi dalla configurazione di sistema.'); return
    timing=capture(['/usr/bin/snap','refresh','--time','--abs-time'])
    match=re.search(r'^hold:\s*(.+)$',timing,re.M)
    if match and match[1] not in ('-','none'):
        try:
            active=match[1]=='forever' or datetime.datetime.fromisoformat(match[1].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
        except ValueError: active=True
        if active:
            s.result('Snap','saltato','Aggiornamenti sospesi da snap refresh --hold.'); return
    listing=capture(['/usr/bin/snap','list'])
    blocked={line.split()[0] for line in listing.splitlines()[1:] if line.split() and 'held' in line.split()[-1].split(',')}
    output=capture(['/usr/bin/snap','refresh','--list'])
    lines=output.splitlines()[1:]
    packages=[line.split()[0] for line in lines if line.split() and line.split()[0] not in blocked and 'held' not in line.split()[-1]]
    if selected is not None: packages=[p for p in packages if 'snap:'+p in selected]
    if not packages:
        s.result('Snap','nessun aggiornamento'); return
    for package in packages:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*',package): continue
        s.checkpoint(); s.command(['/usr/bin/snap','refresh',package])
        s.result('Snap: '+package,'aggiornato')
    s.result('Snap','aggiornato')

def snap_cleanup(s,packages=None):
    revisions=capture(['/usr/bin/snap','list','--all'])
    if packages is None: packages={line.split()[0] for line in revisions.splitlines()[1:] if line.split()}
    for package in packages:
        disabled=[]
        for line in revisions.splitlines()[1:]:
            fields=line.split()
            if len(fields)>=6 and fields[0]==package and 'disabled' in fields[-1] and fields[2].isdigit(): disabled.append(int(fields[2]))
        for revision in sorted(disabled)[:-1]:
            s.command(['/usr/bin/snap','remove',package,'--revision='+str(revision)])
    s.result('Pulizia Snap','pulito','Conservata una revisione precedente per ogni app aggiornata.')


def installer_cleanup(s, locations=None):
    locations=locations or [(Path('/var/tmp'),'ubuntu-update-deb-'),(Path('/run'),'ubuntu-update-')]
    removed=0
    for folder,prefix in locations:
        for path in folder.glob(prefix+'*'):
            if not re.fullmatch(re.escape(prefix)+r'[a-z0-9_]{8}',path.name): continue
            info=path.lstat()
            if path.is_symlink() or not path.is_dir() or info.st_uid!=0 or info.st_mode & 0o022: continue
            shutil.rmtree(path); removed+=1
    s.result('Installer temporanei','pulito',f'{removed} directory di installazione abbandonate eliminate.')


def main():
    if sys.argv[1:] not in ([],['--apply'],['--selected'],['--clean'],['--system']): return 2
    mode=sys.argv[1] if sys.argv[1:] else '--check'
    apply=mode!='--check'
    selected=None
    if mode=='--selected':
        try:
            from selection import read_selection
        except ImportError:
            from .selection import read_selection
        try: selected=read_selection()
        except (ValueError,TypeError): return 2
    if apply and os.geteuid() != 0: return 1
    s = Session()
    lock = None
    try:
        if apply:
            lock = open('/run/ubuntu-update-utility.lock', 'w')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        tasks = [('APT', lambda: apt_update(s))] if apply else [('APT', lambda: s.command(['/usr/bin/apt', 'list', '--upgradable']))]
        if shutil.which('snap'): tasks.append(('Snap', lambda: snap_update(s,apply)))
        if shutil.which('flatpak'):
            def flatpak():
                if apply:
                    s.command(['/usr/bin/flatpak', 'update', '--system', '-y'])
                    if mode=='--apply': s.command(['/usr/bin/flatpak', 'uninstall', '--system', '--unused', '-y'])
                else: s.command(['/usr/bin/flatpak', 'remote-ls', '--system', '--updates'])
            tasks.append(('Flatpak sistema', flatpak))
        tasks.append(('FortiClient',lambda:forticlient(s,apply)))
        if shutil.which('ubuntu-drivers'): tasks.append(('Driver', lambda: drivers(s,apply)))
        if shutil.which('fwupdmgr'): tasks.append(('Firmware', lambda: firmware(s) if apply else s.command(['/usr/bin/fwupdmgr','get-updates'], accepted=(0,2))))
        try:
            from .packages import PACKAGES, update_package
        except ImportError:
            from packages import PACKAGES, update_package
        tasks.extend((package, lambda p=package: update_package(s,p,apply)) for package in PACKAGES)
        if mode=='--selected':
            tasks=[]
            if any(i.startswith('snap:') for i in selected): tasks.append(('Snap',lambda:snap_update(s,True,selected)))
            tasks.extend((p,lambda p=p:update_package(s,p,True)) for p in PACKAGES if 'deb:'+p in selected)
        elif mode=='--clean':
            tasks=[('Pulizia APT',lambda:apt_cleanup(s)),('Installer temporanei',lambda:installer_cleanup(s))]
            if shutil.which('snap'): tasks.append(('Pulizia Snap',lambda:snap_cleanup(s)))
            if shutil.which('flatpak'): tasks.append(('Pulizia Flatpak',lambda:s.command(['/usr/bin/flatpak','uninstall','--system','--unused','-y'])))
        elif mode=='--system':
            tasks=[(name,action) for name,action in tasks if name not in PACKAGES and name!='Snap']
            tasks[0]=('APT',lambda:apt_update(s,clean_after=False))
        for index,(category, action) in enumerate(tasks):
            s.checkpoint(); s.emit('stage',category=category,index=index,total=len(tasks))
            count = len(s.results)
            try:
                action()
                if count == len(s.results): s.result(category, 'pulito' if mode=='--clean' else 'aggiornato' if apply else 'controllato')
            except Cancelled: raise
            except Exception as error: s.result(category, 'errore', str(error))
        s.emit('summary', results=s.results, reboot=Path('/var/run/reboot-required').exists())
        return int(any(item['status']=='errore' for item in s.results))
    except Cancelled:
        s.result('Sessione', 'saltato', 'Annullata tra le operazioni.'); return 0
    except BlockingIOError:
        s.result('Sessione', 'errore', 'Un aggiornamento è già in corso.'); return 1
    finally:
        if lock: lock.close()

if __name__ == '__main__': sys.exit(main())
