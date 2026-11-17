"""Exercise source association UI; all package operations remain mocked."""
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ubuntu_update.app import Utility
from ubuntu_update.inventory import identify
from gi.repository import GLib
app=Utility(autostart=False)
class Process:
    def __init__(self):self.stdin=io.StringIO()
process=Process()

def verify():
    app.event(dict(type='assistance',installation=dict(id=identify('/example'),name='Example',path='/example',version='1.0',homepage='',instructions='Verifica della fonte',profile={})),process)
    GLib.timeout_add(250,fill)
    return False

def fill():
    dialog=app.assistance_dialog
    dialog.save_button.emit('clicked')
    assert dialog.error_label.get_text(),'Empty source must remain in the dialog'
    assert process.stdin.getvalue()==''
    dialog.source_fields['homepage'].set_text('https://vendor.example/')
    dialog.save_button.emit('clicked')
    value=json.loads(process.stdin.getvalue())
    assert value['action']=='save' and value['profile']['homepage']=='https://vendor.example/'
    print('Native assisted source association, validation and response: passed',flush=True)
    app.quit();return False
GLib.timeout_add(800,verify)
app.run([])
