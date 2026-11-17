"""Discover and update a selected Flatpak reference in its own installation."""
import os
import subprocess


def pending(scope):
    def rows(args):
        p=subprocess.run(['/usr/bin/flatpak',*args,'--'+scope],capture_output=True,text=True,env=dict(os.environ,LC_ALL='C'))
        if p.returncode: raise RuntimeError(p.stderr.strip())
        return [line.split('\t') for line in p.stdout.splitlines()]
    installed={r[0]:(r[1],r[2]) for r in rows(['list','--app','--columns=ref,version,origin']) if len(r)>2}
    updates=rows(['remote-ls','--app','--updates','--columns=ref,version,origin'])
    unique={r[0]:(r[0],installed[r[0]][0],r[1]) for r in updates if len(r)>2 and r[0] in installed and r[2]==installed[r[0]][1]}
    return list(unique.values())


def process(session,scope,selected=None):
    if selected is not None and not any(i.startswith('flatpak-'+scope+':') for i in selected): return
    for ref,current,available in pending(scope):
        identifier='flatpak-'+scope+':'+ref
        name=ref.split('/')[1] if ref.startswith('app/') else ref.split('/')[0]
        if selected is None:
            session.candidate(identifier,name,current or 'Non specificata',available or 'Nuova revisione','Flatpak '+scope)
        elif identifier in selected:
            session.checkpoint()
            session.command(['/usr/bin/flatpak','update','--'+scope,'-y',ref])
            session.emit('completed',id=identifier)
            session.result(name,'aggiornato',(available or 'Nuova revisione')+'\nFlatpak '+scope+': '+ref)
