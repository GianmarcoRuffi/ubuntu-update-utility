# Ubuntu Update Utility

Applicazione desktop in italiano per Ubuntu: ricerca generale delle installazioni,
aggiornamenti selettivi e pulizia. Richiede Python 3.12+, GTK4 e Libadwaita 1.2+;
il collaudo locale è eseguito su Ubuntu 26.04.

## Installazione e avvio

Costruire con `sh packaging/build.sh`. Installare il pacchetto in `dist` con un
doppio clic oppure:

```sh
sudo apt install ./dist/ubuntu-update-utility_0.5.1_all.deb
```

Aprire **Ubuntu Update Utility** dal menu. Per il collegamento Desktop eseguire
`python3 packaging/desktop-shortcut.py` dopo l’installazione. Il desktop potrebbe
richiedere **Consenti avvio** al primo clic.

All’apertura parte soltanto la ricerca. Non vengono installate applicazioni.
Il pulsante **Cerca aggiornamenti** permette di ripeterla.

## Lista e selezione

La ricerca legge database dei pacchetti, launcher utente e di sistema, directory
XDG, `/opt`, `/usr/local/bin`, `~/Applications`, `~/.local/opt` e le directory utente del PATH. Non esegue i
programmi per scoprirne la versione e non scandisce indiscriminatamente documenti
o altri dischi. Le installazioni separate della stessa applicazione hanno
identificatori distinti; i dettagli della riga mostrano il percorso.

Il pannello sinistro distingue:

- **Aggiornamenti disponibili**: versione o nuovo contenuto verificati per Snap,
  Flatpak o standalone con una fonte riconosciuta.
- **Da verificare / aggiornamento assistito**: applicazioni individuate, comprese
  quelle senza una versione confrontabile, una fonte nota o un aggiornamento
  automatizzabile. La presenza qui non afferma che esista una versione nuova.

Le checkbox partono deselezionate. **Aggiorna selezionate** interviene soltanto
sulle installazioni scelte. Non esistono esclusioni personali per FortiClient,
Gpick, XAMPP o altri nomi. Fonti, versioni e disponibilità vengono ricontrollate
prima dell’installazione. Canali e blocchi dei gestori vengono rispettati.

**APT resta separato**: un’app con repository APT configurato segue **Aggiorna
sistema**. Quel pulsante gestisce APT, driver raccomandati e firmware; Snap e
Flatpak si selezionano nella lista. Le operazioni amministrative richiedono
l’autenticazione Polkit, senza memorizzare la password.

## Standalone e percorso assistito

Gli aggiornatori dedicati esistenti sono adattatori del catalogo comune. Postman,
JMeter, Audacity e Forge vengono riconosciuti dai metadati della loro installazione,
anche in percorsi diversi da quelli del PC originale. I pacchetti Docker Desktop,
DBeaver, Discord (DEB stabile amd64), GitHub Desktop e Teams hanno adattatori dedicati
quando non gestiti da APT.
Le build di sviluppo non vengono trasformate silenziosamente in release stabili.

Il motore generale riconosce informazioni di aggiornamento AppImage, release
GitHub associate al progetto, manifest JSON e appcast XML. Controlla i pacchetti,
i checksum pubblicati e l’architettura. Per gli archivi generici è necessario
identificare l’eseguibile e verificare il launcher; installazioni contenenti dati
locali richiedono assistenza per la migrazione.

Selezionando una riga assistita è possibile:

- consultare i passaggi necessari e aprire il sito ufficiale;
- associare una fonte e, se necessario, dichiarare la versione installata;
- salvare il link HTTPS diretto al DEB del produttore. Dopo una nuova ricerca,
  selezionare la riga assistita e premere **Aggiorna selezionate** per scaricare il
  pacchetto, leggere la versione e proporre l’installazione se è più recente;
- specificare repository, nome del pacchetto, canale ed eseguibile nelle opzioni
  avanzate, oppure indicare un manifest JSON/appcast;
- scegliere un DEB già scaricato per aggiornare il corrispondente pacchetto
  installato. L’helper verifica una copia privata del file, prodotto, versione,
  architettura e dipendenze prima di chiedere conferma.

Le associazioni sono salvate per installazione in
`${XDG_CONFIG_HOME:-~/.config}/ubuntu-update-utility/sources.json`.
Dopo **Salva fonte**, ripetere la ricerca. Per automatizzare il download, indicare
un link diretto al DEB o una delle fonti strutturate. Un manifest JSON semplice usa
`version`, `url` HTTPS e, quando pubblicato, `sha256`.

FortiClient può richiedere accesso al portale o indicazioni aziendali; XAMPP può
richiedere esportazione e migrazione di database; Gpick compilato localmente può
richiedere una nuova compilazione. Questi passaggi non vengono nascosti né
considerati completati solo perché sono state aperte le istruzioni. Non vengono
eseguiti comandi shell definiti nelle associazioni delle fonti.

## Pulizia, recupero e riepilogo

**Pulisci** è indipendente dagli aggiornamenti: pulisce la cache APT, propone
`autoremove --purge` con anteprima e conferma, rimuove revisioni Snap obsolete
conservandone una precedente, runtime Flatpak inutilizzati e temporanei
riconoscibili dell’utility. Conserva kernel necessari e copie di recupero.
Non svuota Download né cerca file personali da cancellare.

Le installazioni in archivio sono preparate separatamente e conservano una copia
`.previous`. Le AppImage aggiornabili dall’utente mantengono il percorso originale
e una copia precedente. **Ripristina versione precedente** permette di scambiarle.
Le installazioni e i backup creati dalle versioni precedenti restano riconoscibili.
Il recupero dei DEB dipende invece dai pacchetti precedenti del produttore/APT.

**Annulla dopo l’operazione** attende la conclusione dell’installazione corrente.
Il riepilogo finale raccoglie successi, errori, rinunce e passaggi ancora necessari
di entrambe le fasi. Nessun riavvio automatico. Registri delle sessioni in
`~/.local/state/ubuntu-update-utility`.

## Installer e verifiche

Icona SVG, desktop entry e metadati AppStream sono inclusi nel DEB. La schermata
locale di Ubuntu App Center usa comunque un’icona generica: è un limite del suo
[costruttore per i DEB locali](https://github.com/ubuntu/app-center/blob/main/packages/app_center/lib/apps/app_title_bar.dart).

```sh
python3 -m unittest discover -s tests -v
python3 tests/gui_smoke.py
python3 tests/gui_assistance.py
python3 tests/read_only_check.py
sh packaging/build.sh
python3 tests/package_check.py
```

Le prove grafiche richiedono un display. I test non applicano aggiornamenti al PC.
`python3 tests/gui_preview.py` produce un’anteprima con dati di esempio.
Vedere `VALIDATION.md` per i collaudi isolati e i limiti della verifica.

Disinstallare con `sudo apt remove ubuntu-update-utility`. Applicazioni aggiornate,
associazioni e copie di recupero rimangono disponibili. Rimuovere manualmente il
collegamento Desktop se creato.
