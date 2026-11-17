import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from ubuntu_update import flatpaks,local_deb,standalone,profiles
from ubuntu_update.inventory import Installation,discover,identify
from ubuntu_update.metadata import appimage_update_info
from tests_support import FakeSession

class UniversalInventory(unittest.TestCase):
    def test_distinct_copies_of_same_app(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);apps=root/'desktop';apps.mkdir()
            for folder in ('one','two'):
                binary=root/folder/'Example.AppImage';binary.parent.mkdir();binary.write_bytes(b'not executed')
                (apps/(folder+'.desktop')).write_text('[Desktop Entry]\nName=Example\nExec='+str(binary)+'\n')
            result=discover(root,[apps],[],metadata=lambda _: {})
            self.assertEqual(len(result),2);self.assertNotEqual(result[0].id,result[1].id)
    def test_known_app_at_arbitrary_location_uses_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);app=root/'arbitrary/product';(app/'app/resources/app').mkdir(parents=True)
            (app/'Postman').write_text('binary not executed')
            (app/'app/resources/app/package.json').write_text(json.dumps(dict(name='Postman',version='12.0.1')))
            apps=root/'desktop';apps.mkdir();(apps/'tool.desktop').write_text('[Desktop Entry]\nName=My tool\nExec='+str(app/'Postman')+'\n')
            result=discover(root,[apps],[],metadata=lambda _: {})
            self.assertEqual(result[0].root,str(app));self.assertEqual(result[0].provider,'builtin');self.assertEqual(result[0].version,'12.0.1')
    def test_user_hidden_entry_overrides_system(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);user=root/'user';system=root/'system';user.mkdir();system.mkdir();binary=root/'app';binary.touch()
            (user/'app.desktop').write_text('[Desktop Entry]\nHidden=true\n')
            (system/'app.desktop').write_text('[Desktop Entry]\nName=Example\nExec='+str(binary)+'\n')
            self.assertEqual(discover(root,[user,system],[],metadata=lambda _: {}),[])
    def test_elf_update_info_is_read_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'tool.AppImage';data=bytearray(512)
            data[:6]=b'\x7fELF\x02\x01';struct.pack_into('<Q',data,40,64);struct.pack_into('<HHH',data,58,64,3,1)
            names=b'\0.shstrtab\0.upd_info\0';data[300:300+len(names)]=names
            struct.pack_into('<I',data,128,1);struct.pack_into('<QQ',data,128+24,300,len(names))
            info=b'gh-releases-zsync|vendor|tool|latest|*.AppImage.zsync\0'
            struct.pack_into('<I',data,192,11);struct.pack_into('<QQ',data,192+24,350,len(info));data[350:350+len(info)]=info
            path.write_bytes(data)
            self.assertEqual(appimage_update_info(path),info[:-1].decode())
    def test_unknown_version_stays_selectable_as_assisted(self):
        item=Installation(identify('/unknown'),'Unknown','/unknown')
        session=FakeSession()
        with tempfile.TemporaryDirectory() as temp:standalone.process(session,item,False,Path(temp))
        events=[json.loads(line) for line in session.stream.getvalue().splitlines()]
        self.assertEqual(events[-1]['type'],'candidate');self.assertEqual(events[-1]['mode'],'assisted');self.assertEqual(events[-1]['available'],'Da verificare')

class FlatpakSelection(unittest.TestCase):
    def test_installations_and_branches_stay_separate(self):
        session=FakeSession();refs=[('app/org.example.App/x86_64/stable','1','2'),('app/org.example.App/x86_64/beta','2','3')]
        selected={'flatpak-user:'+refs[1][0]}
        with patch('ubuntu_update.flatpaks.pending',return_value=refs):flatpaks.process(session,'user',selected)
        self.assertEqual(session.commands,[['/usr/bin/flatpak','update','--user','-y',refs[1][0]]])
        with patch('ubuntu_update.flatpaks.pending') as pending:flatpaks.process(session,'system',selected)
        pending.assert_not_called()

class LocalDebAssistance(unittest.TestCase):
    def test_wrong_product_never_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'file.deb';path.write_bytes(b'fixture');session=FakeSession()
            with patch('ubuntu_update.local_deb.installed',return_value='1.0'),patch('subprocess.check_output',side_effect=['Package: unrelated\nVersion: 2.0\nArchitecture: amd64\n','amd64\n']):
                with self.assertRaises(ValueError):local_deb.apply(session,dict(package='example',path=str(path)),os.getuid())
            self.assertEqual(session.commands,[])
    def test_source_owner_is_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'file.deb';path.write_bytes(b'fixture')
            with patch('ubuntu_update.local_deb.installed',return_value='1.0'):
                with self.assertRaises(ValueError):local_deb.apply(FakeSession(),dict(package='example',path=str(path)),os.getuid()+1)
    def test_source_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'file.deb';path.write_bytes(b'fixture');link=Path(temp)/'link.deb';link.symlink_to(path)
            with patch('ubuntu_update.local_deb.installed',return_value='1.0'):
                with self.assertRaises(OSError):local_deb.apply(FakeSession(),dict(package='example',path=str(link)),os.getuid())

