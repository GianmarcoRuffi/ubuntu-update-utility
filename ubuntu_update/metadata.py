"""Read application identity from data, without executing an installed binary."""
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET


def appimage_update_info(path):
    """Read the ELF .upd_info section, for both endian orders and ELF classes."""
    with open(path, 'rb') as stream:
        header=stream.read(64)
        if len(header)<64 or header[:4]!=b'\x7fELF' or header[4] not in (1,2) or header[5] not in (1,2): return ''
        endian='<' if header[5]==1 else '>'
        is64=header[4]==2
        offset=struct.unpack_from(endian+('Q' if is64 else 'I'),header,40 if is64 else 32)[0]
        size,count,index=struct.unpack_from(endian+'HHH',header,58 if is64 else 46)
        minimum=64 if is64 else 40
        if size<minimum or not count or index>=count: return ''
        length=stream.seek(0,2)
        if offset+count*size>length: return ''
        def section(n):
            stream.seek(offset+n*size);data=stream.read(size)
            name=struct.unpack_from(endian+'I',data)[0]
            start,total=struct.unpack_from(endian+('QQ' if is64 else 'II'),data,24 if is64 else 16)
            if start+total>length: raise ValueError('Sezione ELF non valida')
            return name,start,total
        _,start,total=section(index)
        if total>1024*1024: return ''
        stream.seek(start);names=stream.read(total)
        for n in range(count):
            name,start,total=section(n)
            if names[name:].split(b'\0',1)[0]==b'.upd_info' and total<=65536:
                stream.seek(start);return stream.read(total).split(b'\0',1)[0].decode('utf-8')
    return ''


def enrich(item):
    path=Path(item.path)
    ancestors=[path] if path.is_dir() else [path.parent]
    # Stop before global directories so adjacent programs are never merged.
    for root in list(ancestors[0].parents):
        if root in (Path('/'),Path('/opt'),Path('/usr'),Path('/usr/local'),Path.home(),Path.home()/'.local'): break
        ancestors.append(root)
    for root in ancestors:
        managed=root/'utility-version.json'
        if managed.is_file():
            try:
                data=json.loads(managed.read_text())
                item.name=data['name'];item.version=data.get('version','');item.root=str(root);item.managed=True
                stable=data.get('original_id','')
                if re.fullmatch(r'install:[0-9a-f]{64}',stable): item.stable_id=stable
                item.provider=data.get('provider','builtin' if item.name in ('Postman','JMeter','Audacity standalone','Forge') else '')
                item.entrypoint=data.get('entrypoint','')
                item.channel=data.get('channel','snapshot' if '~snapshot' in item.version or '-SNAPSHOT' in item.version else 'stable')
                item.homepage=data.get('homepage',item.homepage)
                break
            except (OSError,ValueError,KeyError): pass
        matched=False;manifest_found=False
        for relative in ('app/resources/app/package.json','resources/app/package.json','package.json'):
            manifest=root/relative
            if not manifest.is_file(): continue
            try: data=json.loads(manifest.read_text())
            except (OSError,ValueError): continue
            if not isinstance(data,dict): continue
            if data.get('name','').lower()=='postman' and (root/'Postman').exists():
                if relative=='resources/app/package.json' and root.name=='app' and (root.parent/'Postman').exists():root=root.parent
                item.name='Postman';item.provider='builtin';item.entrypoint='Postman';matched=True
            repository=data.get('repository',{})
            repo=repository.get('url','') if isinstance(repository,dict) else repository
            if isinstance(repo,str) and repo.startswith(('https://github.com/','git+https://github.com/')): item.homepage=repo.removeprefix('git+').removesuffix('.git')
            if isinstance(data.get('version'),str):item.version=data['version'];manifest_found=True
            if isinstance(data.get('homepage'),str) and not item.homepage: item.homepage=data['homepage']
            if path.is_relative_to(root): item.root=str(root)
            if matched: break
        if matched: item.root=str(root);break
        for meta in (root/'usr/share/metainfo').glob('*.xml'):
            try:
                xml=ET.parse(meta).getroot()
                if 'audacity' in xml.findtext('id','').lower() and (root/'AppRun').exists():
                    item.name='Audacity standalone';item.provider='builtin';item.root=str(root);item.entrypoint='AppRun'
                    if root.name=='squashfs-root' and any(root.parent.glob('*.AppImage')):
                        item.root=str(root.parent);item.entrypoint='squashfs-root/AppRun'
                    release=xml.find('./releases/release')
                    if release is not None: item.version=release.get('version','')
                    matched=True;break
            except (OSError,ET.ParseError): continue
        if matched: break
        if (root/'bin/jmeter').is_file() and (root/'lib/ext/ApacheJMeter_core.jar').is_file():
            import zipfile
            try:
                with zipfile.ZipFile(root/'lib/ext/ApacheJMeter_core.jar') as jar:
                    text=jar.read('META-INF/MANIFEST.MF').decode()
                match=re.search(r'^Implementation-Version:\s*(\S+)',text,re.M)
                if match: item.version=match[1]
            except (OSError,KeyError,zipfile.BadZipFile): pass
            item.name='JMeter';item.provider='builtin';item.root=str(root);item.entrypoint='bin/jmeter';break
        if (root/'forge-adventure.sh').is_file():
            jars=list(root.glob('forge-gui-desktop-*-jar-with-dependencies.jar'))
            if len(jars)==1:
                item.version=jars[0].name.removeprefix('forge-gui-desktop-').removesuffix('-jar-with-dependencies.jar').replace('-SNAPSHOT','~snapshot')
                item.name='Forge';item.provider='builtin';item.root=str(root);item.entrypoint='forge-adventure.sh'
                item.channel='snapshot' if '~snapshot' in item.version else 'stable';break
        if (root/'lib/VERSION').is_file() and (root/'lampp').is_file():
            item.name='XAMPP';item.root=str(root);item.homepage='https://www.apachefriends.org/faq_linux.html'
            try: item.version=(root/'lib/VERSION').read_text().strip()
            except OSError: pass
            break
        if manifest_found:break
    root=Path(item.root or item.path)
    if path.suffix.lower()=='.appimage':
        try: item.update_info=appimage_update_info(path)
        except (OSError,ValueError,UnicodeError): pass
        item.root=str(path)
        item.entrypoint=''
    candidates=list((root/'usr/share/metainfo').glob('*.xml'))+list((root/'share/metainfo').glob('*.xml'))
    for manifest in candidates:
        try:
            component=ET.parse(manifest).getroot()
            if not item.version:
                release=component.find('./releases/release')
                if release is not None: item.version=release.get('version','')
            if not item.homepage: item.homepage=component.findtext("url[@type='homepage']",'')
        except (OSError,ET.ParseError): continue
    if item.name.lower().startswith('gpick') and not item.homepage: item.homepage='https://github.com/thezbyg/gpick'
    if item.package.startswith('forticlient'): item.homepage=item.homepage or 'https://repo.fortinet.com/'
    return item
