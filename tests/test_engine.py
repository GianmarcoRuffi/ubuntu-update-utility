import unittest
from ubuntu_update.engine import protected_change
class Safety(unittest.TestCase):
    def test_protected(self):
        for text in ['Remv linux-image-1', 'Purg app']:
            self.assertTrue(protected_change(text))
    def test_regular(self):
        self.assertFalse(protected_change('Inst curl (1)'))
        self.assertFalse(protected_change('Inst forticlient (1)'))

from ubuntu_update.engine import cleanup_plan
from ubuntu_update.runtime import Session, Cancelled
from unittest.mock import patch
import io

class Cleanup(unittest.TestCase):
    def test_kernel_and_utility_never_removed(self):
        for package in ('linux-image-6.17.0', 'linux-modules-6.17.0', 'ubuntu-update-utility'):
            self.assertTrue(cleanup_plan('Remv '+package)[1])
    def test_normal_cleanup_requires_candidates(self):
        self.assertEqual(cleanup_plan('Remv libunused (1.0)'), (['libunused'], False))
    def test_no_candidates(self):
        self.assertEqual(cleanup_plan('0 to remove'), ([],False))

class Protocol(unittest.TestCase):
    def test_only_explicit_confirmation(self):
        for response in ('{}\n','yes\n','{"approve": "true"}\n'):
            with patch('sys.stdin',io.StringIO(response)):
                self.assertFalse(Session(io.StringIO()).confirm('title','body'))
    def test_closed_pipe_cancels(self):
        with patch('sys.stdin',io.StringIO('')):
            with self.assertRaises(Cancelled): Session(io.StringIO()).confirm('title','body')
    def test_checkpoint_cancel(self):
        with patch('sys.stdin',io.StringIO('{"cancel": true}\n')):
            with self.assertRaises(Cancelled): Session(io.StringIO()).checkpoint()

class KernelRetention(unittest.TestCase):
    def test_running_and_reserve_protected(self):
        keep={'6.17.0-1-generic','6.17.0-2-generic'}
        for package in ('linux-image-6.17.0-1-generic','linux-modules-6.17.0-2-generic','linux-headers-6.17.0-1'):
            self.assertTrue(cleanup_plan('Remv '+package,keep)[1])
    def test_older_kernel_can_be_removed(self):
        self.assertFalse(cleanup_plan('Remv linux-image-6.17.0-1-generic',{'6.17.0-2-generic','6.17.0-3-generic'})[1])
    def test_kernel_metapackage_protected(self):
        self.assertTrue(cleanup_plan('Remv linux-image-generic',{'6.17.0-2-generic'})[1])
