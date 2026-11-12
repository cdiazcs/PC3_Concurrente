"""Build portable: JDK 21+, Python stdlib, optional .NET 8. No services."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import py_compile
import argparse
import re
ROOT = Path(__file__).resolve().parents[1]

def java_sources():
    return [str(p) for directory in ('server-java','clients-java','frontend-java','workers/java','benchmarks')
            for p in sorted((ROOT/directory).rglob('*.java'))]

def compile_java(output):
    if not shutil.which('javac'):
        raise RuntimeError('JDK 21+ requerido: javac no disponible')
    version = subprocess.check_output(['javac', '-version'], text=True, stderr=subprocess.STDOUT)
    match = re.search(r'javac (\d+)', version)
    if not match or int(match.group(1)) < 21:
        raise RuntimeError('JDK 21+ requerido para el cierre Fase I')
    Path(output).mkdir(parents=True, exist_ok=True)
    subprocess.run(['javac','--release','17','-encoding','UTF-8','-cp',str(ROOT/'lib'/'*'),
                    '-d',str(output),*java_sources()],cwd=ROOT,check=True)

def classpath(output):
    return str(output)+os.pathsep+str(ROOT/'lib'/'*')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=('all', 'java', 'python', 'csharp'), default='all')
    parser.add_argument('--require-dotnet', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.component in ('all', 'java'):
        compile_java(ROOT/'build')
        print('OK: JDK 21+; bytecode release 17', flush=True)
    if args.component in ('all', 'python'):
        for folder in ('cnn_python','workers/python','messaging','tests','scripts','databases/mariadb','web-server','benchmarks'):
            for path in (ROOT/folder).rglob('*.py'):
                py_compile.compile(str(path),doraise=True)
        print('OK: sintaxis Python', flush=True)
    if args.component in ('all', 'csharp'):
        if shutil.which('dotnet'):
            subprocess.run(['dotnet','--list-sdks'], check=True)
            subprocess.run(['dotnet','build','workers/csharp/Worker.csproj','--nologo'],check=True)
            print('OK: C# compilado (net8.0)', flush=True)
        elif args.require_dotnet or args.component == 'csharp':
            raise RuntimeError('SDK .NET 8 requerido para este perfil')
        else:
            print('NO VERIFICADO: C# (.NET 8 SDK no disponible)', flush=True)
    return 0
if __name__ == '__main__':
    sys.exit(main())
