import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ubuntu_update import engine, user_worker
from ubuntu_update.selection import read_selection
from tests_support import FakeSession

class SelectionProtocol(unittest.TestCase):
    def test_valid_deduplicated_identifiers(self):
        value={'selected':['snap:firefox','archive:Forge','deb:teams-for-linux','snap:firefox']}
        self.assertEqual(read_selection(io.StringIO(json.dumps(value))),set(value['selected']))
    def test_rejects_commands_paths_unknown_packages(self):
        for value in ['snap:foo;reboot','deb:bash','archive:/tmp/foo','snap:--help','APT:curl',42]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_selection(io.StringIO(json.dumps({'selected':[value]})))
    def test_rejects_invalid_shape(self):
        for data in ({'selected':'firefox'},{'selected':[], 'command':'reboot'},[],None):
            with self.assertRaises(ValueError): read_selection(io.StringIO(json.dumps(data)))

class SelectedWorkers(unittest.TestCase):
    def test_root_only_runs_selected_deb(self):
        session=FakeSession()
        data=io.StringIO(json.dumps({'selected':['deb:teams-for-linux','archive:Forge']})+'\n')
        with patch('sys.argv',['helper','--selected']),patch('sys.stdin',data),patch('ubuntu_update.engine.os.geteuid',return_value=0),patch('ubuntu_update.engine.open',return_value=io.StringIO(),create=True),patch('fcntl.flock'),patch('ubuntu_update.engine.Session',return_value=session),patch('ubuntu_update.engine.apt_update') as apt,patch('ubuntu_update.engine.snap_update') as snap,patch('ubuntu_update.packages.update_package') as packages:
            self.assertEqual(engine.main(),0)
        apt.assert_not_called();snap.assert_not_called()
        packages.assert_called_once_with(session,'teams-for-linux',True)
    def test_empty_selection_does_nothing(self):
        session=FakeSession()
        with patch('sys.argv',['helper','--selected']),patch('sys.stdin',io.StringIO('{"selected":[]}\n')),patch('ubuntu_update.engine.os.geteuid',return_value=0),patch('ubuntu_update.engine.open',return_value=io.StringIO(),create=True),patch('fcntl.flock'),patch('ubuntu_update.engine.Session',return_value=session),patch('ubuntu_update.engine.apt_update') as apt,patch('ubuntu_update.packages.update_package') as packages:
            self.assertEqual(engine.main(),0)
        apt.assert_not_called();packages.assert_not_called();self.assertEqual(session.commands,[])
    def test_user_only_runs_selected_archive(self):
        session=FakeSession()
        items=[dict(name='Forge',version='1',path=Path('/forge')),dict(name='Postman',version='1',path=Path('/postman'))]
        with tempfile.TemporaryDirectory() as temp,patch('pathlib.Path.home',return_value=Path(temp)),patch('sys.argv',['worker','--selected']),patch('sys.stdin',io.StringIO('{"selected":["archive:Forge","snap:firefox"]}\n')),patch('ubuntu_update.user_worker.os.geteuid',return_value=1001),patch('ubuntu_update.user_worker.Session',return_value=session),patch('ubuntu_update.user_worker.discover',return_value=items),patch('ubuntu_update.user_worker.update') as update,patch('ubuntu_update.user_worker.special_apps') as special:
            self.assertEqual(user_worker.main(),0)
            update.assert_called_once_with(session,items[0],True,Path(temp))
        special.assert_not_called();self.assertEqual(session.commands,[])
    def test_clean_root_does_not_install_anything(self):
        session=FakeSession()
        with patch('sys.argv',['helper','--clean']),patch('ubuntu_update.engine.os.geteuid',return_value=0),patch('ubuntu_update.engine.open',return_value=io.StringIO(),create=True),patch('fcntl.flock'),patch('ubuntu_update.engine.Session',return_value=session),patch('ubuntu_update.engine.shutil.which',return_value='/binary'),patch('ubuntu_update.engine.apt_update') as update,patch('ubuntu_update.engine.apt_cleanup') as clean,patch('ubuntu_update.engine.installer_cleanup'),patch('ubuntu_update.engine.snap_cleanup') as snap,patch('ubuntu_update.packages.update_package') as packages:
            self.assertEqual(engine.main(),0)
        update.assert_not_called();packages.assert_not_called()
        clean.assert_called_once();snap.assert_called_once()
        self.assertEqual(session.commands,[['/usr/bin/flatpak','uninstall','--system','--unused','-y']])
    def test_user_clean_preserves_backups_and_unrelated_data(self):
        session=FakeSession()
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);base=home/'.local/share/ubuntu-update-utility/apps'
            for name in ('.staging-old','forge','forge.previous'):
                (base/name).mkdir(parents=True);(base/name/'data').write_text('keep')
            cache=home/'.cache/ubuntu-update-utility';cache.mkdir(parents=True)
            unrelated=home/'.cache/other';unrelated.mkdir();(unrelated/'data').write_text('keep')
            with patch('shutil.which',return_value=None):user_worker.clean_user(session,home)
            self.assertFalse((base/'.staging-old').exists());self.assertFalse(cache.exists())
            for name in ('forge','forge.previous'):self.assertTrue((base/name/'data').exists())
            self.assertTrue((unrelated/'data').exists())

