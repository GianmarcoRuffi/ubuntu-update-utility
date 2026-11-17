"""Native, non-blocking source association and downloaded-DEB chooser."""
from pathlib import Path
import re
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gio
try:
    from . import profiles
except ImportError:
    import profiles


def present(parent,installation,reply):
    record=installation.get('profile',{})
    dialog=Adw.MessageDialog(transient_for=parent,heading='Aggiornamento assistito: '+installation['name'],body='Associa una fonte verificata oppure segui le istruzioni del produttore. La selezione non avvia compilazioni o migrazioni automaticamente.')
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    text=Gtk.Label(label=installation.get('instructions',''),wrap=True,xalign=0,selectable=True)
    box.append(text)
    advanced=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
    fields={}
    for key,label,default in [
        ('homepage','Sito ufficiale (HTTPS)',record.get('homepage',installation.get('homepage',''))),
        ('version','Versione installata, se non rilevata',record.get('version',installation.get('version',''))),
        ('repository','Repository GitHub: proprietario/progetto',record.get('repository','')),
        ('asset','Nome del pacchetto della release, anche con *',record.get('asset','')),
        ('entrypoint','Eseguibile dentro l’archivio, es. bin/app',record.get('entrypoint','')),
        ('channel','Canale: stable oppure tag della release',record.get('channel',installation.get('channel','stable'))),
        ('manifest','Manifest JSON o appcast (HTTPS)',record.get('manifest',''))]:
        entry=Adw.EntryRow(title=label);entry.set_text(str(default or ''))
        fields[key]=entry
        (box if key in ('homepage','version') else advanced).append(entry)
    kind=Gtk.DropDown.new_from_strings(['Rilevamento / GitHub','Manifest JSON','Appcast XML'])
    kind.set_selected({'json':1,'appcast':2}.get(record.get('provider'),0));advanced.append(kind)
    expander=Gtk.Expander(label='Fonte di aggiornamento avanzata',expanded=bool(record.get('repository') or record.get('manifest')))
    expander.set_child(advanced);box.append(expander)
    error=Gtk.Label(wrap=True,xalign=0);error.add_css_class('error');box.append(error)
    answered=False
    def send(value):
        nonlocal answered
        if answered:return
        answered=True;reply(value);dialog.close()
    def save(_):
        try:
            data={key:entry.get_text().strip() for key,entry in fields.items() if entry.get_text().strip()}
            data['provider']=['github','json','appcast'][kind.get_selected()]
            for key in ('homepage','manifest'):
                if data.get(key):profiles.validate_url(data[key])
            if data.get('repository') and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',data['repository']):raise ValueError('Repository: inserisci proprietario/progetto.')
            if data.get('entrypoint'):
                value=Path(data['entrypoint'])
                if value.is_absolute() or '..' in value.parts:raise ValueError('L’eseguibile deve essere relativo alla cartella dell’archivio.')
            if data.get('asset') and ('/' in data['asset'] or '\\' in data['asset']):raise ValueError('Inserisci solo il nome del pacchetto, senza cartelle.')
            if not any(data.get(key) for key in ('homepage','repository','manifest')):raise ValueError('Indica almeno una fonte ufficiale.')
            for key in ('recovery_path','previous_version'):
                if record.get(key):data[key]=record[key]
            profiles.validate(data)
            send(dict(action='save',profile=data))
        except (OSError,ValueError) as exc:error.set_text(str(exc))
    actions=Gtk.Box(spacing=8)
    save_button=Gtk.Button(label='Salva fonte');save_button.connect('clicked',save);actions.append(save_button)
    open_button=Gtk.Button(label='Apri sito ufficiale')
    def open_site(_):
        try:
            url=profiles.validate_url(fields['homepage'].get_text().strip())
            Gio.AppInfo.launch_default_for_uri(url,None)
        except Exception as exc:error.set_text(str(exc))
    open_button.connect('clicked',open_site);actions.append(open_button);box.append(actions)
    if installation.get('package'):
        install_button=Gtk.Button(label='Installa un DEB già scaricato…')
        def choose(_):
            chooser=Gtk.FileChooserNative(title='Pacchetto per '+installation['package'],transient_for=parent,action=Gtk.FileChooserAction.OPEN,accept_label='Seleziona',cancel_label='Annulla')
            filter=Gtk.FileFilter();filter.set_name('Pacchetti Debian');filter.add_pattern('*.deb');chooser.add_filter(filter)
            def chosen(widget,response):
                if response==Gtk.ResponseType.ACCEPT:
                    file=widget.get_file();path=file.get_path() if file else None
                    if path:send(dict(action='deb',path=path))
                chooser.destroy()
            chooser.connect('response',chosen);chooser.show()
        install_button.connect('clicked',choose);box.append(install_button)
    scroll=Gtk.ScrolledWindow(min_content_height=300,max_content_height=520,min_content_width=580)
    scroll.set_child(box);dialog.set_extra_child(scroll)
    dialog.add_response('skip','Salta');dialog.add_response('cancel','Annulla operazione');dialog.set_close_response('skip')
    dialog.connect('response',lambda _,response:send({'cancel':True} if response=='cancel' else dict(action='skip')))
    # Exposed for the native smoke test, not persisted as application state.
    dialog.source_fields=fields;dialog.save_button=save_button;dialog.error_label=error
    dialog.present();return dialog
