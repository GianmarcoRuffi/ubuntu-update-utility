"""User-owned standalone installations with atomic activation and one backup."""
import json
import os
from pathlib import Path
try:
    from .paths import data_home,state_home,config_home,app_roots
except ImportError:
    from paths import data_home,state_home,config_home,app_roots
import re
import shutil
import subprocess
import tarfile
import tempfile
try:
    from . import sources
except ImportError:
    import sources


def safe_extract(archive, destination):
    with tarfile.open(archive) as tar:
        # data filter forbids traversal, device nodes and escaping links.
        members=tar.getmembers()
        size=sum(member.size for member in members)
        destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
        if size > 12*1024**3 or size+128*1024**2 > shutil.disk_usage(destination).free:
            raise OSError('Spazio insufficiente per estrarre l’archivio')
        tar.extractall(destination, members=members, filter='data')


def activate(staged, target):
    """Keep one previous installation and restore it if activation fails."""
    target, staged = Path(target), Path(staged)
    backup = target.with_name(target.name+'.previous')
    if backup.exists():
        if backup.is_symlink(): raise ValueError('Backup simbolico inatteso')
        shutil.rmtree(backup)
    had_previous = target.exists()
    if had_previous: target.rename(backup)
    try: staged.rename(target)
    except BaseException:
        if had_previous: backup.rename(target)
        raise
    return backup if had_previous else None


def user_home():
    return Path.home()


def running_under(path):
    prefix = str(path.resolve())+'/'
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            exe = str((proc/'exe').resolve(strict=True))
            cmd = (proc/'cmdline').read_bytes().decode(errors='replace')
            if exe==str(path.resolve()) or exe.startswith(prefix) or prefix in cmd or str(path.resolve()) in cmd.split('\0'): return True
        except (OSError, RuntimeError): continue
    return False


def discover(home):
    items = []
    postman = Path('/opt/Postman')
    if postman.exists():
        metadata = postman/'app/resources/app/package.json'
        try: version=json.loads(metadata.read_text()).get('version') if metadata.exists() else None
        except (ValueError,OSError): version=None
        items.append(dict(name='Postman', version=version, path=postman))
    for path in Path('/opt').glob('apache-jmeter-*'):
        if path.is_dir(): items.append(dict(name='JMeter',version=path.name.removeprefix('apache-jmeter-'),path=path))
    for path in (home/'.local/opt/audacity').glob('Audacity-*'):
        if path.is_dir(): items.append(dict(name='Audacity standalone',version=path.name.removeprefix('Audacity-'),path=path))
    for path in home.glob('forge-installer-*'):
        if path.is_dir(): items.append(dict(name='Forge',version=path.name.removeprefix('forge-installer-').replace('-SNAPSHOT','~snapshot'),path=path))
    managed = data_home(home)/'ubuntu-update-utility/apps'
    for folder in managed.glob('*'):
        if folder.name.endswith(('.previous','.failed')) or folder.name.startswith('.'): continue
        metadata = folder/'utility-version.json'
        if metadata.exists():
            try: data=json.loads(metadata.read_text())
            except (ValueError,OSError):
                items.append(dict(name=folder.name,version=None,path=folder)); continue
            try:
                from .catalog import ARCHIVES
            except ImportError:
                from catalog import ARCHIVES
            if data.get('name') not in ARCHIVES: continue
            items = [i for i in items if i['name'] != data['name']]
            items.append(dict(name=data['name'],version=data.get('version'),path=folder))
    return items