if __name__=='__main__':unittest.main()

class InstallerCleanup(unittest.TestCase):
    def test_only_private_owned_utility_installers_are_removed(self):
        import os
        session=FakeSession()
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            managed=folder/'ubuntu-update-deb-abcdefgh';managed.mkdir(mode=0o700)
            unsafe=folder/'ubuntu-update-deb-ijklmnop';unsafe.mkdir();unsafe.chmod(0o777)
            unrelated=folder/'otherinstaller';unrelated.mkdir()
            link=folder/'ubuntu-update-deb-12345678';link.symlink_to(unrelated,target_is_directory=True)
            # Ownership is enforced in production; emulate only the private root folder.
            original=Path.lstat
            def owner(path):
                info=original(path)
                if path==managed:
                    import types
                    return types.SimpleNamespace(st_uid=0,st_mode=info.st_mode)
                return info
            with patch('pathlib.Path.lstat',owner):engine.installer_cleanup(session,[(folder,'ubuntu-update-deb-')])
            self.assertFalse(managed.exists())
            self.assertTrue(unsafe.exists());self.assertTrue(unrelated.exists());self.assertTrue(link.is_symlink())

class DiscoveryEvents(unittest.TestCase):
    def test_candidate_serializes_kind_without_protocol_collision(self):
        from ubuntu_update.runtime import Session
        output=io.StringIO()
        Session(output).candidate('archive:Forge','Forge','1','2','Standalone')
        event=json.loads(output.getvalue())
        self.assertEqual(event['type'],'candidate');self.assertEqual(event['kind'],'Standalone')
    def test_snap_candidates_include_versions_and_skip_held(self):
        from ubuntu_update.runtime import Session
        output=io.StringIO();session=Session(output)
        with patch('ubuntu_update.engine.capture',side_effect=[
            'Name Version Rev Size Publisher Notes\nfirefox 2 2 1MB vendor -\nheld-app 2 2 1MB vendor -\n',
            'Name Version Rev Tracking Publisher Notes\nfirefox 1 1 stable vendor -\nheld-app 1 1 stable vendor held\n']):engine.snap_update(session,False)
        candidates=[json.loads(line) for line in output.getvalue().splitlines() if json.loads(line)['type']=='candidate']
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['id'],'snap:firefox')
        self.assertEqual(candidates[0]['current'],'1');self.assertEqual(candidates[0]['available'],'2')

class SnapSelection(unittest.TestCase):
    def test_unchecked_available_snap_is_not_refreshed(self):
        session=FakeSession()
        result=type('Result',(),{'stdout':''})()
        with patch('subprocess.run',return_value=result),patch('ubuntu_update.engine.capture',side_effect=[
            'timer: 00:00~24:00/4\nhold: -\n',
            'Name Version Rev Tracking Publisher Notes\none 1 1 stable vendor -\ntwo 1 1 stable vendor -\n',
            'Name Version Rev Size Publisher Notes\none 2 2 1MB vendor -\ntwo 2 2 1MB vendor -\n']):
            engine.snap_update(session,True,{'snap:one'})
        self.assertEqual(session.commands,[['/usr/bin/snap','refresh','one']])
