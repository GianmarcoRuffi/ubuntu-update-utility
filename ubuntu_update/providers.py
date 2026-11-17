"""Reusable update sources for discovered standalone installations."""
from dataclasses import dataclass
import fnmatch
import hashlib
import json
from pathlib import Path
try:
    from .paths import data_home,state_home,config_home,app_roots
except ImportError:
    from paths import data_home,state_home,config_home,app_roots
import re
import struct
import subprocess
import tempfile
from urllib.parse import urlsplit, urljoin
import xml.etree.ElementTree as ET
try:
    from . import sources,profiles
except ImportError:
    import sources,profiles

@dataclass
class Check:
    source: dict | None = None
    reason: str = ''
    available: bool = False


def version(value):
    match=re.search(r'\d+\.\d+(?:\.\d+)*(?:[-+~][A-Za-z0-9._+-]+)?',value)
    return match[0] if match else ''


def validate_entrypoint(value):
    p=Path(value)
    if not value or p.is_absolute() or '..' in p.parts: raise ValueError('Eseguibile relativo non valido')
    return value


def github(item,profile):
    repository=profile.get('repository','')
    if not repository:
        match=re.fullmatch(r'https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/?',item.homepage)
        if match: repository=match[1]
    if not repository: raise ValueError('Repository non identificato')
    channel=profile.get('channel',item.channel)
    pattern=profile.get('asset','')
    if not pattern:
        if Path(item.path).suffix.lower()=='.appimage':
            pattern='*.AppImage'
        elif item.package:pattern='*.deb'
        else: raise ValueError('Scegli il pacchetto Linux della release e il percorso dell’eseguibile nella procedura assistita.')
    data=sources.release(repository,channel)
    arch=subprocess.check_output(['/usr/bin/dpkg','--print-architecture'],text=True).strip()
    candidates=[a for a in data.get('assets',[]) if fnmatch.fnmatchcase(a['name'].lower(),pattern.lower())]
    wrong=('aarch64','arm64') if arch=='amd64' else ('x86_64','amd64','i386','i686')
    candidates=[a for a in candidates if not any(cpu in a['name'].lower() for cpu in wrong)]
    if len(candidates)!=1: raise ValueError('Pacchetto della release assente o ambiguo: specifica il nome nella procedura assistita.')
    asset=candidates[0];filename=asset['name']
    if Path(filename).name!=filename: raise ValueError('Nome del pacchetto non valido')
    candidate=version(data['tag_name'])
    if not candidate: raise ValueError('Versione della release non identificabile')
    kind='deb' if filename.lower().endswith('.deb') else 'appimage' if filename.lower().endswith('.appimage') else 'archive' if re.search(r'\.(tar\.(gz|xz|bz2)|tgz)$',filename) else 'assisted'
    digest=asset.get('digest','') or ''
    sha=digest.removeprefix('sha256:') if digest.startswith('sha256:') else ''
    extra={}
    if not sha:
        for algorithm,width in (('sha256',64),('sha512',128)):
            sidecar=next((a for a in data.get('assets',[]) if a['name']==filename+'.'+algorithm),None)
            if sidecar:
                match=re.search(r'\b[0-9a-fA-F]{'+str(width)+r'}\b',sources.fetch(sidecar['browser_download_url']).decode())
                if not match:raise ValueError('Checksum pubblicato non valido')
                extra[algorithm]=match[0]
                break
        if not extra:
            sums=next((a for a in data.get('assets',[]) if a['name'].lower() in ('sha256sums','sha256sums.txt','checksums.txt','sha256sum.txt')),None)
            if sums:
                content=sources.fetch(sums['browser_download_url']).decode()
                for line in content.splitlines():
                    if line.rstrip().endswith(filename):
                        match=re.search(r'\b[0-9a-fA-F]{64}\b',line)
                        if match:extra['sha256']=match[0];break
                if not extra:raise ValueError('Pacchetto non presente nell’elenco dei checksum pubblicati')
    sha=sha or extra.get('sha256','')
    return dict(version=candidate,url=asset['browser_download_url'],name=filename,sha256=sha,page=data['html_url'],format=kind,entrypoint=profile.get('entrypoint',''),hosts=sources.HOSTS,sha512=extra.get('sha512',''))