def source_for(name):
    arch = subprocess.check_output(['/usr/bin/dpkg','--print-architecture'],text=True).strip()
    if name == 'Audacity standalone':
        cpu = 'x86_64' if arch=='amd64' else 'aarch64'
        return sources.github_asset('audacity/audacity',rf'audacity-linux-.*-{cpu}\.AppImage')
    if name == 'Forge': return sources.github_asset('Card-Forge/forge',r'forge-installer-[0-9.]+\.tar\.bz2')
    if name == 'JMeter':
        page = sources.fetch('https://jmeter.apache.org/download_jmeter.cgi').decode()
        version = re.search(r'apache-jmeter-([0-9.]+)\.tgz',page)
        if not version: raise ValueError('Versione JMeter non identificata')
        filename='apache-jmeter-'+version[1]+'.tgz'
        url='https://dlcdn.apache.org/jmeter/binaries/'+filename
        digest=sources.fetch('https://downloads.apache.org/jmeter/binaries/'+filename+'.sha512').decode().split()[0]
        return dict(version=version[1],url=url,name=filename,sha512=digest,page='https://jmeter.apache.org/download_jmeter.cgi')
    if name == 'Postman':
        version=json.loads(sources.fetch('https://dl.pstmn.io/api/version/latest'))['version']
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+',version): raise ValueError('Versione Postman non valida')
        return dict(version=version,url='https://dl.pstmn.io/download/version/'+version+'/linux_'+('64' if arch=='amd64' else 'arm64'),name='postman.tar.gz',page='https://www.postman.com/downloads/')
    raise ValueError('Applicazione non supportata')


def update(s, item, apply, home):
    name, old = item['name'], item['path']
    if not item.get('version'):
        s.result(name,'verifica manuale','Versione installata non identificabile.'); return
    source = source_for(name)
    if source['version'] and not sources.newer(source['version'],item['version']):
        s.result(name,'nessun aggiornamento',str(item['version'])); return
    if not apply:
        s.emit('candidate',id=item.get('id','archive:'+name),name=name,current=item['version'],available=source['version'],kind='Standalone',mode='automatic',path=str(old))
        s.result(name,'aggiornamento disponibile' if source['version'] else 'verifica archivio richiesta',
                 f"{item['version']} → {source['version'] or 'ultima versione del produttore'}\n{source['page']}"); return
    if running_under(old):
        s.result(name,'intervento richiesto','Chiudere l’applicazione e riprovare.'); return
    base=data_home(home)/'ubuntu-update-utility/apps'
    base.mkdir(parents=True,exist_ok=True)
    target=base/item.get('target',name.lower().replace(' ','-'))
    with tempfile.TemporaryDirectory(prefix='.staging-',dir=base) as temp:
        temp=Path(temp); archive=temp/source['name']
        sources.fetch(source['url'],archive,limit=3*1024**3)
        for algorithm in ('sha256','sha512'):
            if source.get(algorithm): sources.verify(archive,source[algorithm],algorithm)
        if name=='Audacity standalone':
            archive.chmod(0o755)
            # Extract as the desktop user; the existing installation also uses AppRun.
            subprocess.run([str(archive),'--appimage-extract'],cwd=temp,check=True,stdout=subprocess.DEVNULL)
            staged=temp/'squashfs-root'; executable=staged/'AppRun'
        else:
            unpack=temp/'unpack'; unpack.mkdir(); safe_extract(archive,unpack)
            contents=list(unpack.iterdir())
            staged=contents[0] if len(contents)==1 and contents[0].is_dir() else unpack
            executable=staged/({'Postman':'Postman','JMeter':'bin/jmeter','Forge':'forge-adventure.sh'}[name])
        if name=='Postman':
            metadata=staged/'app/resources/app/package.json'
            actual=json.loads(metadata.read_text())['version']
            if source['version'] != actual: raise ValueError('Versione archivio Postman inattesa')
            if not sources.newer(source['version'],item['version']):
                s.result(name,'nessun aggiornamento',item['version']); return
        if not executable.is_file() or not os.access(executable,os.X_OK):
            raise ValueError('Eseguibile previsto assente o non avviabile nell’archivio')
        if name == 'Forge':
            profile=old/'forge.profile.properties'
            if profile.exists():
                text=profile.read_text()
                # Relative data paths must remain anchored to the old installation.
                def absolute_path(match):
                    key,value=match.group(1),match.group(2).strip()
                    if value and not value.startswith('/'):
                        value=str((old/value).resolve())
                    return key+'='+value
                text=re.sub(r'^(\w*Dir)=(.*)$',absolute_path,text,flags=re.M)
                (staged/'forge.profile.properties').write_text(text)
        if name == 'JMeter':
            if staged.name != 'apache-jmeter-'+source['version']:
                raise ValueError('Versione archivio JMeter inattesa')
            for filename in ('user.properties','system.properties'):
                original=old/'bin'/filename
                if original.exists(): shutil.copy2(original,staged/'bin'/filename)
            if any(not jar.name.startswith('ApacheJMeter_') for jar in (old/'lib/ext').glob('*.jar')):
                s.result(name,'intervento richiesto','Plugin personalizzati presenti: migrazione da verificare.'); return
        relative=executable.relative_to(staged)
        (staged/'utility-version.json').write_text(json.dumps(dict(name=name,version=source['version'],provider='builtin',entrypoint=str(relative),original_id=item.get('id',''))))
        # Initial copy remains intact as an additional recovery point. Never delete
        # data from /opt or the user's original installation automatically.
        if not target.exists() and not s.confirm('Attivare '+name+' '+source['version']+'?',
                'La nuova versione sarà installata separatamente. La precedente e i suoi dati saranno conservati. I collegamenti esistenti saranno aggiornati mantenendo gli argomenti.'):
            s.result(name,'saltato'); return
        # Seed the first recovery copy from the existing installation, so the
        # Restore button also works immediately after adopting an application.
        if not target.exists():
            previous=target.with_name(target.name+'.previous')
            original=old/'squashfs-root' if name=='Audacity standalone' else old
            required=sum(p.stat().st_size for p in original.rglob('*') if p.is_file() and not p.is_symlink())
            if required+128*1024**2 > shutil.disk_usage(base).free:
                raise OSError('Spazio insufficiente per conservare la versione precedente')
            if previous.exists(): raise ValueError('Copia di recupero inattesa: verificare manualmente')
            shutil.copytree(original,previous,symlinks=True)
            (previous/'utility-version.json').write_text(json.dumps(dict(name=name,version=item['version'],provider='builtin',entrypoint=str(relative),original_id=item.get('id',''))))
            # activate() replaces existing backups only when target exists.
            staged.rename(target)
        else:
            activate(staged,target)
        newexe=target/relative
        try:
            replace_launchers(home,old,target,newexe,name,item.get('wrapper',None))
        except BaseException:
            # Preserve both complete versions if launcher activation fails.
            failed=target.with_name(target.name+'.failed')
            if not failed.exists():
                target.rename(failed)
                target.with_name(target.name+'.previous').rename(target)
            raise
        if item.get('id'): s.emit('completed',id=item['id'])
        s.result(name,'aggiornato',source['version']+'; precedente conservata in '+str(old))


