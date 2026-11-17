"""Machine-independent desktop inventory. Never execute discovered programs."""
from dataclasses import dataclass
import configparser
import hashlib
import os
from pathlib import Path
try:
    from .paths import data_home,state_home,config_home,app_roots
except ImportError:
    from paths import data_home,state_home,config_home,app_roots
import shlex
import shutil
import subprocess
from functools import lru_cache
try:
    from .metadata import enrich
except ImportError:
    from metadata import enrich

@dataclass
class Installation:
    id: str
    name: str
    path: str
    version: str = ''
    package: str = ''
    homepage: str = ''
    icon: str = ''
    manager: str = 'standalone'
    mode: str = 'assisted'
    root: str = ''
    provider: str = ''
    entrypoint: str = ''
    channel: str = 'stable'
    update_info: str = ''
    desktop: str = ''
    wrapper: str = ''
    managed: bool = False
    stable_id: str = ''


def package_identify(package):
    return 'install:'+hashlib.sha256(('dpkg:'+package).encode()).hexdigest()

def identify(path):
    return 'install:'+hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()


def executable(command, search_path=None):
    try: words=shlex.split(command)
    except ValueError: return None
    if not words: return None
    if Path(words[0]).name=='env':
        words=words[1:]
        while words and '=' in words[0]: words=words[1:]
    if not words or words[0].startswith('-'): return None
    value=words[0]
    if not Path(value).is_absolute(): value=shutil.which(value,path=search_path)
    if not value: return None
    path=Path(value)
    try:
        if path.is_file(): return path.resolve()
    except OSError: pass
    return None


@lru_cache(maxsize=None)
def package_metadata(path):
    query=subprocess.run(['/usr/bin/dpkg-query','-S',str(path)],capture_output=True,text=True)
    if query.returncode: return {}
    package=query.stdout.split(': ',1)[0].split(':',1)[0]
    result=subprocess.run(['/usr/bin/dpkg-query','-W','-f=${Version}\t${Homepage}',package],capture_output=True,text=True)
    version,_,homepage=result.stdout.partition('\t')
    policy=subprocess.run(['/usr/bin/apt-cache','policy',package],capture_output=True,text=True,env=dict(os.environ,LC_ALL='C'))
    import re
    return dict(package=package,version=version,homepage=homepage.strip(),manager='apt' if re.search(r'^\s+\d+ https?://',policy.stdout,re.M) else 'standalone')


def looks_like_bundle(path,item):
    if item.provider or item.managed or (path/'lampp').is_file():return True
    for folder in (path,path/'bin',path/'app'):
        if not folder.is_dir():continue
        for file in folder.iterdir():
            if not file.is_file() or not os.access(file,os.X_OK):continue
            if '.so' in file.name or file.suffix in ('.dll','.dylib','.a','.o'):continue
            with file.open('rb') as stream:header=stream.read(4)
            if header.startswith((b'#!',b'\x7fELF')):return True
    return False


def discover(home=None, desktop_dirs=None, application_dirs=None, metadata=package_metadata,on_error=None):
    home=Path(home or Path.home())
    user_data=data_home(home)
    data_dirs=[Path(p) for p in os.environ.get('XDG_DATA_DIRS','/usr/local/share:/usr/share').split(':') if p]
    desktop_dirs=desktop_dirs if desktop_dirs is not None else [user_data/'applications',*[p/'applications' for p in data_dirs]]
    defaults=application_dirs is None
    application_dirs=application_dirs if application_dirs is not None else [home/'Applications',home/'.local/opt',Path('/opt'),Path('/usr/local/bin'),*app_roots(home)]
    if defaults:
        application_dirs.extend([home/'.local/bin',home/'bin'])
        for value in os.environ.get('PATH','').split(os.pathsep):
            path=Path(value)
            if value and path.is_absolute() and (path.is_relative_to(home) or path.is_relative_to('/usr/local') or path.is_relative_to('/opt')):
                if path not in application_dirs:application_dirs.append(path)
    found={}
    desktop_ids=set()
    apt_paths=set()
    for directory in desktop_dirs:
        try:desktops=list(Path(directory).glob('*.desktop'))
        except OSError as error:
            if on_error:on_error(str(directory),str(error))
            continue
        for desktop in desktops:
            if desktop.name in desktop_ids:continue
            desktop_ids.add(desktop.name)
            parser=configparser.ConfigParser(interpolation=None,strict=False)
            try:
                parser.read(desktop,encoding='utf-8');entry=parser['Desktop Entry']
                if entry.get('Type','Application')!='Application' or entry.get('Hidden','false')=='true' or entry.get('NoDisplay','false')=='true': continue
                path=executable(entry.get('Exec',''))
                if not path: continue
                if str(path).startswith(('/snap/','/var/lib/snapd/')) or 'flatpak run' in entry.get('Exec',''): continue
                wrapper=''
                details=metadata(path)
                if details.get('manager')=='apt':
                    apt_paths.add(path);continue
                if not details:
                    try:
                        with path.open('rb') as stream:data=stream.read(65536)
                        if data.startswith(b'#!'):
                            import re
                            lines=re.findall(r'^\s*exec\s+(.*)$',data.decode(errors='replace'),re.M)
                            target=executable(lines[-1]) if lines else None
                            if target and target!=path: wrapper=str(path);path=target;details=metadata(path)
                    except OSError:pass
                if details.get('manager')=='apt':
                    apt_paths.add(path);continue
                item=Installation(identify(path),entry.get('Name',path.name),str(path),icon=entry.get('Icon',''),desktop=str(desktop),wrapper=wrapper,**details)
                item=enrich(item);item.id=item.stable_id or (package_identify(item.package) if item.package else identify(item.root or path))
                if item.managed or item.id not in found:found[item.id]=item
            except (OSError,ValueError,configparser.Error,KeyError): continue
    for directory in application_dirs:
        directory=Path(directory)
        if not directory.is_dir(): continue
        try:
            candidates=list(directory.iterdir())
            if directory not in (Path('/usr/local/bin'),Path('/opt')):
                candidates.extend(directory.rglob('*.AppImage'))
        except OSError as error:
            if on_error:on_error(str(directory),str(error))
            continue
        for path in candidates:
            try:
                if any(part.startswith('.') and part not in ('.local','.config') or part.endswith(('.previous','.failed')) for part in path.relative_to(directory).parts):continue
                if any(path.resolve() in native.parents or path.resolve()==native for native in apt_paths):continue
                if path.is_symlink() and not path.exists(): continue
                if path.is_file() and not (os.access(path,os.X_OK) or path.suffix.lower()=='.appimage'): continue
                if any(i.provider=='builtin' and Path(i.root) in path.resolve().parents for i in found.values() if i.root):continue
                # Existing desktop entries already identify files within this bundle.
                if any(Path(i.root or i.path)==path.resolve() or path.resolve() in Path(i.path).parents for i in found.values()): continue
                details=metadata(path)
                if details.get('manager')=='apt':
                    apt_paths.add(path);continue
                item=enrich(Installation(identify(path),path.stem,str(path.resolve()),**details))
                if path.is_dir() and not looks_like_bundle(path,item):continue
                item.id=item.stable_id or (package_identify(item.package) if item.package else identify(item.root or path))
                if item.managed or item.id not in found:found[item.id]=item
            except (OSError,RuntimeError): continue
    return sorted(found.values(),key=lambda i:(i.name.lower(),i.path))
