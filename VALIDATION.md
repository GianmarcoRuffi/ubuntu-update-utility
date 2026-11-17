# Verifica del piano

Verifiche svolte il 17 novembre 2026 su Ubuntu 26.04. Le operazioni reali di
aggiornamento del PC non sono state avviate.

| Requisito | Implementazione e verifica |
| --- | --- |
| GUI italiana GTK4/Libadwaita, avanzamento, dettagli e riepilogo | `app.py`; smoke test nativo con display attivo, inclusa autenticazione annullata |
| Avvio dal menu e desktop, pacchetto installabile | launcher nel DEB; `desktop-shortcut.py`; validazione desktop entry e contenuti pacchetto; installazione e rimozione reali in una root dpkg isolata |
| Password di sistema e helper root | helper Python in modalità isolata, percorso fisso; policy Polkit `auth_admin`; proprietà root e permessi controllati nel DEB |
| APT, configurazioni e blocchi | simulazione upgrade, attesa lock, rispetto hold, `--force-confold`; test errore APT e mancata pulizia dopo fallimento |
| Autoremove/purge/clean | anteprima e conferma; kernel in uso e riserva protetti; test rifiuto, kernel vecchi e metapacchetti |
| Snap e recupero | refresh dei soli snap non sospesi; test hold globale e individuale; eliminazione delle revisioni obsolete conservandone una |
| Flatpak utente e sistema | fasi separate con cleanup `--unused`, senza `--delete-data`; controllo reale di sola lettura |
| Driver e firmware | rilevamento Ubuntu e fwupd, conferme dedicate, nessun riavvio automatico; test rifiuto firmware |
| FortiClient | esclusione APT temporanea; aggiornamento separato solo con conferma; assenza repository segnalata come verifica manuale |
| Docker, DBeaver, GitHub Desktop, Teams | sorgenti dedicate, controllo DEB e checksum; metadata reali verificati e download HEAD DBeaver/Teams riuscito |
| Postman, JMeter, Audacity, Forge stabile | sorgenti ufficiali e GitHub release; rilevamento reale; download JMeter ufficiale con SHA-512 ed estrazione verificati |
| Dati, launcher personalizzati e rollback | installazione separata e backup; test aggiornamento JMeter completo, opzioni launcher, recupero e fallimento attivazione |
| XAMPP, Gpick, app sconosciute | controllo disponibilità e istruzioni manuali; verifica reale dei risultati senza dichiararli aggiornati |
| Download, archivi e pulizia | HTTPS con redirect autorizzati; test checksum errato, traversal, symlink esterni, spazio insufficiente e rete assente; temporanei rimossi |
| Isolamento errori, annullamento e singola esecuzione | protocollo JSON, lock e checkpoint; flusso amministrativo provato con UID 0 in user namespace e host in sola lettura |

## Comandi riproducibili

```sh
python3 -m unittest discover -s tests -v
python3 tests/gui_smoke.py
python3 tests/read_only_check.py
sh packaging/build.sh
python3 tests/package_check.py
bwrap --ro-bind / / --unshare-user --uid 0 --gid 0 --unshare-pid \
  --proc /proc --tmpfs /run --tmpfs /tmp --tmpfs /var/tmp \
  --die-with-parent python3 tests/install_sandbox.py
bwrap --ro-bind / / --unshare-user --uid 0 --gid 0 --unshare-pid \
  --proc /proc --tmpfs /run --tmpfs /tmp --tmpfs /var/tmp \
  --die-with-parent python3 -m unittest discover -s tests -q
bwrap --ro-bind / / --unshare-user --uid 0 --gid 0 --unshare-pid \
  --proc /proc --tmpfs /run --tmpfs /tmp --die-with-parent \
  python3 tests/sandbox_check.py
```

La suite e il sandbox usano fixture per le installazioni: non provano il flash di
firmware fisico, l’installazione di nuovi driver sull’hardware o ogni futura
release dei produttori. I cambiamenti dei siti vengono segnalati come errori,
senza sostituire un’installazione che non sia stata verificata.

Per XAMPP la pagina ufficiale attuale non espone un installer Linux identificabile;
Gpick è una compilazione personalizzata. Entrambi seguono il percorso manuale
previsto dal piano. FortiClient non ha un repository configurato su questo PC.

## Revisione 0.4.0 — selezione e pulizia separate

- Pannelli affiancati con divisore verticale; la lista appare dopo la scansione
  completa e contiene soltanto aggiornamenti standalone e Snap selezionabili.
- Icone delle applicazioni installate e checkbox con selezione multipla. La lista
  selezionata è validata da entrambi i worker: test su identificatori non validi,
  selezione vuota, esclusione delle app non selezionate e assenza di APT nel flusso
  selettivo.
- Pulsante Pulisci indipendente: test che nessun aggiornamento sia avviato,
  protezione dei backup e dei file estranei, rimozione dei soli installer temporanei
  dell’utility con proprietà e permessi attesi.
- Riepilogo finale unico per tutte le fasi: il test grafico verifica successi,
  fallimenti e autenticazione annullata; nessuna finestra prematura fra i worker.
- Icona SVG dedicata in hicolor, desktop ID corrispondente all’application ID e
  metadati AppStream inclusi nel DEB. L’icona nella barra è verificata dal test
  grafico. Il progetto locale non ha una homepage pubblica: il validatore
  AppStream segnala il relativo avviso, senza errori nei metadati.
- Anteprima nativa con dati di esempio: `python3 tests/gui_preview.py` produce
  `dist/preview.png`. La scansione reale è stata ripetuta senza installazioni né
  pulizie sul PC.
