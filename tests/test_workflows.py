import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from ubuntu_update import engine, archives
from ubuntu_update.runtime import Session

class FakeSession(Session):
    def __init__(self, approve=True):
        super().__init__(io.StringIO());self.commands=[];self.approve=approve
    def command(self,args,**kwargs): self.commands.append(args);return 0
    def confirm(self,*args):return self.approve
    def checkpoint(self):pass

class Workflows(unittest.TestCase):
    def test_no_cleanup_after_failed_upgrade(self):
        s=FakeSession()
        def command(args,**kwargs):
            s.commands.append(args)
            if 'upgrade' in args:raise RuntimeError('APT occupato')
        s.command=command
        with tempfile.TemporaryDirectory() as temp,patch('ubuntu_update.engine.capture',return_value='Inst curl (1)'),patch('ubuntu_update.engine.tempfile.TemporaryDirectory',return_value=tempfile.TemporaryDirectory(dir=temp)):
            with self.assertRaises(RuntimeError):engine.apt_update(s)
        self.assertFalse(any('autoclean' in cmd or 'clean' in cmd or 'autoremove' in cmd for cmd in s.commands))
    def test_cleanup_confirmation_rejected(self):
        s=FakeSession(False)
        with tempfile.TemporaryDirectory() as temp,patch('ubuntu_update.engine.kernel_versions_to_keep',return_value={'6.17.0-1-generic'}),patch('ubuntu_update.engine.capture',side_effect=['Inst curl (1)','Remv libunused (1)']),patch('ubuntu_update.engine.tempfile.TemporaryDirectory',return_value=tempfile.TemporaryDirectory(dir=temp)):
            engine.apt_update(s)
        self.assertFalse(any('autoremove' in cmd for cmd in s.commands))
    def test_vpn_is_a_regular_apt_package(self):
        self.assertFalse(engine.protected_change('Inst forticlient (8.0)'))
    def test_firmware_refusal(self):
        s=FakeSession(False)
        r=subprocess.CompletedProcess([],0,'Firmware update; requires reboot','')
        with patch('subprocess.run',return_value=r):engine.firmware(s)
        self.assertFalse(any('update' in cmd for cmd in s.commands))
    def test_snap_hold_respected(self):
        s=FakeSession()
        r=subprocess.CompletedProcess([],0,'forever','')
        with patch('subprocess.run',return_value=r):engine.snap_update(s,True)
        self.assertEqual(s.commands,[])
    def test_restore_keeps_both_versions(self):
        from ubuntu_update.user_worker import restore
        s=FakeSession()
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);base=home/'.local/share/ubuntu-update-utility/apps';base.mkdir(parents=True)
            for name,value in [('app','new'),('app.previous','old')]:
                folder=base/name;folder.mkdir();(folder/'version').write_text(value)
            with patch('ubuntu_update.archives.running_under',return_value=False):restore(s,home)
            self.assertEqual((base/'app/version').read_text(),'old')
            self.assertEqual((base/'app.previous/version').read_text(),'new')

