#!/usr/bin/python3
"""Install only the utility's own desktop shortcut for the current user."""
from pathlib import Path
import shutil
import subprocess
source=Path('/usr/share/applications/ubuntu-update-utility.desktop')
if not source.exists(): raise SystemExit('Installare prima il pacchetto .deb.')
result=subprocess.run(['xdg-user-dir','DESKTOP'],capture_output=True,text=True,check=True)
folder=Path(result.stdout.strip())
if not folder.is_absolute() or folder==Path.home(): raise SystemExit('Directory Desktop non configurata.')
folder.mkdir(parents=True,exist_ok=True)
target=folder/source.name
shutil.copy2(source,target);target.chmod(0o755)
subprocess.run(['gio','set',str(target),'metadata::trusted','true'],check=False)
print('Collegamento creato:',target)
