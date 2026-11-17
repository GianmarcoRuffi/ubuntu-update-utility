# Ubuntu Update Utility

Utility desktop in italiano per Ubuntu 26.04, Python 3, GTK4 e Libadwaita.

## Installazione e avvio

Costruire con `sh packaging/build.sh`. Installare il pacchetto prodotto in `dist`
con un doppio clic oppure `sudo apt install ./dist/ubuntu-update-utility_0.3.0_all.deb`.
Aprire **Ubuntu Update Utility** dal menu applicazioni. Per il collegamento sul
Desktop eseguire `python3 packaging/desktop-shortcut.py` dopo l’installazione;
il desktop potrebbe richiedere di scegliere **Consenti avvio** al primo clic.

**Controlla aggiornamenti** non installa pacchetti; consulta gli indici locali APT
e gli indici online dei produttori. **Aggiorna tutto** richiede l’autenticazione
Polkit e aggiorna prima il sistema, poi le applicazioni dell’utente.
Le rimozioni APT, i nuovi driver, il firmware e FortiClient richiedono conferma.
**Annulla dopo l’operazione** attende la conclusione dell’installazione corrente.
Non viene eseguito alcun riavvio automatico.

## Applicazioni e recupero

APT, Snap e Flatpak sono gestiti separatamente. I pacchetti con repository APT
non vengono aggiornati anche come standalone. Le sorgenti dedicate sono Docker,
DBeaver, shiftkey/desktop, IsmaelMartinez/teams-for-linux, Postman, Apache JMeter,
audacity/audacity e Card-Forge/forge. Forge segue le release stabili.

Gli archivi vengono installati in `~/.local/share/ubuntu-update-utility/apps`.
Una copia `.previous` permette il recupero con **Ripristina versione precedente**.
La prima installazione originale viene mantenuta: l’utility non cancella directory
preesistenti in `/opt`, progetti, database o salvataggi. Gli installer scaricati
vengono eliminati al termine, anche in caso di errore. Per i pacchetti DEB il
recupero dipende dai pacchetti precedenti disponibili attraverso il produttore/APT.

XAMPP e Gpick personalizzato mostrano disponibilità e istruzioni: migrazioni di
database e ricompilazioni richiedono intervento manuale. Le altre applicazioni
individuate vengono segnalate senza inventare una verifica degli aggiornamenti.
I plugin JMeter personalizzati possono richiedere migrazione manuale.

I registri delle sessioni sono in `~/.local/state/ubuntu-update-utility`.
La password è gestita da Polkit e non viene registrata. Il helper amministrativo
usa esclusivamente operazioni e sorgenti definite nel pacchetto installato.

## Sviluppo e verifiche

`python3 -m unittest discover -s tests -v` esegue i test di motore e sicurezza.
`python3 tests/gui_smoke.py` controlla la finestra su un display grafico attivo,
senza avviare aggiornamenti. `python3 ubuntu_update/app.py` avvia la GUI dai
sorgenti; l’applicazione degli aggiornamenti di sistema richiede il pacchetto
installato, con helper di proprietà root.

Disinstallare con `sudo apt remove ubuntu-update-utility`. Le applicazioni già
aggiornate e le copie di recupero restano disponibili. Rimuovere il collegamento
dal desktop manualmente se creato.
