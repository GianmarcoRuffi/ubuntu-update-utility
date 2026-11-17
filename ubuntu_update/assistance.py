"""Assisted paths never imply success merely because a browser was opened."""
from dataclasses import asdict
try:
    from . import profiles
except ImportError:
    import profiles


def instructions(item):
    text=f'Installazione: {item.root or item.path}\nVersione: {item.version or "non identificata"}\n'
    name=item.name.lower()
    if 'xampp' in name:
        text+='Prima della migrazione: esporta i database, copia progetti e configurazioni, verifica di poter ripristinare il backup. Controlla la compatibilità PHP/MariaDB e prova la nuova versione separatamente. Non sovrascrivere la directory attuale.\n'
    elif 'gpick' in name:
        text+='Per una compilazione locale: controlla la release e le dipendenze nel progetto ufficiale, compila in una directory separata e conserva il binario precedente. Non sostituire la versione della distribuzione con quella locale.\n'
    elif 'forti' in name:
        branch='.'.join(item.version.split('.')[:2])
        text+=f'Conserva edizione e ramo installati ({branch or "da verificare"}). Se il client è gestito da un’azienda, verifica le indicazioni del suo amministratore. L’aggiornamento può interrompere la VPN. Scarica il DEB compatibile dal portale ufficiale.\n'
    else:
        text+='Associa il sito o repository ufficiale. Per archivi o compilazioni non riconosciuti consulta le istruzioni del produttore, verifica i dati locali e conserva la versione precedente.\n'
    return text


def run(session,item,home):
    payload=asdict(item);payload['instructions']=instructions(item)
    payload['profile']=profiles.load(home).get(item.id,{})
    response=session.assistance(payload)
    action=response.get('action','skip')
    if action=='save':
        record=response.get('profile',{})
        profiles.save(item.id,record,home)
        session.result(item.name,'intervento richiesto','Fonte salvata. Ripeti la ricerca per verificare versione e pacchetto.');return
    if action=='deb' and item.package:
        code=session.child(['/usr/bin/pkexec','/usr/lib/ubuntu-update-utility/helper','--local-deb'],dict(package=item.package,path=response.get('path','')))
        if code==0:
            session.emit('completed',id=item.id)
        else: session.result(item.name,'intervento richiesto','Installazione non completata; controllare i dettagli. Codice '+str(code))
        return
    session.result(item.name,'saltato' if action=='skip' else 'intervento richiesto','Procedura assistita non completata. '+instructions(item))
