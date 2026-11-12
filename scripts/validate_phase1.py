"""Reproduce dos entrenamientos completos sin sobrescribir artefactos oficiales.

Solo stdlib. Desde la raiz: python3 scripts/validate_phase1.py --output build/phase1
El directorio de salida debe ser nuevo. No evalua generalizacion externa.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cnn_python.dataset import DEFAULT_DATASET, generate, load_split
from cnn_python.evaluate import evaluate
from cnn_python.model import CNN, DEFAULT_WEIGHTS, load_weights
from cnn_python.train import metrics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('build/phase1'))
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('output_exists: elige un directorio nuevo para preservar evidencia')
    output.mkdir(parents=True)
    protected = [DEFAULT_WEIGHTS, DEFAULT_DATASET,
                 *sorted((ROOT/'model/training').glob('*')),
                 *sorted((ROOT/'model/evaluation').glob('*'))]
    original = {str(p.relative_to(ROOT)): sha(p) for p in protected if p.is_file()}
    sources = {str(p.relative_to(ROOT)): sha(p) for p in
               [*sorted((ROOT/'cnn_python').glob('*.py')), Path(__file__).resolve()]}
    legacy = json.loads((ROOT/'model/training/training.json').read_text(encoding='utf-8'))
    provenance = {}
    for name, expected in legacy['source_sha256'].items():
        raw = (ROOT/'cnn_python'/name).read_bytes()
        lf = raw.replace(b'\r\n', b'\n')
        variants = {'raw': raw, 'LF': lf, 'CRLF': lf.replace(b'\n', b'\r\n'),
                    'BOM+LF': b'\xef\xbb\xbf'+lf,
                    'BOM+CRLF': b'\xef\xbb\xbf'+lf.replace(b'\n', b'\r\n')}
        provenance[name] = {'recorded_sha256': expected,
                            'current_sha256': hashlib.sha256(raw).hexdigest(),
                            'matching_encodings': [key for key, value in variants.items()
                                                   if hashlib.sha256(value).hexdigest() == expected]}
    started = time.perf_counter()
    regenerated = output/'geometry-v1.zip'
    generate(regenerated)
    dataset_matches = sha(regenerated) == sha(DEFAULT_DATASET)
    with zipfile.ZipFile(regenerated) as fresh, zipfile.ZipFile(DEFAULT_DATASET) as official_zip:
        dataset_content_matches = (fresh.namelist() == official_zip.namelist()
                                   and all(fresh.read(name) == official_zip.read(name)
                                           for name in fresh.namelist()))
    require(dataset_content_matches, 'dataset_content_regeneration_mismatch')
    runs, models = [], []
    for number in (1, 2):
        run = output/f'run-{number}'
        command = [sys.executable, '-m', 'cnn_python.train', '--weights', str(run/'weights.txt'),
                   '--report-dir', str(run), '--epochs', '60']
        run.mkdir()
        print(f'Entrenamiento {number}/2: 60 epocas; salida {run}', flush=True)
        with (run/'train.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=600)
        require(result.returncode == 0, f'training_failed: {run}/train.log')
        report = json.loads((run/'training.json').read_text(encoding='utf-8'))
        model = CNN.load(run/'weights.txt')
        test, _ = evaluate(model, load_split(split='test'))
        (run/'evaluation.json').write_text(json.dumps(test, indent=2)+'\n', encoding='utf-8')
        require(all(math.isfinite(value) for values in model.weights.values() for value in values),
                'nonfinite_weights')
        require(all(value > 0 for value in report['parameter_change_l2'].values()), 'unchanged_layer')
        require(report['final_validation']['cross_entropy'] < report['initial_validation']['cross_entropy'],
                'validation_did_not_improve')
        best = min(report['history'], key=lambda row: row['validation_cross_entropy'])
        require(report['best_epoch'] == best['epoch'], 'wrong_checkpoint_selection')
        require(all(report['source_sha256'][name] == sources['cnn_python/'+name]
                    for name in ('model.py', 'dataset.py', 'train.py')), 'source_changed_during_run')
        runs.append({'command': command, 'weights_sha256': sha(run/'weights.txt'),
                     **{key: report[key] for key in ('epochs_run', 'best_epoch', 'seed', 'batch_size',
                         'learning_rate', 'initial_validation', 'final_training', 'final_validation',
                         'parameter_change_l2', 'seconds')}, 'test': test})
        models.append(model)
        print(f'Run {number}: val_loss={report["final_validation"]["cross_entropy"]:.9g}, '
              f'test_accuracy={test["accuracy"]:.2%}', flush=True)
    identical = (output/'run-1/weights.txt').read_bytes() == (output/'run-2/weights.txt').read_bytes()
    same_history = (output/'run-1/history.csv').read_bytes() == (output/'run-2/history.csv').read_bytes()
    require(identical and same_history, 'nonreproducible_runs')
    official = CNN.load()
    max_difference = max(abs(a-b) for image, _ in load_split(split='test')
                         for a, b in zip(official.predict(image).probabilities,
                                         models[0].predict(image).probabilities))
    official_test, _ = evaluate(official, load_split(split='test'))
    legacy_weights = load_weights()
    max_weight_difference = max(abs(a-b) for key in legacy_weights
                                for a, b in zip(legacy_weights[key], models[0].weights[key]))
    require(sources == {name: sha(ROOT/name) for name in sources}, 'sources_changed')
    require(original == {name: sha(ROOT/name) for name in original}, 'official_artifact_changed')
    summary = {'schema_version': 1, 'scope': 'sequential_training_and_synthetic_evaluation_only',
               'external_evaluation': 'PENDING: no independent documented images available',
               'timestamp_utc': datetime.now(timezone.utc).isoformat(),
               'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                               'zlib_runtime': zlib.ZLIB_RUNTIME_VERSION},
               'source_sha256': sources, 'legacy_source_provenance': provenance,
               'dataset_regenerated_identically': dataset_matches,
               'dataset_regenerated_contents_identical': dataset_content_matches,
               'regenerated_dataset_sha256': sha(regenerated),
               'official_artifacts_sha256': original, 'official_artifacts_unchanged': True,
               'two_training_runs_identical_weights': identical,
               'two_training_runs_identical_history': same_history,
               'matches_official_weights_bytes': runs[0]['weights_sha256'] == sha(DEFAULT_WEIGHTS),
               'max_weight_difference_from_official': max_weight_difference,
               'max_test_probability_difference_from_official': max_difference,
               'official_test': official_test, 'runs': runs,
               'total_seconds': time.perf_counter()-started}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(f'Evidencia: {output}/summary.json; pesos oficiales intactos.', flush=True)


if __name__ == '__main__':
    main()