def external_manifest(item,profile):
    url=profiles.validate_url(profile['manifest'])
    hosts=set(sources.HOSTS)|{urlsplit(url).hostname}
    raw=sources.fetch(url,allowed_hosts=hosts)
    if profile.get('provider')=='appcast':
        tree=ET.fromstring(raw);enclosure=tree.find('./channel/item/enclosure')
        if enclosure is None: raise ValueError('Manifest appcast privo di pacchetto')
        ns='{http://www.andymatuschak.org/xml-namespaces/sparkle}'
        data=dict(version=enclosure.get(ns+'shortVersionString') or enclosure.get(ns+'version',''),url=enclosure.get('url',''),sha256='',format=profile.get('format','archive'))
    else:
        data=json.loads(raw)
        if not isinstance(data,dict): raise ValueError('Manifest JSON non valido')
    candidate=version(str(data.get('version','')));download=profiles.validate_url(urljoin(url,data.get('url','')))
    if not isinstance(candidate,str) or not version(candidate): raise ValueError('Versione del manifest non valida')
    hosts.add(urlsplit(download).hostname)
    name=Path(urlsplit(download).path).name
    return dict(version=candidate,url=download,name=name,sha256=data.get('sha256',''),page=profile.get('homepage',url),format='deb' if name.lower().endswith('.deb') else 'appimage' if name.lower().endswith('.appimage') else 'archive',entrypoint=profile.get('entrypoint',''),hosts=hosts)


def appimage_zsync(item,info):
    url=profiles.validate_url(info.removeprefix('zsync|'))
    hosts=set(sources.HOSTS)|{urlsplit(url).hostname}
    header=sources.fetch(url,allowed_hosts=hosts).split(b'\n\n',1)[0].decode()
    fields=dict(line.split(': ',1) for line in header.splitlines() if ': ' in line)
    name=fields.get('Filename','');sha=fields.get('SHA-1','')
    if Path(name).name!=name or not re.fullmatch('[a-fA-F0-9]{40}',sha): raise ValueError('Metadati zsync non validi')
    download=profiles.validate_url(urljoin(url,fields.get('URL',name)));hosts.add(urlsplit(download).hostname)
    # SHA-1 is the integrity hash published by zsync; it is not a signature.
    return dict(version='',url=download,name=name,sha1=sha,page=url,format='appimage',entrypoint='',hosts=hosts)


def check(item,profile=None):
    profile=profile or {}
    try:
        if profile.get('version') and not item.version: item.version=profile['version']
        if profile.get('manifest'): source=external_manifest(item,profile)
        elif item.update_info.startswith('zsync|'): source=appimage_zsync(item,item.update_info)
        else:
            if item.update_info.startswith('gh-releases-zsync|'):
                parts=item.update_info.split('|')
                if len(parts)!=5: raise ValueError('Informazioni AppImage non valide')
                _,owner,repo,channel,pattern=parts
                profile=dict(profile,repository=owner+'/'+repo,channel='stable' if channel=='latest' else channel,asset=pattern.removesuffix('.zsync'))
            source=github(item,profile)
        if item.package and source['format']!='deb':return Check(source,'Il pacchetto proposto cambia il formato dell’installazione: procedura assistita richiesta.',True)
        if source['format']=='deb' and not item.package:return Check(source,'Il DEB richiede una migrazione: l’installazione attuale non appartiene a un pacchetto Debian.',True)
        if source['format']=='archive':
            validate_entrypoint(source['entrypoint'])
            if item.wrapper:return Check(source,'Il launcher usa un wrapper personalizzato: seguire il percorso assistito per conservarne le opzioni.',True)
        if source['format']=='assisted': return Check(source,'Questo formato richiede l’installazione assistita.',True)
        if source.get('sha1'):
            path=Path(item.path)
            with path.open('rb') as stream: current=hashlib.file_digest(stream,'sha1').hexdigest()
            return Check(source,available=current.lower()!=source['sha1'].lower())
        if not item.version: return Check(source,'Versione installata non verificabile: specificarla nella procedura assistita.',True)
        return Check(source,available=sources.newer(source['version'],item.version))
    except (OSError,ValueError,TypeError,KeyError,ET.ParseError) as error:
        return Check(reason=str(error))


