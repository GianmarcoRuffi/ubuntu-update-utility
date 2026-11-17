"""Validate the distributable without installing it on the host."""
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
archive=root/'dist/ubuntu-update-utility_0.5.0_all.deb'
with tempfile.TemporaryDirectory() as temp:
    temp=Path(temp)
    subprocess.run(['dpkg-deb','-x',str(archive),str(temp)],check=True)
    subprocess.run(['desktop-file-validate',str(temp/'usr/share/applications/it.local.UbuntuUpdateUtility.desktop')],check=True)
    policy=ET.parse(temp/'usr/share/polkit-1/actions/it.local.UbuntuUpdateUtility.policy')
    assert policy.find('.//annotate').text=='/usr/lib/ubuntu-update-utility/helper'
    assert policy.find('.//allow_active').text=='auth_admin'
    desktop=(temp/'usr/share/applications/it.local.UbuntuUpdateUtility.desktop').read_text()
    assert 'Icon=it.local.UbuntuUpdateUtility\n' in desktop
    assert 'StartupWMClass=it.local.UbuntuUpdateUtility\n' in desktop
    assert (temp/'usr/share/icons/hicolor/scalable/apps/it.local.UbuntuUpdateUtility.svg').is_file()
    metadata=ET.parse(temp/'usr/share/metainfo/it.local.UbuntuUpdateUtility.metainfo.xml')
    assert metadata.find('launchable').text=='it.local.UbuntuUpdateUtility.desktop'
    assert metadata.find('icon').text=='it.local.UbuntuUpdateUtility'
    helper=temp/'usr/lib/ubuntu-update-utility/helper'
    assert helper.stat().st_mode & 0o777==0o755
    contents=subprocess.check_output(['dpkg-deb','--contents',str(archive)],text=True)
    assert 'root/root' in contents
    for source in (root/'ubuntu_update').glob('*.py'):
        name=source.name
        installed=temp/'usr/lib/ubuntu-update-utility'/name
        assert installed.read_bytes()==(root/'ubuntu_update'/name).read_bytes(),name+' is stale'
print('Package ownership, permissions, policy, launcher and source freshness: passed')
