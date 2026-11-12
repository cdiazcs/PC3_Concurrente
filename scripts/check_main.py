"""Preflight de integration sin instalar dependencias. No simula RabbitMQ ni bases de datos."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'server-java/CentralServer.java',
    'server-java/DistributedCnn.java',
    'workers/python/worker.py',
    'workers/java/WorkerJava.java',
    'workers/csharp/Worker.cs',
    'cnn_python/model.py',
    'model/weights/weights.txt',
    'model/data/geometry-v1.zip',
    'frontend-java/OpenAICubesGUI.java',
    'databases/postgresql/01_schema.sql',
    'databases/mariadb/01_schema.sql',
    'contracts/RABBITMQ_V1.md',
]

def main():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        for name in missing:
            print('FALTA:', name, file=sys.stderr)
        return 1
    print('OK: estructura de integration y fuentes existentes')
    for name in ('solicitud_modeloA', 'resultado_modeloA'):
        data = json.loads((ROOT / 'contracts/examples' / (name + '.json')).read_text(encoding='utf-8'))
        assert data['schemaVersion'] == 1 and data['idSolicitud']
    print('OK: ejemplos de contratos JSON parseables; ver test_cross_language para compatibilidad ejecutada')
    result = subprocess.run([sys.executable, '-m', 'cnn_python.predict',
                             'model/examples/circulo-0.png'], cwd=ROOT, text=True, capture_output=True, timeout=30)
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    prediction = json.loads(result.stdout)
    assert prediction['class'] == 'circulo', prediction
    print('OK: inferencia local CNN =', prediction['class'])
    javac = shutil.which('javac')
    if javac:
        from build import compile_java
        with tempfile.TemporaryDirectory() as build:
            compile_java(build)
        print('OK: compilacion de fuentes Java')
    else:
        print('NO VERIFICADO: Java (javac no instalado)')
    if shutil.which('dotnet'):
        print('Disponibilidad: dotnet instalado, probar dotnet build en CI/equipo')
    else:
        print('NO VERIFICADO: worker C# (.NET SDK no instalado aqui)')
    print('ALCANCE: preflight sin servicios; RabbitMQ y TCP se verifican por separado')
    return 0

if __name__ == '__main__':
    sys.exit(main())