class PackageLifecycle(unittest.TestCase):
    def test_discord_resolves_official_deb_and_installs_selected_version(self):
        from ubuntu_update import packages, sources, standalone
        from ubuntu_update.inventory import Installation, package_identify

        session = FakeSession()
        item = Installation(package_identify('discord'), 'Discord', '/usr/bin/discord', version='1.0.168', package='discord')
        cdn = 'https://stable.dl2.discordapp.net/distro/app/stable/linux/x64/1.0.169/Discord.deb'

        def download(url, target, **kwargs):
            self.assertEqual(url, cdn)
            self.assertEqual(kwargs['allowed_hosts'], sources.DISCORD_CDNS)
            target.write_bytes(b'deb fixture')

        original_run = subprocess.run

        def simulate(args, **kwargs):
            if args[0] == '/usr/bin/apt-get':
                return subprocess.CompletedProcess(args, 0, 'Inst discord (1.0.169)', '')
            return original_run(args, **kwargs)

        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(sources, 'open_url') as request,
            patch.object(sources, 'fetch', side_effect=download) as fetch,
            patch.object(packages, 'installed', side_effect=['1.0.168', '1.0.168', '1.0.169']),
            patch.object(packages, 'repository_managed', return_value=False),
            patch.object(packages, 'app_running', return_value=False),
            patch('subprocess.check_output', side_effect=['amd64\n','amd64\n','Package: discord\nVersion: 1.0.169\nArchitecture: amd64\n']),
            patch('subprocess.run', side_effect=simulate),
            patch.object(session, 'confirm', return_value=True) as confirm,
        ):
            request.return_value.__enter__.return_value.url = cdn
            standalone.process(session,item,False,Path(temp))
            self.assertIn('"id": "deb:discord"',session.stream.getvalue())
            fetch.assert_not_called()
            packages.update_package(session,'discord',True)
            self.assertEqual(request.call_args.kwargs['method'], 'HEAD')
            confirm.assert_called_once()
        self.assertEqual(session.results[-1]['status'], 'aggiornato')
        self.assertFalse(Path(session.commands[0][-1]).exists())

    def test_discord_rejects_an_unexpected_download_target(self):
        from ubuntu_update import sources

        for url in ('https://outside.example/Discord.deb',
                    'https://stable.dl2.discordapp.net/distro/app/canary/linux/x64/1.0.169/Discord.deb'):
            with self.subTest(url=url), patch.object(sources,'open_url') as request:
                request.return_value.__enter__.return_value.url = url
                with self.assertRaises(ValueError):
                    sources.package_source('discord','amd64')

    def test_verified_deb_installs_and_download_is_removed(self):
        from ubuntu_update import packages
        s=FakeSession()
        source=dict(version='9.0',name='app.deb',url='https://github.com/a/b',sha256='digest',page='https://github.com/a')
        def download(url,target,**kwargs):target.write_bytes(b'deb fixture')
        with patch('ubuntu_update.packages.installed',side_effect=['1.0','9.0']),patch('ubuntu_update.packages.repository_managed',return_value=False),patch('ubuntu_update.packages.app_running',return_value=False),patch('ubuntu_update.sources.package_source',return_value=source),patch('ubuntu_update.sources.fetch',side_effect=download),patch('ubuntu_update.sources.verify'),patch('subprocess.check_output',side_effect=['amd64\n','Package: teams-for-linux\nVersion: 9.0\nArchitecture: amd64\n']),patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'Inst teams-for-linux (9.0)','')):
            packages.update_package(s,'teams-for-linux',True)
        self.assertEqual(s.results[-1]['status'],'aggiornato')
        self.assertIn('--no-remove',s.commands[0])
        self.assertFalse(Path(s.commands[0][-1]).exists())
    def test_wrong_product_never_installed(self):
        from ubuntu_update import packages
        s=FakeSession()
        source=dict(version='9.0',name='app.deb',url='https://github.com/a/b',sha256='digest',page='https://github.com/a')
        def download(url,target,**kwargs):target.write_bytes(b'deb fixture')
        with patch('ubuntu_update.packages.installed',return_value='1.0'),patch('ubuntu_update.packages.repository_managed',return_value=False),patch('ubuntu_update.packages.app_running',return_value=False),patch('ubuntu_update.sources.package_source',return_value=source),patch('ubuntu_update.sources.fetch',side_effect=download),patch('ubuntu_update.sources.verify'),patch('subprocess.check_output',side_effect=['amd64\n','Package: unexpected\nVersion: 9.0\nArchitecture: amd64\n']):
            with self.assertRaises(ValueError):packages.update_package(s,'teams-for-linux',True)
        self.assertEqual(s.commands,[])

class SnapPolicies(unittest.TestCase):
    def test_targeted_refresh_does_not_override_per_app_hold(self):
        s=FakeSession()
        empty=subprocess.CompletedProcess([],1,'','not configured')
        with patch('subprocess.run',return_value=empty),patch('ubuntu_update.engine.capture',side_effect=[
            'timer: 00:00~24:00/4\nhold: -\n',
            'Name Version Rev Tracking Publisher Notes\nheld-app 1 1 latest/stable vendor held\nnormal-app 1 1 latest/stable vendor -\n',
            'Name Version Rev Size Publisher Notes\nheld-app 2 2 1MB vendor -\nnormal-app 2 2 1MB vendor -\n',
            'Name Version Rev Tracking Publisher Notes\nnormal-app 0 1 latest/stable vendor disabled\nnormal-app 1 2 latest/stable vendor disabled\nnormal-app 2 3 latest/stable vendor -\n']):
            engine.snap_update(s,True)
        self.assertIn(['/usr/bin/snap','refresh','normal-app'],s.commands)
        self.assertNotIn(['/usr/bin/snap','refresh','held-app'],s.commands)
        with patch('ubuntu_update.engine.capture',return_value='Name Version Rev Tracking Publisher Notes\nnormal-app 0 1 latest/stable vendor disabled\nnormal-app 1 2 latest/stable vendor disabled\nnormal-app 2 3 latest/stable vendor -\n'):
            engine.snap_cleanup(s,{'normal-app'})
        self.assertIn(['/usr/bin/snap','remove','normal-app','--revision=1'],s.commands)
        self.assertNotIn(['/usr/bin/snap','remove','normal-app','--revision=2'],s.commands)