def replace_launchers(home, old, target, executable, name, wrapper_path=None):
    directory=data_home(home)/'applications'; directory.mkdir(parents=True,exist_ok=True)
    # Preserve custom JMeter shell wrapper, including JAVA_HOME and suite args.
    wrappers={'JMeter':home/'.local/bin/apache-jmeter-gui','Audacity standalone':home/'.local/bin/audacity'}
    wrapper=Path(wrapper_path) if wrapper_path else wrappers.get(name) if wrapper_path is None else None
    if wrapper and wrapper.is_symlink():
        backup=wrapper.with_name(wrapper.name+'.previous')
        if backup.is_symlink(): backup.unlink()
        elif backup.exists(): raise ValueError('Backup launcher già presente')
        wrapper.rename(backup); wrapper.symlink_to(executable)
    elif wrapper and wrapper.is_file():
        text=wrapper.read_text()
        changed=text.replace(str(old),str(target))
        if changed != text:
            backup=wrapper.with_name(wrapper.name+'.previous')
            if not backup.exists(): shutil.copy2(wrapper,backup)
            wrapper.write_text(changed)
    has_launcher=False
    for file in directory.glob('*.desktop'):
        text=file.read_text(errors='replace')
        if str(old) in text or str(target) in text or (wrapper and str(wrapper) in text): has_launcher=True
        changed=text.replace(str(old/'squashfs-root/AppRun'),str(executable)).replace(str(old),str(target))
        if changed!=text:
            backup=file.with_suffix('.desktop.previous')
            if not backup.exists(): shutil.copy2(file,backup)
            file.write_text(changed)
    if has_launcher: return
    if wrapper and wrapper.exists(): executable=wrapper
    launcher=directory/('ubuntu-update-'+name.lower().replace(' ','-')+'.desktop')
    launcher.write_text('[Desktop Entry]\nType=Application\nName='+name+'\nExec="'+str(executable).replace('"','\\"')+'"\nIcon=system-software-update\nTerminal=false\nCategories=Utility;\n')
