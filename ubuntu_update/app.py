#!/usr/bin/python3
import gi
import json
import datetime
import os
import subprocess
import threading
from pathlib import Path
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GLib, Adw

class Utility(Adw.Application):
    def __init__(self):
        super().__init__(application_id='it.local.UbuntuUpdateUtility')
        self.cancelled = False
        self.running = False
    def do_activate(self):
        if hasattr(self, 'win'):
            self.win.present(); return
        self.win = Adw.ApplicationWindow(application=self, title='Ubuntu Update Utility')
        self.win.set_default_size(940, 740)
        self.win.connect('close-request', self.close_requested)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(Adw.HeaderBar())
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('bottom','start','end'): getattr(body,'set_margin_'+side)(20)
        box.append(body)
        title = Gtk.Label(label='Aggiornamenti Ubuntu', xalign=0); title.add_css_class('title-1'); body.append(title)
        self.status = Gtk.Label(label='Pronto. FortiClient escluso dagli aggiornamenti automatici.', xalign=0, wrap=True); body.append(self.status)
        buttons = Gtk.Box(spacing=10)
        self.check = Gtk.Button(label='Controlla aggiornamenti')
        self.run = Gtk.Button(label='Aggiorna tutto'); self.run.add_css_class('suggested-action')
        self.stop = Gtk.Button(label='Annulla dopo l’operazione'); self.stop.set_sensitive(False)
        self.check.connect('clicked', lambda _: self.start(False)); self.run.connect('clicked', lambda _: self.start(True))
        self.stop.connect('clicked', lambda _: self.cancel())
        self.restore = Gtk.Button(label='Ripristina versione precedente')
        self.restore.connect('clicked',lambda _:self.start(False,restore=True))
        for button in (self.check,self.run,self.stop): buttons.append(button)
        body.append(buttons)
        body.append(self.restore)
        self.progress=Gtk.ProgressBar(show_text=True); body.append(self.progress)
        self.results=Gtk.Label(xalign=0,yalign=0,wrap=True,selectable=True)
        results_scroll=Gtk.ScrolledWindow(min_content_height=100,max_content_height=160,propagate_natural_height=True)
        results_scroll.set_child(self.results); body.append(results_scroll)
        self.view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=280); scroll.set_child(self.view)
        expander = Gtk.Expander(label='Dettagli delle operazioni', expanded=True); expander.set_child(scroll); body.append(expander)
        self.win.set_content(box); self.win.present()
    def close_requested(self, *_):
        if self.running:
            self.cancel(); return True
        return False
    def cancel(self):
        self.cancelled = True; self.stop.set_sensitive(False)
        self.status.set_text('Annullamento richiesto: attendo la fine dell’operazione corrente.')
    def append(self, text):
        buf=self.view.get_buffer(); buf.insert(buf.get_end_iter(),text)
        if buf.get_line_count()>6000:
            end=buf.get_iter_at_line(buf.get_line_count()-6000)[1]
            buf.delete(buf.get_start_iter(),end)
    def reply(self, process, message):
        try:
            process.stdin.write(json.dumps(message)+'\n'); process.stdin.flush()
        except (BrokenPipeError,ValueError): pass
    def event(self, event, process):
        kind = event.get('type')
        if kind == 'log': self.append(event['text'])
        elif kind == 'stage':
            self.status.set_text(event['category']+' in corso…')
            self.progress.set_fraction(event.get('index',0)/max(event.get('total',1),1))
            self.progress.set_text(event['category'])
        elif kind == 'checkpoint':
            self.reply(process, {'cancel':True} if self.cancelled else {'continue':True})
        elif kind == 'confirm':
            dialog = Adw.MessageDialog(transient_for=self.win,heading=event['title'],body='Controlla i dettagli prima di confermare.')
            details=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
            details.get_buffer().set_text(event['detail'])
            scroll=Gtk.ScrolledWindow(min_content_height=180,max_content_height=350,min_content_width=480)
            scroll.set_child(details); dialog.set_extra_child(scroll)
            dialog.add_response('no','Salta'); dialog.add_response('yes','Conferma'); dialog.set_default_response('no'); dialog.set_close_response('no')
            def response(_, value):
                self.reply(process, {'cancel':True} if self.cancelled else {'approve':value=='yes'})
            dialog.connect('response',response); dialog.present()
        elif kind == 'result':
            line = f"{event['category']}: {event['status']}"
            self.results.set_text(self.results.get_text()+line+'\n')
            self.append(line+'\n'+event.get('detail','')+'\n')
        elif kind == 'summary':
            self.progress.set_fraction(1)
            self.status.set_text('Completato. '+('Riavvio necessario.' if event['reboot'] else 'Controlla il riepilogo.'))
    def start(self, apply, restore=False):
        self.running = True; self.cancelled = False
        self.restore.set_sensitive(False)
        self.check.set_sensitive(False); self.run.set_sensitive(False); self.stop.set_sensitive(True)
        self.results.set_text(''); self.view.get_buffer().set_text('')
        def work():
            directory=Path(__file__).parent
            commands = [[ '/usr/bin/python3',str(directory/'user_worker.py'),'--restore']] if restore else [
                ['/usr/bin/pkexec','/usr/lib/ubuntu-update-utility/helper','--apply'] if apply else
                ['/usr/bin/python3',str(directory/'engine.py')],
                ['/usr/bin/python3',str(directory/'user_worker.py')]+(['--apply'] if apply else [])]
            state=Path.home()/'.local/state/ubuntu-update-utility'
            state.mkdir(parents=True,exist_ok=True)
            logpath=state/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.jsonl')
            try:
                with open(logpath,'x') as log:
                    os.chmod(logpath,0o600)
                    for command in commands:
                        if self.cancelled: break
                        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
                            for line in proc.stdout:
                                log.write(line); log.flush()
                                try: event = json.loads(line)
                                except ValueError: GLib.idle_add(self.append,line); continue
                                GLib.idle_add(self.event,event,proc)
                            code = proc.wait()
                        GLib.idle_add(self.append,f'\nProcesso terminato: {code}\n')
                        if code in (126,127):
                            GLib.idle_add(self.status.set_text,'Autenticazione annullata o non disponibile.'); break
                GLib.idle_add(self.append,'Registro: '+str(logpath)+'\n')
            except Exception as error: GLib.idle_add(self.append,str(error)+'\n')
            GLib.idle_add(self.finished)
        threading.Thread(target=work,daemon=True).start()
    def finished(self):
        if self.cancelled: self.status.set_text('Operazione annullata. Gli aggiornamenti già completati sono indicati nel riepilogo.')
        self.restore.set_sensitive(True)
        self.running = False; self.check.set_sensitive(True); self.run.set_sensitive(True); self.stop.set_sensitive(False)

if __name__ == '__main__': Utility().run()
