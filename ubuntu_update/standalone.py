"""Uniform lifecycle for discovered built-in, generic and assisted updates."""
from pathlib import Path
try:
    from . import profiles, providers, archives
    from .assistance import run as assist
    from .catalog import CATALOG,DEBS
except ImportError:
    import profiles, providers, archives
    from assistance import run as assist
    from catalog import CATALOG,DEBS


def offer(session,item,available='Da verificare',reason=''):
    session.emit('candidate',id=item.id,name=item.name,current=item.version or 'Non identificata',available=available,kind='Standalone',mode='assisted',path=item.root or item.path,homepage=item.homepage,icon=item.icon,reason=reason)


def _process(session,item,apply,home):
    profile=profiles.load(home).get(item.id,{})
    if profile.get('homepage'): item.homepage=profile['homepage']
    if item.package in DEBS and not (profiles.deb_url(profile) or profile.get('repository') or profile.get('manifest')):
        if apply:assist(session,item,home);return
        try:
            try:
                from .packages import update_package
            except ImportError:
                from packages import update_package
            update_package(session,item.package,False)
        except (OSError,ValueError,KeyError) as error:offer(session,item,reason=str(error))
        return
    if item.provider=='builtin' and item.name in CATALOG and not profile.get('repository') and not profile.get('manifest'):
        if not item.version:
            if apply:assist(session,item,home)
            else:offer(session,item,reason='Versione installata non identificabile.')
            return
        if item.channel!='stable':
            if apply:assist(session,item,home)
            else:offer(session,item,reason='Canale '+item.channel+': verifica la build compatibile nel percorso assistito.')
            return
        root=Path(item.root or item.path)
        if item.name=='Audacity standalone' and root.name=='squashfs-root':
            # The legacy Audacity adapter expects the enclosing extracted bundle.
            root=root.parent
        record=dict(name=item.name,version=item.version,path=root,id=item.id,target=item.id.removeprefix('install:'),wrapper=item.wrapper)
        count=len(session.results)
        try:archives.update(session,record,apply,home)
        except (OSError,ValueError,KeyError) as error:
            if apply:raise
            offer(session,item,reason=str(error));return
        # A built-in adapter may require migration rather than an automatic update.
        if len(session.results)>count and session.results[-1]['status']=='intervento richiesto':
            if apply:assist(session,item,home)
            else:offer(session,item,reason=session.results[-1]['detail'])
        return
    check=providers.check(item,profile)
    if check.reason:
        if apply:assist(session,item,home)
        else:offer(session,item,check.source.get('version','Da verificare') if check.source else 'Da verificare',check.reason)
    elif not check.available:
        session.result(item.name,'nessun aggiornamento',item.version)
    elif not apply:
        if check.source['format']=='deb':
            offer(session,item,reason='Seleziona la riga per scaricare il DEB e verificare la versione.')
        else:
            session.emit('candidate',id=item.id,name=item.name,current=item.version or 'Non identificata',available=check.source['version'] or 'Nuovo contenuto AppImage',kind='Standalone',mode='automatic',path=item.root or item.path,homepage=item.homepage,icon=item.icon)
    else:
        if providers.install(session,item,check.source,home):
            if check.source.get('version') and check.source['format']=='archive':
                profile=dict(profile,version=check.source['version'])
                profiles.save(item.id,profile,home)


def process(session,item,apply,home):
    try:
        return _process(session,item,apply,home)
    except Exception as error:
        try:
            from .runtime import Cancelled
        except ImportError:
            from runtime import Cancelled
        if isinstance(error,Cancelled):raise
        session.result(item.name,'errore',str(error)+'\nInstallazione: '+(item.root or item.path))