def verify_appimage(path):
    with open(path,'rb') as stream: data=stream.read(64)
    if len(data)<20 or data[:4]!=b'\x7fELF' or data[8:11] not in (b'AI\x01',b'AI\x02'):
        raise ValueError('Il file scaricato non è una AppImage')
    machine=struct.unpack_from('<H' if data[5]==1 else '>H',data,18)[0]
    arch=subprocess.check_output(['/usr/bin/dpkg','--print-architecture'],text=True).strip()
    if machine!={'amd64':62,'arm64':183}.get(arch): raise ValueError('Architettura AppImage incompatibile')


def verify_executable(path):
    with open(path,'rb') as stream:header=stream.read(256)
    if header.startswith(b'#!'):
        first=header.split(b'\n',1)[0]
        if b'\r' in first:raise ValueError('Script con formato non compatibile')
        interpreter=first[2:].strip().split(b' ',1)[0].decode()
        if not Path(interpreter).is_absolute() or not Path(interpreter).is_file():raise ValueError('Interprete dello script non disponibile')
        return
    if len(header)<20 or header[:4]!=b'\x7fELF' or header[5] not in (1,2):raise ValueError('Formato dell’eseguibile non riconosciuto: procedura assistita richiesta')
    machine=struct.unpack_from('<H' if header[5]==1 else '>H',header,18)[0]
    arch=subprocess.check_output(['/usr/bin/dpkg','--print-architecture'],text=True).strip()
    if machine!={'amd64':62,'arm64':183}.get(arch):raise ValueError('Architettura dell’eseguibile incompatibile')


