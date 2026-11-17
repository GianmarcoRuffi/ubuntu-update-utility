"""Exercise real worker protocol without applying any updates."""
import json
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
for worker in ('engine.py','user_worker.py'):
    count=0
    with subprocess.Popen([sys.executable,str(root/'ubuntu_update'/worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as process:
        for line in process.stdout:
            event=json.loads(line)
            if event['type']=='checkpoint':
                process.stdin.write('{"continue": true}\n');process.stdin.flush()
            elif event['type']=='confirm':
                raise AssertionError('Read-only check must not request authorization')
            elif event['type']=='result':
                count+=1
                print(worker,event['category'],event['status'],event.get('detail','')[:150].replace('\n',' '),flush=True)
            elif event['type']=='summary':
                assert count>0
        code=process.wait()
        stderr=process.stderr.read()
        assert code in (0,1),(code,stderr)
        assert not stderr,stderr
