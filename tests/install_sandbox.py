"""Install/remove the actual DEB under an isolated dpkg root, no host changes."""
import os
from pathlib import Path
import subprocess
import tempfile
assert os.geteuid()==0
archive=Path(__file__).resolve().parents[1]/'dist/ubuntu-update-utility_0.5.2_all.deb'
with tempfile.TemporaryDirectory() as temp:
    temp=Path(temp);target=temp/'root';target.mkdir()
    args=['/usr/bin/dpkg','--root='+str(target),'--log='+str(temp/'dpkg.log'),'--force-depends']
    previous=archive.with_name('ubuntu-update-utility_0.5.1_all.deb')
    if previous.is_file():
        subprocess.run(args+['--install',str(previous)],capture_output=True,text=True,check=True)
    result=subprocess.run(args+['--install',str(archive)],capture_output=True,text=True)
    assert 'Version: 0.5.2\n' in (target/'var/lib/dpkg/status').read_text()
    assert result.returncode==0,(result.stdout,result.stderr)
    helper=target/'usr/lib/ubuntu-update-utility/helper'
    assert helper.is_file() and helper.stat().st_uid==0
    assert (target/'usr/share/applications/it.local.UbuntuUpdateUtility.desktop').is_file()
    result=subprocess.run(args+['--remove','ubuntu-update-utility'],capture_output=True,text=True)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert not helper.exists()
print('Actual DEB installation and removal in isolated dpkg root: passed (dependencies supplied by host only for other tests)')
