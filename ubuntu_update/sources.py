"""Fixed vendor sources and bounded HTTPS transfers (no user supplied URLs)."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import urllib.parse
import urllib.request

HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
         'objects.githubusercontent.com', 'desktop.docker.com', 'docs.docker.com',
         'dbeaver.io', 'downloads.dbeaver.net', 'dl.pstmn.io', 'downloads.getpostman.com', 'dlcdn.apache.org',
         'downloads.apache.org', 'jmeter.apache.org', 'www.apachefriends.org'}


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Sorgente di download non consentita')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, target=None, limit=8*1024*1024):
    request = urllib.request.Request(validate_url(url), headers={'User-Agent': 'UbuntuUpdateUtility/1.0', 'Accept': 'application/json' if 'api.github.com' in url else '*/*'})
    opener = urllib.request.build_opener(Redirect())
    with opener.open(request, timeout=30) as response:
        validate_url(response.url)
        length = response.headers.get('Content-Length')
        if length and int(length) > limit: raise ValueError('Download oltre il limite previsto')
        if target:
            if shutil.disk_usage(Path(target).parent).free < (int(length) if length else limit)+128*1024*1024:
                raise OSError('Spazio libero insufficiente per il download')
            with open(target, 'xb') as stream:
                total = 0
                while chunk := response.read(1024*1024):
                    total += len(chunk)
                    if total > limit: raise ValueError('Download troppo grande')
                    stream.write(chunk)
            return response.url
        data = response.read(limit+1)
        if len(data) > limit: raise ValueError('Risposta troppo grande')
        return data


def newer(candidate, installed):
    import subprocess
    if not candidate or not installed: return False
    return subprocess.run(['/usr/bin/dpkg', '--compare-versions', candidate, 'gt', installed], capture_output=True).returncode == 0


def release(repository):
    data = json.loads(fetch(f'https://api.github.com/repos/{repository}/releases/latest'))
    if data.get('draft') or data.get('prerelease'): raise ValueError('Release stabile non disponibile')
    return data


def github_asset(repository, pattern):
    data = release(repository)
    assets = [a for a in data['assets'] if re.fullmatch(pattern, a['name'], re.I)]
    if len(assets) != 1: raise ValueError('Pacchetto compatibile non identificato in modo univoco')
    asset = assets[0]
    digest = asset.get('digest') or ''
    sidecar = next((a for a in data['assets'] if a['name'] == asset['name']+'.sha256'), None)
    if sidecar and not digest:
        match = re.search(r'\b[a-fA-F0-9]{64}\b', fetch(sidecar['browser_download_url']).decode())
        if not match: raise ValueError('Checksum pubblicato non valido')
        digest = 'sha256:'+match[0]
    return dict(version=data['tag_name'].removeprefix('v').removeprefix('release-').removeprefix('forge-').removeprefix('Audacity-'),
                url=asset['browser_download_url'], name=asset['name'],
                sha256=digest.removeprefix('sha256:') if digest.startswith('sha256:') else '',
                page=data['html_url'])


def verify(path, digest, algorithm='sha256'):
    if not re.fullmatch('[0-9a-fA-F]{'+str(hashlib.new(algorithm).digest_size*2)+'}', digest):
        raise ValueError('Checksum non valido')
    with open(path, 'rb') as stream:
        value = hashlib.file_digest(stream, algorithm).hexdigest()
    if value.lower() != digest.lower(): raise ValueError('Checksum del download non corrispondente')


def package_source(package, arch):
    if package == 'github-desktop':
        return github_asset('shiftkey/desktop', rf'GitHubDesktop-linux-{arch}-.*\.deb')
    if package == 'teams-for-linux':
        return github_asset('IsmaelMartinez/teams-for-linux', rf'teams-for-linux_.*_{arch}\.deb')
    if package == 'dbeaver-ce':
        page = fetch('https://dbeaver.io/download/').decode()
        config = re.search(r'window.dbeaverDownloadConfig.*?(\{"schemaVersion".*?\});',page,re.S)
        if not config: raise ValueError('Indice DBeaver non identificato')
        data=json.loads(config[1]);version=data['products']['ce']['version']
        cpu='x86_64' if arch=='amd64' else 'aarch64'
        name=f'dbeaver-ce-latest-linux-{cpu}.deb'
        checksum=fetch('https://dbeaver.io/files/checksum/'+name+'.sha256').decode()
        match=re.search(r'\b[a-fA-F0-9]{64}\b',checksum)
        if not match: raise ValueError('Checksum DBeaver non disponibile')
        return dict(version=version,url='https://dbeaver.io/files/'+name,name=name,
                    page='https://dbeaver.io/download/',sha256=match[0])
    if package == 'docker-desktop':
        import xml.etree.ElementTree as ET
        if arch != 'amd64': raise ValueError('Architettura Docker Desktop non supportata')
        feed=ET.fromstring(fetch('https://desktop.docker.com/linux/main/amd64/appcast.xml'))
        enclosure=feed.find('./channel/item/enclosure')
        if enclosure is None: raise ValueError('Indice Docker non valido')
        url=enclosure.attrib['url'];validate_url(url)
        namespace='{http://www.andymatuschak.org/xml-namespaces/sparkle}'
        version=enclosure.attrib[namespace+'shortVersionString']+'-'+enclosure.attrib[namespace+'version']
        checksums=fetch(url.rsplit('/',1)[0]+'/checksums.txt').decode()
        digest=re.search(r'([a-f0-9]{64})\s+\*?docker-desktop-amd64.deb',checksums)
        if not digest: raise ValueError('Checksum Docker mancante')
        return dict(version=version,url=url,name='docker-desktop-amd64.deb',sha256=digest[1],page='https://docs.docker.com/desktop/release-notes/')
    raise ValueError('Applicazione non supportata')