class AssistedFlow(unittest.TestCase):
    def test_opened_instructions_do_not_report_success(self):
        from ubuntu_update.assistance import run
        session=FakeSession();session.assistance=lambda item:dict(action='opened')
        with tempfile.TemporaryDirectory() as temp:
            item=Installation(identify('/app'),'Unknown','/app')
            run(session,item,Path(temp))
        self.assertEqual(session.results[-1]['status'],'intervento richiesto')
    def test_saved_source_is_per_installation(self):
        from ubuntu_update.assistance import run
        session=FakeSession();session.assistance=lambda item:dict(action='save',profile=dict(homepage='https://vendor.example/',version='1.0'))
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);item=Installation(identify('/app'),'Unknown','/app')
            run(session,item,home)
            self.assertEqual(profiles.load(home)[item.id]['version'],'1.0')
            self.assertNotIn(identify('/another-copy'),profiles.load(home))
    def test_child_forwards_confirmation_and_records_errors(self):
        from ubuntu_update.runtime import Session
        code='import json,sys;print(json.dumps({"type":"confirm","title":"Install?","detail":"details"}),flush=True);a=json.loads(sys.stdin.readline());print(json.dumps({"type":"result","category":"Test","status":"aggiornato" if a.get("approve") else "errore"}),flush=True)'
        # Child reads payload first, as the installed helper does.
        code='import sys;sys.stdin.readline();'+code
        output=io.StringIO();session=Session(output)
        with patch('sys.stdin',io.StringIO('{"approve": true}\n')):
            self.assertEqual(session.child(['/usr/bin/python3','-c',code],{'package':'test','path':'/not-opened'}),0)
        self.assertEqual(session.results[-1]['status'],'aggiornato')

class LocalDebSuccess(unittest.TestCase):
    def test_snapshot_checked_confirmed_installed_and_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'package.deb';path.write_bytes(b'fixture');session=FakeSession()
            with patch('ubuntu_update.local_deb.installed',side_effect=['1.0','2.0']),patch('subprocess.check_output',side_effect=['Package: example\nVersion: 2.0\nArchitecture: amd64\n','amd64\n']),patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'Inst example (2.0)','')):
                self.assertTrue(local_deb.apply(session,dict(package='example',path=str(path)),os.getuid()))
            self.assertEqual(session.results[-1]['status'],'aggiornato')
            self.assertFalse(Path(session.commands[0][-1]).exists())
            self.assertIn('--no-remove',session.commands[0])

class FlatpakOrigins(unittest.TestCase):
    def test_foreign_remote_cannot_replace_installed_origin(self):
        result1=subprocess.CompletedProcess([],0,'org.example.App/x86_64/stable\t1\tflathub\n','')
        result2=subprocess.CompletedProcess([],0,'org.example.App/x86_64/stable\t9\tother-remote\norg.example.App/x86_64/stable\t2\tflathub\n','')
        with patch('subprocess.run',side_effect=[result1,result2]):
            self.assertEqual(flatpaks.pending('user'),[('org.example.App/x86_64/stable','1','2')])

class PackageIdentity(unittest.TestCase):
    def test_aliases_of_same_deb_share_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);desktop=root/'desktop';desktop.mkdir()
            for name in ('main','uri'):
                path=root/name;path.touch()
                (desktop/(name+'.desktop')).write_text('[Desktop Entry]\nName=Example\nExec='+str(path)+'\n')
            found=discover(root,[desktop],[],metadata=lambda _:dict(package='example',version='1.0'))
            self.assertEqual(len(found),1)

class SourceFailureFallback(unittest.TestCase):
    def test_catalogue_network_failure_stays_selectable(self):
        item=Installation(identify('/app'),'Example','/app',package='teams-for-linux',version='1')
        session=FakeSession()
        with tempfile.TemporaryDirectory() as temp,patch('ubuntu_update.packages.update_package',side_effect=OSError('Rete assente')):
            standalone.process(session,item,False,Path(temp))
        event=json.loads(session.stream.getvalue())
        self.assertEqual(event['mode'],'assisted');self.assertEqual(event['id'],item.id)

class XdgLocations(unittest.TestCase):
    def test_associations_and_launchers_use_configured_locations(self):
        from ubuntu_update.archives import replace_launchers
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);data=home/'data';config=home/'config'
            with patch.dict(os.environ,dict(XDG_DATA_HOME=str(data),XDG_CONFIG_HOME=str(config))):
                profiles.save(identify('/example'),dict(homepage='https://vendor.example/'),home)
                replace_launchers(home,home/'old',home/'new',home/'new/tool','Example',wrapper_path='')
                self.assertTrue((config/'ubuntu-update-utility/sources.json').exists())
                self.assertTrue((data/'applications/ubuntu-update-example.desktop').exists())
    def test_relative_xdg_setting_is_ignored(self):
        from ubuntu_update.paths import data_home
        with patch.dict(os.environ,dict(XDG_DATA_HOME='relative-folder')):
            self.assertEqual(data_home(Path('/another/home')),Path('/another/home/.local/share'))
    def test_legacy_store_remains_a_recovery_root(self):
        from ubuntu_update.paths import app_roots
        with patch.dict(os.environ,dict(XDG_DATA_HOME='/custom/data')):
            roots=app_roots(Path('/another/home'))
            self.assertIn(Path('/custom/data/ubuntu-update-utility/apps'),roots)
            self.assertIn(Path('/another/home/.local/share/ubuntu-update-utility/apps'),roots)
