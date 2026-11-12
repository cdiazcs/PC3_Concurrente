"""Ejecuta la suite integral local con evidencia JSON, sin instalar herramientas.

python3 scripts/validate_phase2.py --dotnet-dir /tmp/pc3-dotnet8 --output build/phase2
Requiere Python, JDK y SDK .NET 8. Usa sockets localhost; no acredita nodos fisicos.
El directorio de salida debe ser nuevo. No cambia la configuracion global.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet-dir', type=Path)
    parser.add_argument('--output', type=Path, default=Path('build/phase2'))
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('output_exists: elige una carpeta nueva para preservar evidencia')
    paths = [str(args.dotnet_dir.resolve())] if args.dotnet_dir else []
    tool_path = os.pathsep.join([*paths, os.environ.get('PATH', '')])
    for tool in ('java', 'javac', 'dotnet'):
        if not shutil.which(tool, path=tool_path):
            parser.error(f'missing_tool: {tool}; no se instala automaticamente')
    output.mkdir(parents=True)
    tools = output/'tools'
    tools.mkdir()
    if os.name == 'posix':
        # Historical benchmark code invokes "python"; provide a process-local alias.
        (tools/'python').symlink_to(sys.executable)
        paths.append(str(tools))
    os.environ['PATH'] = os.pathsep.join([*paths, os.environ.get('PATH', '')])
    os.environ['JAVA_TOOL_OPTIONS'] = (os.environ.get('JAVA_TOOL_OPTIONS', '')
                                      +' -Djava.awt.headless=true').strip()
    os.environ['DOTNET_CLI_HOME'] = str(output/'dotnet-cli')
    os.environ['NUGET_PACKAGES'] = str(output/'nuget-cache')
    os.environ['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    os.environ['DOTNET_SKIP_FIRST_TIME_EXPERIENCE'] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT/'tests'))
    protected = {str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'model').rglob('*') if p.is_file()}
    folders = ('cnn_python', 'workers', 'server-java', 'clients-java', 'frontend-java', 'benchmarks', 'tests')
    sources = {str(p.relative_to(ROOT)): sha(p) for folder in folders for p in (ROOT/folder).rglob('*')
               if p.is_file() and p.suffix in ('.py', '.java', '.cs', '.csproj')
               and not {'obj', 'bin', '__pycache__'} & set(p.parts)}
    sources[str(Path(__file__).resolve().relative_to(ROOT))] = sha(Path(__file__).resolve())
    versions = {}
    for name, command in (('python', [sys.executable, '--version']), ('java', ['java', '-version']),
                          ('javac', ['javac', '-version']), ('dotnet', ['dotnet', '--info'])):
        p = subprocess.run(command, capture_output=True, text=True, timeout=30)
        versions[name] = (p.stdout+p.stderr).strip()
    records = []
    class EvidenceResult(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            records.append({'test': test.id(), 'status': 'passed'})
        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            records.append({'test': test.id(), 'status': 'skipped', 'reason': reason})
        def addFailure(self, test, err):
            super().addFailure(test, err)
            records.append({'test': test.id(), 'status': 'failed'})
        def addError(self, test, err):
            super().addError(test, err)
            records.append({'test': test.id(), 'status': 'error'})
    print(f'Suite integral localhost; log: {output}/tests.log', flush=True)
    started = time.monotonic()
    log_path = output/'tests.log'
    with log_path.open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'), pattern='test_*.py')
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=EvidenceResult).run(suite)
    elapsed = time.monotonic()-started
    unchanged = all(sha(ROOT/name) == value for name, value in protected.items())
    source_unchanged = all(sha(ROOT/name) == value for name, value in sources.items())
    summary = {'schema_version': 1, 'scope': 'localhost_integration_not_physical_distribution',
               'timestamp_utc': datetime.now(timezone.utc).isoformat(),
               'platform': platform.platform(), 'versions': versions,
               'command': [sys.executable, *sys.argv], 'tests_run': result.testsRun,
               'failures': len(result.failures), 'errors': len(result.errors),
               'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
               'seconds': elapsed, 'source_sha256': sources, 'sources_unchanged': source_unchanged,
               'official_model_artifacts_sha256': protected, 'official_model_artifacts_unchanged': unchanged,
               'log_sha256': sha(log_path), 'results': records}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(f'{result.testsRun} tests; failures={len(result.failures)}; errors={len(result.errors)}; '
          f'skipped={len(result.skipped)}; seconds={elapsed:.2f}; model_unchanged={unchanged}', flush=True)
    return 0 if result.wasSuccessful() and unchanged and source_unchanged else 1


if __name__ == '__main__':
    sys.exit(main())
