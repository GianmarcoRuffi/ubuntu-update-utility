"""Exercise native widgets and authentication cancellation, without updates."""
import io
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ubuntu_update.app import Utility
from gi.repository import GLib

class RejectedAuthentication:
    def __init__(self,*args,**kwargs):
        self.stdout=io.StringIO('');self.stdin=io.StringIO()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def wait(self):return 126

app=Utility()
patcher=patch('ubuntu_update.app.subprocess.Popen',RejectedAuthentication)

def finished():
    if app.running:return True
    assert app.check.get_sensitive() and app.run.get_sensitive()
    assert 'Autenticazione annullata' in app.status.get_text()
    assert 'Processo terminato: 126' in app.view.get_buffer().get_text(app.view.get_buffer().get_start_iter(),app.view.get_buffer().get_end_iter(),False)
    patcher.stop()
    print('Native GUI, category result and cancelled authentication: passed',flush=True)
    app.quit();return False

def verify():
    assert app.win.get_visible()
    assert app.check.get_sensitive() and app.run.get_sensitive()
    app.event({'type':'result','category':'APT','status':'controllato','detail':'Test grafico'},None)
    assert 'APT: controllato' in app.results.get_text()
    patcher.start();app.start(True)
    GLib.timeout_add(100,finished)
    return False

GLib.timeout_add(1000,verify)
app.run([])
