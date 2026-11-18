import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
from ubuntu_update import providers,profiles,standalone
from ubuntu_update.inventory import Installation,identify,package_identify
from tests_support import FakeSession


def image(payload=b'old'):
    data=bytearray(64);data[:4]=b'\x7fELF';data[4:6]=b'\x02\x01';data[8:11]=b'AI\x02';struct.pack_into('<H',data,18,62)
    return bytes(data)+payload

class GenericSources(unittest.TestCase):
    def test_github_filters_cpu_and_compares_versions(self):
        item=Installation('id','Example','/example.AppImage',version='1.0',homepage='https://github.com/vendor/example')
        data=dict(tag_name='v2.0',html_url=item.homepage,assets=[dict(name='example-x86_64.AppImage',browser_download_url='https://github.com/vendor/example/file',digest='sha256:'+'a'*64),dict(name='example-arm64.AppImage',browser_download_url='https://github.com/vendor/example/arm')])
        with patch('ubuntu_update.sources.release',return_value=data),patch('subprocess.check_output',return_value='amd64\n'):
            result=providers.check(item)
        self.assertTrue(result.available);self.assertEqual(result.source['sha256'],'a'*64)
    def test_ambiguous_assets_are_assisted(self):
        item=Installation('id','Example','/example.AppImage',version='1.0',homepage='https://github.com/vendor/example')
        data=dict(tag_name='v2.0',html_url=item.homepage,assets=[dict(name=n,browser_download_url='https://github.com/file') for n in ('one.AppImage','two.AppImage')])
        with patch('ubuntu_update.sources.release',return_value=data),patch('subprocess.check_output',return_value='amd64\n'):
            self.assertIn('ambiguo',providers.check(item).reason)
    def test_manifest_requires_version_and_https(self):
        item=Installation('id','Example','/example',version='1.0')
        data=dict(version='2.0',url='https://vendor.example/app.AppImage',sha256='a'*64)
        with patch('ubuntu_update.sources.fetch',return_value=json.dumps(data).encode()):
            result=providers.check(item,dict(manifest='https://vendor.example/update.json'))
        self.assertTrue(result.available);self.assertIn('vendor.example',result.source['hosts'])
        data['url']='http://vendor.example/insecure'
        with patch('ubuntu_update.sources.fetch',return_value=json.dumps(data).encode()):
            self.assertTrue(providers.check(item,dict(manifest='https://vendor.example/update.json')).reason)
    def test_missing_version_never_claims_already_updated(self):
        item=Installation('id','Example','/example.AppImage',homepage='https://github.com/vendor/example')
        data=dict(tag_name='v2.0',html_url=item.homepage,assets=[dict(name='example.AppImage',browser_download_url='https://github.com/file')])
        with patch('ubuntu_update.sources.release',return_value=data),patch('subprocess.check_output',return_value='amd64\n'):
            self.assertIn('installata',providers.check(item).reason)
    def test_zsync_detects_actual_content_change(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'app.AppImage';path.write_bytes(image())
            item=Installation(identify(path),'Example',str(path),update_info='zsync|https://vendor.example/app.zsync')
            digest=hashlib.sha1(path.read_bytes()).hexdigest()
            header=f'Filename: app.AppImage\nURL: app.AppImage\nSHA-1: {digest}\n\n'.encode()
            with patch('ubuntu_update.sources.fetch',return_value=header):self.assertFalse(providers.check(item).available)
    def test_profiles_reject_commands_and_non_https(self):
        with tempfile.TemporaryDirectory() as temp:
            for record in ({'command':'reboot'},{'homepage':'file:///etc/passwd'},{'homepage':'https://user:password@vendor.example/'},{'provider':'shell'}):
                with self.subTest(record=record),self.assertRaises(ValueError):profiles.save(identify('/app'),record,Path(temp))

class AppImageLifecycle(unittest.TestCase):
    def test_versioned_update_keeps_recovery_profile(self):
        from ubuntu_update.user_worker import restore
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            path=home/'Example.AppImage'
            path.write_bytes(image())
            item=Installation(identify(path),'Example',str(path),version='1.0',root=str(path))
            source=dict(format='appimage',name=path.name,url='https://vendor.example/app',page='https://vendor.example/',version='2.0')
            with (patch.object(providers,'check',return_value=providers.Check(source,available=True)),
                  patch('ubuntu_update.archives.running_under',return_value=False),
                  patch('subprocess.check_output',return_value='amd64'),
                  patch('ubuntu_update.sources.fetch',side_effect=lambda url,target,**kw:target.write_bytes(image(b'new')))):
                standalone.process(FakeSession(),item,True,home)
                restore(FakeSession(),home)
                self.assertEqual(path.read_bytes(),image())
                self.assertEqual(profiles.load(home)[item.id]['version'],'1.0')


class GenericInstallation(unittest.TestCase):
    def test_appimage_updates_in_place_with_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);path=home/'example.AppImage';path.write_bytes(image());path.chmod(0o755)
            item=Installation(identify(path),'Example',str(path),version='1.0',root=str(path))
            data=image(b'new');source=dict(format='appimage',name='new.AppImage',url='https://github.com/new',page='https://github.com/project',version='2.0',sha256=hashlib.sha256(data).hexdigest())
            def download(url,target,**kwargs):target.write_bytes(data)
            with patch('ubuntu_update.sources.fetch',side_effect=download),patch('ubuntu_update.archives.running_under',return_value=False),patch('subprocess.check_output',return_value='amd64\n'):
                self.assertTrue(providers.install(FakeSession(),item,source,home))
            self.assertEqual(path.read_bytes(),data);self.assertEqual(path.with_name(path.name+'.previous').read_bytes(),image())
            self.assertEqual(profiles.load(home)[item.id]['version'],'2.0')
    def test_corrupt_download_leaves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);path=home/'example.AppImage';path.write_bytes(image())
            item=Installation(identify(path),'Example',str(path),root=str(path))
            source=dict(format='appimage',name='new.AppImage',url='https://github.com/new',page='https://github.com/project',version='2.0',sha256='0'*64)
            with patch('ubuntu_update.sources.fetch',side_effect=lambda url,target,**kw:target.write_bytes(b'bad')),patch('ubuntu_update.archives.running_under',return_value=False):
                with self.assertRaises(ValueError):providers.install(FakeSession(),item,source,home)
            self.assertEqual(path.read_bytes(),image());self.assertFalse(path.with_name(path.name+'.previous').exists())
    def test_generic_archive_preserves_launcher_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);old=home/'old';(old/'bin').mkdir(parents=True);(old/'bin/legacy').write_text('old');(old/'bin/legacy').chmod(0o755)
            desktop=home/'example.desktop';desktop.write_text('[Desktop Entry]\nName=Example\nExec="'+str(old/'bin/legacy')+'" --profile "My Profile" %U\n')
            archive=home/'new.tgz'
            with tarfile.open(archive,'w:gz') as tar:
                info=tarfile.TarInfo('example/bin/example');payload=b'#!/bin/sh\ntrue\n';info.size=len(payload);info.mode=0o755;tar.addfile(info,io.BytesIO(payload))
            data=archive.read_bytes();item=Installation(identify(old),'Example',str(old/'bin/legacy'),root=str(old),desktop=str(desktop))
            source=dict(format='archive',name='new.tgz',url='https://github.com/new',page='https://github.com/project',version='2.0',entrypoint='bin/example',sha256=hashlib.sha256(data).hexdigest())
            with patch('ubuntu_update.sources.fetch',side_effect=lambda url,target,**kw:target.write_bytes(data)),patch('ubuntu_update.archives.running_under',return_value=False):
                self.assertTrue(providers.install(FakeSession(),item,source,home))
            launcher=home/'.local/share/applications/example.desktop'
            self.assertIn('"My Profile" %U',launcher.read_text());self.assertIn('"--profile"',launcher.read_text())
            self.assertEqual((old/'bin/legacy').read_text(),'old')
            from ubuntu_update.user_worker import restore
            with patch('ubuntu_update.archives.running_under',return_value=False):
                for entry in ('legacy','example'):
                    restore(FakeSession(),home)
                    self.assertIn(f'/bin/{entry}" "--profile" "My Profile" %U',launcher.read_text())

