"""Validate the distributable without installing it on the host."""
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
archive=root/'dist/ubuntu-update-utility_0.3.0_all.deb'
with tempfile.TemporaryDirectory() as temp:
    temp=Path(temp)
    subprocess.run(['dpkg-deb','-x',str(archive),str(temp)],check=True)
    subprocess.run(['desktop-file-validate',str(temp/'usr/share/applications/ubuntu-update-utility.desktop')],check=True)
    policy=ET.parse(temp/'usr/share/polkit-1/actions/it.local.UbuntuUpdateUtility.policy')
    assert policy.find('.//annotate').text=='/usr/lib/ubuntu-update-utility/helper'
    assert policy.find('.//allow_active').text=='auth_admin'
    helper=temp/'usr/lib/ubuntu-update-utility/helper'
    assert helper.stat().st_mode & 0o777==0o755
    contents=subprocess.check_output(['dpkg-deb','--contents',str(archive)],text=True)
    assert 'root/root' in contents
    for name in ('runtime.py','engine.py','archives.py','packages.py','user_worker.py','sources.py'):
        installed=temp/'usr/lib/ubuntu-update-utility'/name
        assert installed.read_bytes()==(root/'ubuntu_update'/name).read_bytes(),name+' is stale'
print('Package ownership, permissions, policy, launcher and source freshness: passed')
