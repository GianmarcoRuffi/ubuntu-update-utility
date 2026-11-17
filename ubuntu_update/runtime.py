"""Structured worker protocol; confirmations never accept executable input."""
import json
import os
import subprocess
import sys

class Cancelled(Exception):
    pass

class Session:
    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.results = []
    def emit(self, event_type, **data):
        print(json.dumps(dict(type=event_type, **data), ensure_ascii=False), file=self.stream, flush=True)
    def candidate(self, identifier, name, current, available, kind):
        self.emit('candidate',id=identifier,name=name,current=current,available=available,kind=kind)
    def confirm(self, title, detail):
        self.emit('confirm', title=title, detail=detail)
        response = sys.stdin.readline()
        if not response: raise Cancelled()
        try: value = json.loads(response)
        except ValueError: return False
        if value == {'cancel': True}: raise Cancelled()
        return value == {'approve': True}
    def checkpoint(self):
        self.emit('checkpoint')
        if not sys.stdin.readline().strip() == '{"continue": true}': raise Cancelled()
    def result(self, category, status, detail=''):
        item = dict(category=category, status=status, detail=detail)
        self.results.append(item); self.emit('result', **item)
    def command(self, args, accepted=(0,), timeout=None):
        self.emit('log', text='› '+' '.join(args)+'\n')
        env = dict(os.environ, LC_ALL='C', DEBIAN_FRONTEND='noninteractive')
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env) as proc:
            for line in proc.stdout: self.emit('log', text=line)
            code = proc.wait(timeout=timeout)
        if code not in accepted: raise RuntimeError(f'{args[0]}: codice {code}')
        return code
