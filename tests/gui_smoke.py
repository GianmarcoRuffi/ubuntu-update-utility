"""Native selection/layout/summary and auth-cancellation smoke; no updates."""
import io
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ubuntu_update.app import Utility, ICON, build_commands
from gi.repository import GLib, Gtk

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
    assert app.check.get_sensitive()
    assert 'Autenticazione annullata' in app.status.get_text()
    assert app.last_summary is not None
    patcher.stop()
    app.last_summary.response('close')
    print('Native split layout, app icon, checkboxes, selective commands, final summary and cancelled auth: passed',flush=True)
    app.quit();return False

def verify():
    assert app.win.get_visible()
    assert app.panes.get_orientation()==Gtk.Orientation.HORIZONTAL
    assert Gtk.IconTheme.get_for_display(app.win.get_display()).has_icon(ICON)
    assert not app.run.get_sensitive()
    for identifier,name in [('archive:Forge','Forge'),('snap:demo-app','demo-app')]:
        app.event(dict(type='candidate',id=identifier,name=name,current='1',available='2',kind='Snap' if identifier.startswith('snap:') else 'Standalone'),None)
    assert not app.rows,'Rows must appear only when discovery has finished'
    app.finished()
    assert len(app.rows)==2 and not app.run.get_sensitive()
    app.rows['archive:Forge'].set_active(True)
    assert app.run.get_sensitive() and app.selected_ids()==['archive:Forge']
    assert app.all_check.get_inconsistent()
    commands=build_commands(Path('/sample'),'selected',app.selected_ids())
    assert len(commands)==1 and 'user_worker.py' in commands[0][1]
    app.all_check.set_active(True)
    assert len(app.selected_ids())==2
    assert not app.all_check.get_inconsistent()
    app.action='selected';app.outcomes=[]
    app.event(dict(type='result',category='Forge',status='aggiornato',detail='2'),None)
    app.event(dict(type='result',category='Snap: demo-app',status='errore',detail='Test errore'),None)
    app.event(dict(type='summary',reboot=False),None)
    assert app.last_summary is None,'No modal before all phases finish'
    app.finished()
    dialog=app.last_summary
    view=dialog.get_extra_child().get_child();buf=view.get_buffer()
    text=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
    assert 'Aggiornati / eseguiti' in text and 'Falliti' in text and 'Test errore' in text
    assert 'archive:Forge' not in app.rows and 'snap:demo-app' in app.rows
    dialog.response('close')
    patcher.start();app.start(action='system')
    GLib.timeout_add(100,finished)
    return False

GLib.timeout_add(1000,verify)
app.run([])
