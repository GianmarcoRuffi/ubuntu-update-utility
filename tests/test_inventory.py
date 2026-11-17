from pathlib import Path
import tempfile
import unittest
from ubuntu_update.inventory import discover, identify, executable

class Inventory(unittest.TestCase):
    def test_other_home_and_duplicate_launchers(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);apps=home/'launchers';apps.mkdir();binary=home/'custom/forticlient';binary.parent.mkdir();binary.write_text('not executed')
            for name in ('one','two'):
                (apps/(name+'.desktop')).write_text('[Desktop Entry]\nName=FortiClient\nType=Application\nExec="'+str(binary)+'" %U\n')
            found=discover(home,[apps],[],metadata=lambda p:{})
            self.assertEqual(len(found),1);self.assertEqual(found[0].name,'FortiClient')
            self.assertEqual(found[0].id,identify(binary))
    def test_apt_is_separate_and_unknown_apps_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);apps=home/'launchers';apps.mkdir()
            for name in ('aptapp','unknown'):
                binary=home/name;binary.write_text('data')
                (apps/(name+'.desktop')).write_text('[Desktop Entry]\nName='+name+'\nExec='+str(binary)+'\n')
            found=discover(home,[apps],[],metadata=lambda p:{'manager':'apt'} if p.name=='aptapp' else {})
            self.assertEqual([i.name for i in found],['unknown'])
    def test_shell_text_is_not_executed(self):
        self.assertIsNone(executable('does-not-exist ; touch /tmp/not-created'))

class ApplicationEvidence(unittest.TestCase):
    def test_library_directories_are_not_applications(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);apps=root/'apps';apps.mkdir()
            library=apps/'lib64';library.mkdir();file=library/'libexample.so';file.write_bytes(b'\x7fELF');file.chmod(0o755)
            app=apps/'example';(app/'bin').mkdir(parents=True);exe=app/'bin/example';exe.write_bytes(b'#!/bin/sh\n');exe.chmod(0o755)
            found=discover(root,[],[apps],metadata=lambda p:{})
            self.assertEqual([i.name for i in found],['example'])
