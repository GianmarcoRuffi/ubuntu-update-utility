"""Run only inside a sandbox with private APT/dpkg state and a read-only host."""
import io
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ubuntu_update import engine
from ubuntu_update.runtime import Cancelled, Session


def main():
    root = Path('/tmp/apt-review-root')
    (root/'DEBIAN').mkdir(parents=True)
    (root/'DEBIAN/control').write_text(
        'Package: review-fixture\nVersion: 1.0\nArchitecture: all\n'
        'Maintainer: Test <test@example.invalid>\nDescription: Synthetic test package\n'
    )
    deb = '/tmp/review-fixture.deb'
    subprocess.run(['dpkg-deb', '--build', str(root), deb], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['dpkg', '-i', deb], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['apt-mark', 'auto', 'review-fixture'], check=True, stdout=subprocess.DEVNULL)
    base = ['/usr/bin/apt-get', '-o', 'DPkg::Lock::Timeout=0', '-o', 'APT::Sandbox::User=root']

    class Confirmation(Session):
        def __init__(self, answer):
            super().__init__(io.StringIO())
            self.answer = answer

        def confirm(self, title, detail):
            assert 'review-fixture:all [1.0]' in detail, detail
            probe = subprocess.run(base+['autoremove','--assume-no'], capture_output=True, text=True)
            assert 'lock' in probe.stderr.lower(), probe.stderr
            if self.answer is None:
                raise Cancelled()
            return self.answer

    with patch.object(engine, 'kernel_versions_to_keep', return_value=set()):
        with patch.object(engine, 'cleanup_plan', return_value=(['review-fixture'],True)):
            assert engine.approve_apt_removals(Confirmation(False), base)[0] == 'intervento richiesto'
        assert engine.approve_apt_removals(Confirmation(False), base)[0] == 'saltato'
        try:
            engine.approve_apt_removals(Confirmation(None), base)
        except Cancelled:
            pass
        else:
            raise AssertionError('Expected cancellation')
        assert engine.approve_apt_removals(Confirmation(True), base)[0] == 'aggiornato'
        assert engine.approve_apt_removals(Confirmation(False), base)[0] == 'nessun aggiornamento'
    print('APT removal approval, lock, protected packages, rejection and cancellation passed')


if __name__ == '__main__':
    if not all(Path(path).is_mount() for path in ('/var/lib/dpkg','/var/lib/apt','/var/cache/apt','/etc/apt/apt.conf.d')):
        raise SystemExit('Private APT/dpkg mounts required')
    main()