class ExecutableVerification(unittest.TestCase):
    def test_foreign_binary_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'app';data=bytearray(image());struct.pack_into('<H',data,18,183);path.write_bytes(data)
            with patch('subprocess.check_output',return_value='amd64\n'):
                with self.assertRaises(ValueError):providers.verify_executable(path)
    def test_unrecognized_file_is_not_made_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'app';path.write_text('not a binary')
            with self.assertRaises(ValueError):providers.verify_executable(path)

class GenericDebSource(unittest.TestCase):
    def test_saved_direct_deb_is_downloaded_only_after_selection(self):
        url = 'https://vendor.example/latest?format=deb'
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            item = Installation(package_identify('example'), 'Example', '/usr/bin/example', version='1.0', package='example')
            profiles.save(item.id, {'deb_url': url}, home)
            session = FakeSession()
            session.child = Mock(return_value=0)
            metadata = {'Package': 'example', 'Architecture': 'amd64', 'Version': '2.0'}

            def download(requested, target, **kwargs):
                self.assertEqual(requested, url)
                self.assertIn('vendor.example',kwargs['allowed_hosts'])
                target.write_bytes(b'deb fixture')

            with (patch('ubuntu_update.sources.fetch',side_effect=download) as fetch,
                  patch('ubuntu_update.archives.running_under',return_value=False),
                  patch('ubuntu_update.packages.deb_metadata',return_value=metadata),
                  patch('subprocess.check_output',return_value='amd64\n')):
                standalone.process(session,item,False,home)
                candidate = json.loads(session.stream.getvalue())
                self.assertEqual(candidate['mode'], 'assisted')
                fetch.assert_not_called()
                standalone.process(session,item,True,home)
                fetch.assert_called_once()
                _, payload = session.child.call_args.args
                self.assertEqual(payload['version'], '2.0')
                self.assertEqual(payload['package'], 'example')
                self.assertFalse(Path(payload['path']).exists())

                session.child.reset_mock()
                metadata['Version'] = '1.0'
                standalone.process(session,item,True,home)
                session.child.assert_not_called()
                self.assertEqual(session.results[-1]['status'], 'nessun aggiornamento')

    def test_saved_homepage_accepts_a_direct_deb_but_requires_a_source_for_a_web_page(self):
        item = Installation('id','Example','/usr/bin/example',version='1.0',package='example')
        direct = 'https://vendor.example/package.deb?latest=true'
        self.assertEqual(providers.check(item,{'homepage':direct}).source['url'],direct)
        self.assertIn('link diretto', providers.check(item,{'homepage':'https://vendor.example/download'}).reason)

    def test_unlisted_deb_application_uses_generic_github_provider(self):
        item=Installation('install:'+'a'*64,'Unlisted','/usr/bin/unlisted',version='1.0',package='unlisted',homepage='https://github.com/vendor/unlisted')
        data=dict(tag_name='v2.0',html_url=item.homepage,assets=[dict(name='unlisted_2.0_amd64.deb',browser_download_url='https://github.com/vendor/unlisted/file',digest='sha256:'+'a'*64)])
        with patch('ubuntu_update.sources.release',return_value=data),patch('subprocess.check_output',return_value='amd64\n'):
            result=providers.check(item)
        self.assertTrue(result.available);self.assertFalse(result.reason);self.assertEqual(result.source['format'],'deb')
    def test_deb_download_passes_digest_and_version_to_fixed_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);old=home/'app';old.write_text('old')
            item=Installation(identify(old),'Unlisted',str(old),package='unlisted',version='1.0')
            data=b'deb fixture';source=dict(format='deb',name='new.deb',url='https://github.com/vendor/file',page='https://github.com/vendor/project',version='2.0',sha256=hashlib.sha256(data).hexdigest())
            session=FakeSession();session.child=Mock(return_value=0)
            with patch('ubuntu_update.packages.deb_metadata',return_value=dict(Package='unlisted',Version='1:2.0-1',Architecture='amd64')), patch('ubuntu_update.providers.subprocess.check_output',return_value='amd64'), patch('ubuntu_update.sources.fetch',side_effect=lambda url,target,**kw:target.write_bytes(data)),patch('ubuntu_update.archives.running_under',return_value=False):
                self.assertTrue(providers.install(session,item,source,home))
            command,payload=session.child.call_args.args
            self.assertEqual(command,['/usr/bin/pkexec','/usr/lib/ubuntu-update-utility/helper','--local-deb'])
            self.assertEqual(payload['sha256'],source['sha256']);self.assertEqual(payload['version'],'1:2.0-1')
            self.assertFalse(Path(payload['path']).exists())

class AppImageRecovery(unittest.TestCase):
    def test_recovery_swaps_content_and_recorded_versions(self):
        from ubuntu_update.user_worker import restore
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);path=home/'app.AppImage';path.write_bytes(image(b'new'))
            backup=path.with_name(path.name+'.previous');backup.write_bytes(image(b'old'))
            profiles.save(identify(path),dict(recovery_path=str(path),version='2.0',previous_version='1.0'),home)
            with patch('ubuntu_update.archives.running_under',return_value=False),patch('subprocess.check_output',return_value='amd64\n'):
                restore(FakeSession(),home)
            self.assertEqual(path.read_bytes(),image(b'old'));self.assertEqual(backup.read_bytes(),image(b'new'))
            self.assertEqual(profiles.load(home)[identify(path)]['version'],'1.0')
