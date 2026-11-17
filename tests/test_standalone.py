import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from ubuntu_update import archives, sources, packages

class StandaloneSafety(unittest.TestCase):
    def test_versions(self):
        self.assertTrue(sources.newer('2.0.16','2.0.15~snapshot'))
        self.assertFalse(sources.newer('2.0.15','2.0.16'))
        self.assertFalse(sources.newer('1.0','1.0'))
        self.assertTrue(sources.newer('3.4.13-linux2','3.4.13-linux1'))
    def test_sources_reject_untrusted_urls(self):
        for url in ('http://github.com/a','https://github.com.evil.test/a','https://user:pass@github.com/a','file:///etc/passwd','https://github.com:444/a'):
            with self.assertRaises(ValueError): sources.validate_url(url)
    def test_bad_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'download';path.write_bytes(b'corrupt')
            with self.assertRaises(ValueError): sources.verify(path,'0'*64)
            sources.verify(path,hashlib.sha256(b'corrupt').hexdigest())
    def test_archive_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);archive=temp/'bad.tar'
            with tarfile.open(archive,'w') as tar:
                info=tarfile.TarInfo('../escape');info.size=1;tar.addfile(info,io.BytesIO(b'x'))
            with self.assertRaises(tarfile.FilterError): archives.safe_extract(archive,temp/'out')
            self.assertFalse((temp/'escape').exists())
    def test_archive_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);archive=temp/'bad.tar'
            with tarfile.open(archive,'w') as tar:
                info=tarfile.TarInfo('link');info.type=tarfile.SYMTYPE;info.linkname='/etc';tar.addfile(info)
            with self.assertRaises(tarfile.FilterError): archives.safe_extract(archive,temp/'out')
    def test_activation_keeps_old(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);old=temp/'app';old.mkdir();(old/'data').write_text('old')
            new=temp/'new';new.mkdir();(new/'data').write_text('new')
            archives.activate(new,old)
            self.assertEqual((old/'data').read_text(),'new')
            self.assertEqual((temp/'app.previous/data').read_text(),'old')
    def test_activation_failure_restores_original(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);old=temp/'app';old.mkdir();(old/'data').write_text('original')
            with self.assertRaises(FileNotFoundError): archives.activate(temp/'missing',old)
            self.assertEqual((old/'data').read_text(),'original')
    def test_launcher_keeps_custom_options(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);wrapper=home/'.local/bin/apache-jmeter-gui';wrapper.parent.mkdir(parents=True)
            wrapper.write_text('#!/bin/sh\nexport JAVA_HOME=/jdk\nexec /opt/apache-jmeter-1/bin/jmeter -t "my suite.jmx" "$@"\n')
            archives.replace_launchers(home,Path('/opt/apache-jmeter-1'),Path('/new'),Path('/new/bin/jmeter'),'JMeter')
            self.assertIn('JAVA_HOME=/jdk',wrapper.read_text())
            self.assertIn('exec /new/bin/jmeter -t "my suite.jmx" "$@"',wrapper.read_text())
            self.assertIn('/opt/apache-jmeter-1',wrapper.with_name(wrapper.name+'.previous').read_text())
    def test_repo_avoids_duplicate_updates(self):
        result=type('Result',(),{'stdout':'    500 https://vendor.test/repo stable/main amd64 Packages\n'})()
        with patch('subprocess.run',return_value=result): self.assertTrue(packages.repository_managed('test'))
    def test_missing_repo_detected(self):
        result=type('Result',(),{'stdout':'    100 /var/lib/dpkg/status\n'})()
        with patch('subprocess.run',return_value=result): self.assertFalse(packages.repository_managed('test'))

if __name__=='__main__':unittest.main()

class ArchiveWorkflow(unittest.TestCase):
    def test_jmeter_update_and_recovery_preserve_options_and_data(self):
        from tests_support import FakeSession
        from ubuntu_update.user_worker import restore
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);old=home/'original';(old/'bin').mkdir(parents=True)
            (old/'bin/jmeter').write_text('old executable')
            (old/'bin/user.properties').write_text('custom=value')
            wrapper=home/'.local/bin/apache-jmeter-gui';wrapper.parent.mkdir(parents=True)
            wrapper.write_text('#!/bin/sh\nexec '+str(old)+'/bin/jmeter -t suite.jmx "$@"')
            tarpath=home/'fixture.tgz'
            with tarfile.open(tarpath,'w:gz') as tar:
                content=b'new executable';info=tarfile.TarInfo('apache-jmeter-9.0/bin/jmeter');info.mode=0o755;info.size=len(content);tar.addfile(info,io.BytesIO(content))
            data=tarpath.read_bytes()
            source=dict(version='9.0',url='https://dlcdn.apache.org/fixture',name='fixture.tgz',sha256=hashlib.sha256(data).hexdigest(),page='https://jmeter.apache.org/')
            def download(url,target,**kwargs):target.write_bytes(data)
            session=FakeSession()
            with patch('ubuntu_update.archives.source_for',return_value=source),patch('ubuntu_update.archives.running_under',return_value=False),patch('ubuntu_update.sources.fetch',side_effect=download):
                archives.update(session,dict(name='JMeter',version='1.0',path=old),True,home)
            base=home/'.local/share/ubuntu-update-utility/apps/jmeter'
            self.assertEqual((base/'bin/jmeter').read_text(),'new executable')
            self.assertEqual((base/'bin/user.properties').read_text(),'custom=value')
            self.assertEqual((base.with_name('jmeter.previous')/'bin/jmeter').read_text(),'old executable')
            self.assertTrue((old/'bin/jmeter').exists())
            self.assertIn('-t suite.jmx "$@"',wrapper.read_text())
            with patch('ubuntu_update.archives.running_under',return_value=False):restore(session,home)
            self.assertEqual((base/'bin/jmeter').read_text(),'old executable')
    def test_no_network_leaves_existing_installation_intact(self):
        from tests_support import FakeSession
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);old=home/'app';old.mkdir();(old/'data').write_text('keep')
            with patch('ubuntu_update.archives.source_for',side_effect=OSError('Rete assente')):
                with self.assertRaises(OSError):archives.update(FakeSession(),dict(name='Postman',version='1',path=old),True,home)
            self.assertEqual((old/'data').read_text(),'keep')
    def test_running_application_not_replaced(self):
        from tests_support import FakeSession
        session=FakeSession()
        with patch('ubuntu_update.archives.source_for',return_value=dict(version='9')),patch('ubuntu_update.archives.running_under',return_value=True):
            archives.update(session,dict(name='Forge',version='1',path=Path('/not-real')),True,Path('/not-real'))
        self.assertEqual(session.results[-1]['status'],'intervento richiesto')
    def test_insufficient_disk_space(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);archive=temp/'large.tar'
            with tarfile.open(archive,'w') as tar:
                info=tarfile.TarInfo('file');info.size=4;tar.addfile(info,io.BytesIO(b'data'))
            with patch('shutil.disk_usage',return_value=type('Usage',(),{'free':0})()):
                with self.assertRaises(OSError):archives.safe_extract(archive,temp/'out')
            self.assertFalse((temp/'out/file').exists())
