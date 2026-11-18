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
| FortiClient | nessuna esclusione personale: pacchetto con repository segue APT; standalone segue il percorso assistito o la fonte associata |
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

## Revisione 0.4.1 — descrizione del pacchetto

La descrizione Debian e quella AppStream sono state ampliate con funzioni,
app supportate, conferme, pulizia, recupero e limiti. Verificati il formato a
paragrafi del campo Description nel DEB, la presenza dei metadati e dell'icona,
e installazione/rimozione del nuovo pacchetto in una root dpkg isolata.

L'icona generica della schermata dei DEB locali di App Center non è controllabile
dai metadati del pacchetto: il costruttore `AppTitleBar.fromLocalDeb` non imposta
né `iconUrl` né `iconWidget`. Riferimento:
https://github.com/ubuntu/app-center/blob/main/packages/app_center/lib/apps/app_title_bar.dart

## Revisione 0.5.0 — inventario generale e fonti riutilizzabili

- L’inventario usa launcher, directory XDG e directory applicative standard,
  risolve link e wrapper semplici senza eseguirli, distingue le copie per percorso
  e unifica gli alias di un pacchetto Debian. Le app native APT restano separate.
- I test di inventario coprono altri percorsi/home, applicazioni sconosciute,
  versioni da manifest, collegamenti duplicati, precedenza dei launcher utente e
  lettura delle informazioni ELF AppImage senza eseguire il programma.
- Il ciclo comune gestisce adattatori del catalogo e fonti generiche GitHub,
  AppImage/zsync, manifest JSON e appcast. Versioni mancanti o fonti ambigue
  producono righe assistite, senza dichiarare che l’app è già aggiornata.
- Test di fonti e installazione su fixture: filtro architettura, checksum,
  provenienza HTTPS, archivi, launcher con argomenti, copie di recupero e
  conservazione dell’originale dopo un download corrotto.
- Il percorso assistito nativo valida e salva associazioni per installazione,
  permette di aprire il sito e scegliere un DEB scaricato. Il helper verifica
  una copia privata, proprietario del file, prodotto, versione, architettura,
  checksum quando trasmesso e simulazione delle dipendenze. Nessuna shell
  configurabile. Test su prodotto errato, file di altro utente e symlink.
- Flatpak è selezionabile per installazione, riferimento, ramo e origine. I test
  impediscono che un remoto diverso sostituisca quello dell’app installata.
- Il test grafico distingue i gruppi della lista e prova il percorso assistito;
  l’apertura delle istruzioni non viene registrata come aggiornamento riuscito.
- Resta disponibile il recupero delle installazioni precedenti; le nuove AppImage
  mantengono una copia accanto al file e le associazioni registrano il recupero.

Verifiche aggiuntive riproducibili:

```sh
python3 tests/gui_assistance.py
python3 tests/read_only_check.py
```

Il rilevamento copre le installazioni identificabili nelle posizioni dichiarate;
programmi senza metadati o fuori da tali posizioni possono richiedere una
associazione manuale. L’aggiornamento universale automatico di qualunque binario
non è dichiarato: i casi non verificabili restano esplicitamente assistiti.

Esito finale 0.5.0: 83 test automatici superati sia come utente normale sia nel
sandbox con UID 0 e host in sola lettura. Superati i collaudi grafici della lista,
della selezione, del riepilogo e dell’associazione assistita delle fonti;
verificati proprietà e completezza del DEB, installazione/rimozione isolata,
lock amministrativo e inoltro delle richieste DEB assistite. Controllati anche
percorsi XDG personalizzati e recupero dai percorsi delle vecchie versioni.
Nessun aggiornamento o pulizia del PC reale è stato avviato da queste verifiche.

## Correzioni dopo la review 0.5.1

La pulizia APT mostra le rimozioni della transazione effettiva prima di invocare
dpkg. Il test `tests/apt_cleanup_sandbox.py` richiede una root isolata con APT e
dpkg privati e verifica anche il lock durante la conferma.

La versione Debian completa viene letta dopo la selezione. Il ripristino
conserva gli argomenti dei launcher quando cambia l’eseguibile. I backup
AppImage 0.5.1 possono essere recuperati quando l’inventario identifica il file
e la copia adiacente supera le verifiche.
