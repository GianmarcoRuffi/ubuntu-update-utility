#!/usr/bin/python3
"""Native desktop UI: discover, select, update, then summarize both workers."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GLib, Adw, Gio

ICON = 'it.local.UbuntuUpdateUtility'
GLib.set_application_name('Ubuntu Update Utility')
GLib.set_prgname(ICON)


def build_commands(directory, action, selected):
    user = ['/usr/bin/python3', str(directory / 'user_worker.py')]
    root = ['/usr/bin/pkexec', '/usr/lib/ubuntu-update-utility/helper']
    if action == 'scan':
        return [['/usr/bin/python3', str(directory / 'engine.py')], user]
    if action == 'selected':
        commands = []
        if any(i.startswith(('snap:', 'deb:')) for i in selected):
            commands.append(root + ['--selected'])
        if any(i.startswith('archive:') for i in selected):
            commands.append(user + ['--selected'])
        return commands
    if action == 'clean':
        return [root + ['--clean'], user + ['--clean']]
    if action == 'system':
        return [root + ['--system'], user + ['--system']]
    if action == 'restore':
        return [user + ['--restore']]
    raise ValueError('Operazione non riconosciuta')


def desktop_icon(candidate):
    name = candidate['name'].lower().replace('-ce', '').replace(' standalone', '')
    aliases = {'github-desktop': 'github desktop', 'teams-for-linux': 'teams', 'docker-desktop': 'docker'}
    needle = aliases.get(name, name).replace('-', ' ')
    for info in Gio.AppInfo.get_all():
        identifier = (info.get_id() or '').lower()
        display = info.get_display_name().lower().replace('-', ' ')
        if needle in display or (candidate['kind'] == 'Snap' and identifier.startswith(name + '_')):
            icon = info.get_icon()
            if icon:
                return icon
    return Gio.ThemedIcon.new('application-x-executable')


class Utility(Adw.Application):
    def __init__(self):
        super().__init__(application_id=ICON)
        self.cancelled = False
        self.running = False
        self.candidates = {}
        self.rows = {}
        self.outcomes = []
        self.reboot = False
        self.action = 'scan'
        self.last_summary = None

    def do_activate(self):
        if hasattr(self, 'win'):
            self.win.present()
            return
        self.win = Adw.ApplicationWindow(application=self, title='Ubuntu Update Utility')
        self.win.set_default_size(1120, 760)
        self.win.set_icon_name(ICON)
        self.win.connect('close-request', self.close_requested)
        theme = Gtk.IconTheme.get_for_display(self.win.get_display())
        assets = Path(__file__).resolve().parents[1] / 'assets/icons'
        if assets.exists():
            theme.add_search_path(str(assets))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        branding = Gtk.Box(spacing=10)
        brand_icon=Gtk.Image.new_from_icon_name(ICON)
        brand_icon.set_pixel_size(24)
        branding.append(brand_icon)
        branding.append(Adw.WindowTitle(title='Ubuntu Update Utility', subtitle='Aggiornamenti e pulizia'))
        header.set_title_widget(branding)
        box.append(header)
        self.status = Gtk.Label(label='Cerca gli aggiornamenti, poi seleziona le app da aggiornare.', xalign=0, wrap=True)
        self.status.set_margin_start(20)
        self.status.set_margin_end(20)
        self.status.set_margin_top(12)
        self.status.set_margin_bottom(12)
        box.append(self.status)
        # HORIZONTAL puts the panels side by side, separated by a vertical divider.
        self.panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        self.panes.set_position(435)
        self.panes.set_shrink_start_child(False)
        self.panes.set_shrink_end_child(False)
        box.append(self.panes)
        left = self.panel('Applicazioni disponibili')
        self.check = Gtk.Button(label='Cerca aggiornamenti')
        self.check.connect('clicked', lambda _: self.start(action='scan'))
        left.append(self.check)
        hint = Gtk.Label(label='Standalone e Snap · gli aggiornamenti APT sono separati', wrap=True, xalign=0)
        hint.add_css_class('dim-label')
        left.append(hint)
        self.all_check = Gtk.CheckButton(label='Seleziona tutte')
        self.all_handler=self.all_check.connect('toggled', self.toggle_all)
        left.append(self.all_check)
        self.app_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.app_list.add_css_class('boxed-list')
        self.empty = Gtk.Label(label='Esegui la ricerca per vedere le applicazioni.', wrap=True)
        self.app_list.set_placeholder(self.empty)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_width=330)
        scroll.set_child(self.app_list)
        left.append(scroll)
        self.run = Gtk.Button(label='Aggiorna selezionate (0)')
        self.run.add_css_class('suggested-action')
        self.run.connect('clicked', lambda _: self.start(action='selected'))
        left.append(self.run)
        self.panes.set_start_child(left)
        right = self.panel('Operazioni')
        actions = Gtk.Box(spacing=8)
        self.system = Gtk.Button(label='Aggiorna sistema')
        self.system.set_tooltip_text('APT, Flatpak, driver e firmware; conferme dedicate per le operazioni delicate.')
        self.system.connect('clicked', lambda _: self.start(action='system'))
        self.clean = Gtk.Button(label='Pulisci')
        self.clean.set_tooltip_text('Cache APT, autoremove con purge, vecchie revisioni Snap e runtime inutilizzati. Conserva dati e copie di recupero.')
        self.clean.connect('clicked', lambda _: self.start(action='clean'))
        actions.append(self.system)
        actions.append(self.clean)
        right.append(actions)
        self.progress = Gtk.ProgressBar(show_text=True)
        right.append(self.progress)
        self.results = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True)
        results_scroll = Gtk.ScrolledWindow(min_content_height=120, max_content_height=180, propagate_natural_height=True)
        results_scroll.set_child(self.results)
        right.append(results_scroll)
        self.view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        log_scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=180)
        log_scroll.set_child(self.view)
        expander = Gtk.Expander(label='Dettagli delle operazioni', expanded=True, vexpand=True)
        expander.set_child(log_scroll)
        right.append(expander)
        self.stop = Gtk.Button(label='Annulla dopo l’operazione')
        self.stop.connect('clicked', lambda _: self.cancel())
        self.restore = Gtk.Button(label='Ripristina versione precedente')
        self.restore.connect('clicked', lambda _: self.start(action='restore'))
        right.append(self.stop)
        right.append(self.restore)
        self.panes.set_end_child(right)
        self.win.set_content(box)
        self.update_controls()
        self.win.present()

    def panel(self, title):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(panel, 'set_margin_' + side)(18)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class('title-3')
        panel.append(heading)
        return panel

    def populate(self):
        child = self.app_list.get_first_child()
        while child:
            following = child.get_next_sibling()
            self.app_list.remove(child)
            child = following
        self.rows.clear()
        self.all_check.set_active(False)
        for identifier, candidate in sorted(self.candidates.items(), key=lambda item: item[1]['name'].lower()):
            row = Adw.ActionRow(title=candidate['name'], subtitle=f"{candidate['kind']} · {candidate['current']} → {candidate['available']}")
            image = Gtk.Image.new_from_gicon(desktop_icon(candidate))
            image.set_pixel_size(32)
            row.add_prefix(image)
            checkbox = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            checkbox.connect('toggled', lambda _: self.update_controls())
            row.add_suffix(checkbox)
            row.set_activatable_widget(checkbox)
            self.rows[identifier] = checkbox
            self.app_list.append(row)
        self.empty.set_text('Nessun aggiornamento automatico disponibile. Vedi il riepilogo delle verifiche.' if not self.candidates else '')
        self.update_controls()

    def toggle_all(self, checkbox):
        active=checkbox.get_active()
        for item in self.rows.values():
            item.set_active(active)

    def selected_ids(self):
        return [identifier for identifier, checkbox in self.rows.items() if checkbox.get_active()]

    def update_controls(self):
        idle = not self.running
        for button in (self.check, self.system, self.clean, self.restore):
            button.set_sensitive(idle)
        count = len(self.selected_ids())
        self.run.set_label(f'Aggiorna selezionate ({count})')
        self.run.set_sensitive(idle and count > 0)
        self.all_check.handler_block(self.all_handler)
        self.all_check.set_active(bool(self.rows) and count==len(self.rows))
        self.all_check.set_inconsistent(0<count<len(self.rows))
        self.all_check.handler_unblock(self.all_handler)
        self.all_check.set_sensitive(idle and bool(self.rows))
        self.app_list.set_sensitive(idle)
        self.stop.set_sensitive(self.running and not self.cancelled)

    def close_requested(self, *_):
        if self.running:
            self.cancel()
            return True
        return False

    def cancel(self):
        self.cancelled = True
        self.update_controls()
        self.status.set_text('Annullamento richiesto: attendo la fine dell’operazione corrente.')

    def append(self, text):
        buf = self.view.get_buffer()
        buf.insert(buf.get_end_iter(), text)
        if buf.get_line_count() > 6000:
            end = buf.get_iter_at_line(buf.get_line_count() - 6000)[1]
            buf.delete(buf.get_start_iter(), end)

    def reply(self, process, message):
        try:
            process.stdin.write(json.dumps(message) + '\n')
            process.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def details_dialog(self, title, detail):
        dialog = Adw.MessageDialog(transient_for=self.win, heading=title)
        details = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        details.get_buffer().set_text(detail)
        scroll = Gtk.ScrolledWindow(min_content_height=220, max_content_height=440, min_content_width=480)
        scroll.set_child(details)
        dialog.set_extra_child(scroll)
        return dialog

    def event(self, event, process):
        kind = event.get('type')
        if kind == 'candidate' and self.action == 'scan':
            self.candidates[event['id']] = event
        elif kind == 'log':
            self.append(event['text'])
        elif kind == 'stage':
            self.status.set_text(event['category'] + ' in corso…')
            self.progress.set_fraction(event.get('index', 0) / max(event.get('total', 1), 1))
            self.progress.set_text(event['category'])
        elif kind == 'checkpoint':
            self.reply(process, {'cancel': True} if self.cancelled else {'continue': True})
        elif kind == 'confirm':
            dialog = self.details_dialog(event['title'], event['detail'])
            dialog.add_response('no', 'Salta')
            dialog.add_response('yes', 'Conferma')
            dialog.set_default_response('no')
            dialog.set_close_response('no')
            dialog.connect('response', lambda _, response: self.reply(process, {'cancel': True} if self.cancelled else {'approve': response == 'yes'}))
            dialog.present()
        elif kind == 'result':
            self.outcomes.append(event)
            line = f"{event['category']}: {event['status']}"
            self.results.set_text(self.results.get_text() + line + '\n')
            self.append(line + '\n' + event.get('detail', '') + '\n')
        elif kind == 'summary':
            self.reboot = self.reboot or event.get('reboot', False)

    def start(self, apply=False, restore=False, action=None):
        if self.running:
            return
        action = action or ('restore' if restore else 'system' if apply else 'scan')
        selected = self.selected_ids()
        if action == 'selected' and not selected:
            return
        self.action = action
        self.running = True
        self.cancelled = False
        self.reboot = False
        self.outcomes = []
        self.last_summary = None
        if action == 'scan':
            self.candidates = {}
            self.populate()
            self.empty.set_text('Ricerca in corso…')
        self.results.set_text('')
        self.view.get_buffer().set_text('')
        self.progress.set_fraction(0)
        self.status.set_text('Operazione in corso…')
        self.update_controls()
        commands = build_commands(Path(__file__).parent, action, selected)

        def work():
            try:
                state = Path.home() / '.local/state/ubuntu-update-utility'
                state.mkdir(parents=True, exist_ok=True)
                logpath = state / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.jsonl')
                with open(logpath, 'x') as log:
                    os.chmod(logpath, 0o600)
                    for command in commands:
                        if self.cancelled:
                            break
                        reported_error=False
                        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
                            if action == 'selected':
                                self.reply(proc, {'selected': selected})
                            for line in proc.stdout:
                                log.write(line)
                                log.flush()
                                try:
                                    event = json.loads(line)
                                    if not isinstance(event, dict):
                                        raise ValueError()
                                except ValueError:
                                    GLib.idle_add(self.append, line)
                                    continue
                                if event.get('type')=='result' and event.get('status')=='errore': reported_error=True
                                GLib.idle_add(self.event, event, proc)
                            code = proc.wait()
                        GLib.idle_add(self.append, f'\nProcesso terminato: {code}\n')
                        if code in (126, 127):
                            GLib.idle_add(self.event, dict(type='result', category='Autenticazione', status='errore', detail='Autenticazione annullata o helper non disponibile.'), None)
                            break
                        if code and not reported_error:
                            GLib.idle_add(self.event, dict(type='result', category='Operazione', status='errore', detail=f'Il processo è terminato con codice {code}.'), None)
                GLib.idle_add(self.append, 'Registro: ' + str(logpath) + '\n')
            except Exception as error:
                GLib.idle_add(self.event, dict(type='result', category='Operazione', status='errore', detail=str(error)), None)
            GLib.idle_add(self.finished)
        threading.Thread(target=work, daemon=True).start()

    def finished(self):
        self.running = False
        failed = any(item['status'] == 'errore' for item in self.outcomes)
        if self.action == 'scan':
            self.populate()
            self.status.set_text(f'Ricerca terminata: {len(self.rows)} aggiornamenti disponibili.' + (' Alcune verifiche sono fallite: vedi i dettagli.' if failed else ''))
        else:
            if self.action == 'selected':
                successful = {item['category'].removeprefix('Snap: ') for item in self.outcomes if item['status'] == 'aggiornato'}
                for identifier in list(self.candidates):
                    if self.candidates[identifier]['name'] in successful:
                        del self.candidates[identifier]
                self.populate()
            self.status.set_text('Autenticazione annullata o non disponibile.' if any(i['category'] == 'Autenticazione' for i in self.outcomes) else 'Operazione terminata: consulta il riepilogo.')
            self.show_summary()
        if self.cancelled:
            self.status.set_text('Operazione annullata. Gli esiti già completati sono nel riepilogo.')
        self.progress.set_fraction(1)
        self.update_controls()

    def show_summary(self):
        groups = [('Aggiornati / eseguiti', {'aggiornato', 'pulito', 'ripristinato'}), ('Falliti', {'errore'}), ('Da completare', {'intervento richiesto', 'verifica manuale', 'saltato'})]
        parts = []
        included = set()
        for title, statuses in groups:
            entries = [i for i in self.outcomes if i['status'] in statuses]
            included.update(statuses)
            lines = [f"• {i['category']}: {i['status']}" + (f"\n  {i['detail']}" if i.get('detail') else '') for i in entries]
            parts.append(title + '\n' + ('\n'.join(lines) if lines else 'Nessuno'))
        unchanged = [i['category'] + ': ' + i['status'] for i in self.outcomes if i['status'] not in included]
        if unchanged:
            parts.append('Altri esiti\n' + '\n'.join(unchanged))
        if self.cancelled:
            parts.append('Annullamento richiesto: le operazioni non avviate non sono state eseguite.')
        if self.reboot:
            parts.append('È necessario riavviare il PC per completare alcune operazioni.')
        dialog = self.details_dialog('Riepilogo finale', '\n\n'.join(parts))
        dialog.add_response('close', 'Chiudi')
        dialog.set_close_response('close')
        self.last_summary = dialog
        dialog.present()


if __name__ == '__main__':
    Utility().run()
