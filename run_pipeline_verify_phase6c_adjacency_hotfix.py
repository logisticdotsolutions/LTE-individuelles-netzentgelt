from __future__ import annotations
import shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent; stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); backup=ROOT/'.netzentgelt_hotfix_backups'/('runtime_phase6c_adjacency_'+stamp); backup.mkdir(parents=True)
db=ROOT/'data/02_duckdb/netzentgelt.duckdb'; exports=ROOT/'data/03_exports'
if db.exists(): shutil.copy2(db,backup/'netzentgelt.duckdb')
if exports.exists(): shutil.copytree(exports,backup/'03_exports')
def run(args):
 c=subprocess.run(args,cwd=ROOT)
 if c.returncode: raise RuntimeError('Befehl fehlgeschlagen: '+' '.join(map(str,args)))
try:
 run([sys.executable,str(ROOT/'scripts/run_all.py')]); run([sys.executable,str(ROOT/'payload/scripts/verify_phase6c_adjacency_hotfix.py')])
 print('OK: Pipeline und Anschlusslogik-Verifikation erfolgreich.')
except Exception:
 if (backup/'netzentgelt.duckdb').exists(): shutil.copy2(backup/'netzentgelt.duckdb',db)
 if (backup/'03_exports').exists():
  if exports.exists(): shutil.rmtree(exports)
  shutil.copytree(backup/'03_exports',exports)
 print('FEHLER: Vorheriger Datenstand wurde wiederhergestellt.')
 raise
