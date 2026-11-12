"""Load literal KEY=VALUE configuration without shell evaluation, then run a command."""
from pathlib import Path
import os
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    if len(sys.argv)<3: raise SystemExit('Uso: python scripts/run_env.py .env comando [argumentos...]')
    values={}
    for line in Path(sys.argv[1]).read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        key,separator,value=line.partition('=')
        if not separator or not key.strip().isidentifier(): raise SystemExit('Configuracion KEY=VALUE invalida')
        values[key.strip()]=value.strip()
    sys.exit(subprocess.call(sys.argv[2:],cwd=ROOT,env={**os.environ,**values}))
