#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/DEBIAN" "$stage/usr/lib/ubuntu-update-utility" "$stage/usr/share/applications"
cp packaging/helper "$stage/usr/lib/ubuntu-update-utility/helper"
chmod 755 "$stage/usr/lib/ubuntu-update-utility/helper"
mkdir -p "$stage/usr/share/polkit-1/actions"
cp packaging/it.local.UbuntuUpdateUtility.policy "$stage/usr/share/polkit-1/actions/"
cp ubuntu_update/*.py "$stage/usr/lib/ubuntu-update-utility/"
cat > "$stage/DEBIAN/control" <<EOF
Package: ubuntu-update-utility
Version: 0.5.0
Architecture: all
Maintainer: Ubuntu Update Utility - Progetto locale <local@localhost>
Depends: python3 (>= 3.12), apt, snapd, flatpak, fwupd, ubuntu-drivers-common, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.2), pkexec
Description: Ubuntu Update Utility - aggiornamenti e pulizia per Ubuntu
 Applicazione desktop in italiano per Ubuntu. Riunisce la ricerca degli
 aggiornamenti, la selezione delle applicazioni e la pulizia dei pacchetti
 in una finestra con lista delle app e pannello delle operazioni affiancati.
 .
 Aggiornamenti delle applicazioni:
  * Rileva app standalone, Snap e Flatpak senza percorsi personali predefiniti;
    cerca le versioni disponibili e mostra icone, versioni
    installate e disponibili e checkbox per scegliere cosa aggiornare.
  * Usa fonti generiche AppImage, GitHub, manifest JSON e appcast, e adattatori
    dedicati per Postman, JMeter, Audacity, Forge,
    Docker Desktop, DBeaver, GitHub Desktop e Teams for Linux, quando installati
    senza un repository APT che ne gestisca già gli aggiornamenti.
  * Controlla identità, architettura e versione dei pacchetti scaricati e
    verifica i checksum quando pubblicati dalle sorgenti utilizzate.
 .
 Aggiornamenti del sistema:
  * Mantiene APT separato dalla lista; rileva driver raccomandati e firmware.
  * Usa l'autenticazione di sistema Polkit, senza salvare la password.
  * Richiede conferma per nuovi driver e firmware. Non esclude app per nome.
  * Mostra procedure assistite per associare fonti o installare DEB scaricati,
    incluse applicazioni come FortiClient, XAMPP e Gpick compilato localmente.
 .
 Pulizia e recupero:
  * Il pulsante Pulisci elimina la cache APT e propone autoremove con purge,
    mostrando prima i pacchetti da rimuovere e proteggendo i kernel necessari.
  * Rimuove revisioni Snap obsolete, runtime Flatpak inutilizzati e installer
    temporanei dell'utility; conserva una revisione precedente dove supportato.
  * La pulizia è limitata ai percorsi gestiti: non svuota Download e non
    elimina progetti, database, documenti o copie di recupero delle app.
 .
 Al termine mostra un riepilogo di operazioni riuscite, fallite e da completare.
 È possibile richiedere l'annullamento tra operazioni e ripristinare la versione
 precedente delle app standalone gestite. Il PC non viene riavviato da solo.
EOF
cat > "$stage/usr/share/applications/it.local.UbuntuUpdateUtility.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Ubuntu Update Utility
Exec=/usr/bin/python3 /usr/lib/ubuntu-update-utility/app.py
Icon=it.local.UbuntuUpdateUtility
StartupWMClass=it.local.UbuntuUpdateUtility
Terminal=false
Categories=System;
EOF
mkdir -p "$stage/usr/share/doc/ubuntu-update-utility"
cp README.md "$stage/usr/share/doc/ubuntu-update-utility/"
mkdir -p "$stage/usr/share/icons/hicolor/scalable/apps" "$stage/usr/share/metainfo"
cp assets/icons/hicolor/scalable/apps/*.svg "$stage/usr/share/icons/hicolor/scalable/apps/"
cp packaging/it.local.UbuntuUpdateUtility.metainfo.xml "$stage/usr/share/metainfo/"
mkdir -p dist
dpkg-deb --root-owner-group --build "$stage" dist/ubuntu-update-utility_0.5.0_all.deb