def install(session,item,source,home):
    try:
        from .archives import safe_extract,activate,running_under
    except ImportError:
        from archives import safe_extract,activate,running_under
    old=Path(item.root or item.path)
    if source['format']=='assisted': return False
    if running_under(old) or running_under(Path(item.path)):
        session.result(item.name,'intervento richiesto','Chiudere l’applicazione e riprovare.');return False
    if not session.confirm('Aggiornare '+item.name+'?',f"Installazione: {old}\nFonte: {source['page']}\nPacchetto: {source['url']}\nVersione: {item.version or 'non identificata'} → {source['version'] or 'nuovo contenuto verificato tramite zsync'}"):
        session.result(item.name,'saltato');return False
    if source['format']=='appimage' and old.is_file():
        if old.stat().st_uid!=__import__('os').getuid() or not __import__('os').access(old.parent,__import__('os').W_OK):
            session.result(item.name,'intervento richiesto','AppImage non modificabile dall’utente. Scegliere una posizione utente nella procedura assistita.');return False
        base=old.parent
    else:
        base=data_home(home)/'ubuntu-update-utility/apps';base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.staging-',dir=base) as temp:
        temp=Path(temp);download=temp/source['name']
        sources.fetch(source['url'],download,limit=3*1024**3,allowed_hosts=source.get('hosts'))
        for algorithm in ('sha256','sha512','sha1'):
            if source.get(algorithm): sources.verify(download,source[algorithm],algorithm)
        if source['format']=='deb':
            with download.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            code=session.child(['/usr/bin/pkexec','/usr/lib/ubuntu-update-utility/helper','--local-deb'],dict(package=item.package,path=str(download),sha256=digest,version=source['version']))
            if code:
                session.result(item.name,'intervento richiesto','Il pacchetto non è stato installato. Controllare i dettagli.');return False
        elif source['format']=='appimage':
            verify_appimage(download);download.chmod(0o755)
            backup=old.with_name(old.name+'.previous')
            if backup.exists() and (backup.is_symlink() or not backup.is_file()): raise ValueError('Copia di recupero inattesa')
            if backup.exists(): backup.unlink()
            old.rename(backup)
            try: download.rename(old)
            except BaseException:
                backup.rename(old);raise
            record=profiles.load(home).get(item.id,{})
            profiles.save(item.id,dict(record,recovery_path=str(old),previous_version=item.version,version=source['version'] or item.version),home)
            # Keep executable location unchanged so desktop arguments are preserved.
        else:
            unpack=temp/'unpack';safe_extract(download,unpack)
            entries=list(unpack.iterdir());staged=entries[0] if len(entries)==1 and entries[0].is_dir() else unpack
            relative=Path(validate_entrypoint(source['entrypoint']));executable=staged/relative
            if not executable.resolve().is_relative_to(staged.resolve()) or not executable.is_file(): raise ValueError('Eseguibile previsto assente o esterno all’archivio')
            verify_executable(executable)
            executable.chmod(executable.stat().st_mode|0o100)
            # Packages containing application state need a dedicated migration.
            if any((old/folder).exists() for folder in ('var','data','htdocs','mysql')):
                session.result(item.name,'intervento richiesto','L’installazione contiene dati locali: seguire la migrazione assistita prima di sostituirla.');return False
            target=base/item.id.removeprefix('install:')
            user_desktop=None;text=None
            if item.desktop:
                desktop=Path(item.desktop)
                user_desktop=data_home(home)/'applications'/desktop.name
                import shlex
                lines=[]
                for line in desktop.read_text().splitlines():
                    if line.startswith('Exec='):
                        tokens=shlex.split(line[5:])
                        if not tokens or Path(tokens[0]).resolve()!=Path(item.path).resolve():raise ValueError('Launcher con wrapper: aggiornamento assistito richiesto')
                        tokens[0]=str(target/relative)
                        line='Exec='+' '.join('"'+t.replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')+'"' if not t.startswith('%') else t for t in tokens)
                    lines.append(line)
                text='\n'.join(lines)+'\n'
            else:
                session.result(item.name,'intervento richiesto','Associare un launcher all’installazione prima di attivare un archivio generico.');return False
            (staged/'utility-version.json').write_text(json.dumps(dict(name=item.name,version=source['version'],provider='generic',entrypoint=str(relative),homepage=item.homepage,original_id=item.id)))
            if not target.exists():
                import shutil
                backup=target.with_name(target.name+'.previous')
                if backup.exists():raise ValueError('Copia di recupero già presente: verificare l’installazione')
                if old.is_dir():shutil.copytree(old,backup,symlinks=True)
                else:
                    backup.mkdir();saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,saved)
                (backup/'utility-version.json').write_text(json.dumps(dict(name=item.name,version=item.version,provider='generic',entrypoint=str(relative),homepage=item.homepage,original_id=item.id)))
                staged.rename(target)
            else:activate(staged,target)
            try:
                user_desktop.parent.mkdir(parents=True,exist_ok=True)
                with tempfile.NamedTemporaryFile(mode='w',dir=user_desktop.parent,delete=False) as stream:
                    stream.write(text);temporary=Path(stream.name)
                temporary.replace(user_desktop)
            except BaseException:
                failed=target.with_name(target.name+'.failed')
                if not failed.exists():
                    target.rename(failed);target.with_name(target.name+'.previous').rename(target)
                raise
    session.emit('completed',id=item.id)
    session.result(item.name,'aggiornato',(source['version'] or 'Contenuto AppImage aggiornato')+'\nInstallazione: '+str(old))
    return True
