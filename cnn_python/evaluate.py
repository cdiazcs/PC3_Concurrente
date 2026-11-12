
import argparse
import csv
import hashlib
import json
from pathlib import Path

from .dataset import DEFAULT_DATASET, ROOT, load_split, read_manifest
from .model import CLASSES, CNN, DEFAULT_WEIGHTS, SHAPES, cross_entropy


def evaluate(model, examples):
    confusion = [[0]*3 for _ in range(3)]
    predictions = []
    total_loss = 0.0
    for index, (pixels, expected) in enumerate(examples):
        state = model.trace(pixels)
        total_loss += cross_entropy(state['logits'], expected)
        probabilities = state['probabilities']
        predicted = max(range(len(CLASSES)), key=probabilities.__getitem__)
        confusion[expected][predicted] += 1
        predictions.append({'sample': index, 'expected': CLASSES[expected],
                            'predicted': CLASSES[predicted],
                            **dict(zip(CLASSES, probabilities))})
    total = len(examples)
    if not total:
        raise ValueError('empty_evaluation')
    per_class = {CLASSES[i]: confusion[i][i]/sum(confusion[i])
                 if sum(confusion[i]) else None for i in range(3)}
    return {'classes': CLASSES, 'samples': total,
            'accuracy': sum(confusion[i][i] for i in range(3))/total,
            'cross_entropy': total_loss/total,
            'confusion_matrix_rows_true_columns_predicted': confusion,
            'per_class_recall': per_class,
            'per_class_accuracy': dict(per_class),
            'per_class_accuracy_definition': 'correct / true samples of that class (recall)',
            'model_configuration': {
                'input_shape': [16, 16, 1],
                'convolution': {'filters': 2, 'kernel': [3, 3], 'stride': 1,
                                'padding': 'valid', 'bias': False, 'activation': 'relu'},
                'pooling': {'type': 'max', 'size': [2, 2], 'stride': 2},
                'flatten': 98, 'dense_units': [8, 3],
                'dense_activations': ['relu', 'softmax'],
                'parameter_sections': dict(SHAPES),
                'trainable_parameters': sum(SHAPES.values())}}, predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--weights', type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument('--output', type=Path, default=ROOT / 'model' / 'evaluation')
    args = parser.parse_args()
    report, predictions = evaluate(CNN.load(args.weights), load_split(args.dataset, 'test'))
    report.update({'split': 'test', 'seed': read_manifest(args.dataset)['seeds']['test'],
                   'dataset_sha256': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                   'weights_sha256': hashlib.sha256(args.weights.read_bytes()).hexdigest(),
                   'minimum_accuracy': .85, 'meets_target': report['accuracy'] >= .85})
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (args.output / 'predictions.csv').open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
