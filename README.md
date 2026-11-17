# Ubuntu Update Utility

Utility desktop in italiano per Ubuntu 26.04, Python 3, GTK4 e Libadwaita.

## Installazione e avvio

Costruire con `sh packaging/build.sh`. Installare il pacchetto prodotto in `dist`
con un doppio clic oppure `sudo apt install ./dist/ubuntu-update-utility_0.4.0_all.deb`.
Aprire **Ubuntu Update Utility** dal menu applicazioni. Per il collegamento sul
Desktop eseguire `python3 packaging/desktop-shortcut.py` dopo l’installazione;
il desktop potrebbe richiedere di scegliere **Consenti avvio** al primo clic.

**Cerca aggiornamenti** individua le nuove versioni. Al termine, il pannello a
sinistra mostra le app standalone e Snap con icona e checkbox: selezionare quelle
desiderate e premere **Aggiorna selezionate**. Le app non selezionate vengono
escluse anche dai motori di aggiornamento. Le versioni vengono ricontrollate prima
di installarle.

Il pannello a destra contiene le operazioni e il registro. **Aggiorna sistema**
gestisce separatamente APT, Flatpak, driver e firmware. **Pulisci** esegue la
pulizia della cache dei pacchetti APT, `autoremove --purge` con anteprima e conferma,
la rimozione delle revisioni Snap obsolete (conservandone una precedente), dei
runtime Flatpak inutilizzati e dei temporanei/cache dell’utility. Non aggiorna
applicazioni e non cancella Download, dati personali o copie di recupero.

L’autenticazione è gestita da Polkit. FortiClient, rimozioni, nuovi driver e firmware
mantengono le conferme dedicate. **Annulla dopo l’operazione** attende la conclusione
dell’installazione corrente. Al termine di aggiornamenti, pulizia o ripristino una
finestra riepiloga operazioni riuscite, fallite e da completare, comprese entrambe
le fasi di sistema e utente. Non viene eseguito alcun riavvio automatico.

Il pacchetto include l’icona dedicata nel tema hicolor e i metadati AppStream per
i gestori software che li supportano. La stessa icona compare nella barra della
finestra e nel menu applicazioni.

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
