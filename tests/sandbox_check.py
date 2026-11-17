"""Validate the packaged helper under UID 0 in a private user namespace.
The host is mounted read-only; package operations and downloads are mocked.
"""
import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from ubuntu_update import engine
assert os.geteuid()==0,'Run inside bwrap user namespace'
assert Path('/run').exists()
output=io.StringIO()
with patch('sys.argv',['helper','--apply']),patch('sys.stdin',io.StringIO('{"continue": true}\n'*30)),patch('sys.stdout',output),patch('ubuntu_update.engine.apt_update',side_effect=RuntimeError('APT lock timeout')),patch('ubuntu_update.engine.shutil.which',return_value=None),patch('ubuntu_update.engine.forticlient'),patch('ubuntu_update.packages.update_package'):
    code=engine.main()
assert code==1
messages=[json.loads(line) for line in output.getvalue().splitlines()]
assert any(e['type']=='result' and e.get('category')=='APT' and e['status']=='errore' for e in messages)
assert messages[-1]['type']=='summary','An error must not suppress remaining categories or summary'
assert Path('/run/ubuntu-update-utility.lock').exists()
print('Privileged isolated workflow: passed')

import fcntl
with open('/run/ubuntu-update-utility.lock','w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    second=io.StringIO()
    with patch('sys.argv',['helper','--apply']),patch('sys.stdout',second):
        assert engine.main()==1
    events=[json.loads(line) for line in second.getvalue().splitlines()]
    assert events[-1]['type']=='result' and events[-1]['category']=='Sessione'
    assert 'già in corso' in events[-1]['detail']
print('Concurrent administrative operation rejected: passed')
