"""Regresiones numericas y preprocesamiento de fase 1, sin servicios externos."""
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cnn_python.evaluate import evaluate
from cnn_python.images import PNG, encode_png, read_image
from cnn_python.model import CNN, SHAPES, cross_entropy, loss_and_gradients
from cnn_python.train import initial_weights, metrics, train


class NumericalTests(unittest.TestCase):
    def test_adam_two_updates_bias_correction_and_gradient_clipping(self):
        for first_gradient, clipped in ((2.0, 2.0), (10.0, 5.0)):
            with self.subTest(first_gradient=first_gradient):
                zeros = {key: [0.0]*count for key, count in SHAPES.items()}
                gradients = []
                for value in (first_gradient, -1.0):
                    g = {key: [0.0]*count for key, count in SHAPES.items()}
                    g['B2'][0] = value
                    gradients.append((1.0, g))
                # Closed-form scalar Adam reference, independent of CNN derivatives.
                first = -.003*clipped/(clipped+1e-8)
                moment = .9*(.1*clipped)-.1
                variance = .999*(.001*clipped**2)+.001
                expected = first-.003*(moment/(1-.9**2))/(math.sqrt(variance/(1-.999**2))+1e-8)
                with mock.patch('cnn_python.train.initial_weights', return_value=zeros), \
                        mock.patch('cnn_python.train.loss_and_gradients', side_effect=gradients), \
                        mock.patch('cnn_python.train.metrics', side_effect=[
                            {'accuracy': 0, 'cross_entropy': value} for value in (3, 2, 1)]):
                    weights, report = train([([0]*256, 0)], [([0]*256, 0)],
                                            epochs=2, batch_size=1, verbose=False)
                self.assertAlmostEqual(weights['B2'][0], expected, delta=1e-15)
                self.assertEqual(report['best_epoch'], 2)
                self.assertEqual(weights['B2'][1:], [0, 0])

    def test_evaluation_confusion_errors_absent_classes_and_configuration(self):
        model = CNN({key: [0.0]*count for key, count in SHAPES.items()})
        report, predictions = evaluate(model, [([0]*256, label) for label in (0, 1, 2, 1)])
        self.assertEqual(report['samples'], 4)
        self.assertEqual(report['accuracy'], .25)
        self.assertAlmostEqual(report['cross_entropy'], math.log(3), delta=1e-15)
        self.assertEqual(report['confusion_matrix_rows_true_columns_predicted'],
                         [[1, 0, 0], [2, 0, 0], [1, 0, 0]])
        self.assertEqual(report['per_class_accuracy'], {'circulo': 1, 'cruz': 0, 'triangulo': 0})
        self.assertEqual(report['per_class_accuracy'], report['per_class_recall'])
        self.assertEqual(report['model_configuration']['trainable_parameters'], 837)
        self.assertEqual(report['model_configuration']['parameter_sections'], SHAPES)
        self.assertTrue(all(row['predicted'] == 'circulo' for row in predictions))
        subset, _ = evaluate(model, [([0]*256, 0)])
        self.assertIsNone(subset['per_class_accuracy']['triangulo'])

    def test_loss_large_common_offset_and_underflow(self):
        self.assertAlmostEqual(cross_entropy([1e16]*3, 1), math.log(3), delta=1e-15)
        self.assertEqual(cross_entropy([1000, 0, -1000], 2), 2000)
        self.assertAlmostEqual(cross_entropy([4, 5, 6], 0),
                               cross_entropy([1004, 1005, 1006], 0), delta=1e-14)
        for logits, label in (([], 0), ([math.inf], 0), ([math.nan], 0),
                              ([0, 1], -1), ([0, 1], 2), ([0, 1], True)):
            with self.subTest(logits=logits, label=label), self.assertRaises(ValueError):
                cross_entropy(logits, label)

    def test_evaluation_loss_matches_reference_and_handles_zero_probabilities(self):
        weights = {key: [0.0]*count for key, count in SHAPES.items()}
        weights['B2'] = [1000, 0, -1000]
        examples = [([0.0]*256, 2)]
        report, predictions = evaluate(CNN(weights), examples)
        self.assertEqual(report['cross_entropy'], 2000)
        self.assertEqual(report['accuracy'], 0)
        self.assertEqual(predictions[0]['triangulo'], 0)
        self.assertEqual(report['cross_entropy'], metrics(CNN(weights), examples)['cross_entropy'])
        weights['B2'] = [1e16]*3
        model = CNN(weights)
        self.assertAlmostEqual(evaluate(model, examples)[0]['cross_entropy'], math.log(3))
        self.assertAlmostEqual(loss_and_gradients(weights, examples[0][0], 2)[0], math.log(3))
        for function in (lambda: evaluate(model, []), lambda: metrics(model, []),
                         lambda: evaluate(model, [([0.0]*256, -1)])):
            with self.assertRaises(ValueError):
                function()

    def test_gradients_all_parameters_more_seeds_and_labels(self):
        # Continuous random inputs avoid deliberate ReLU/pool nondifferentiable cases.
        epsilon = 1e-5
        for seed, label in ((47, 0), (89, 1)):
            rng = random.Random(seed+100)
            image = [rng.uniform(.05, .95) for _ in range(256)]
            weights = initial_weights(seed)
            _, gradients = loss_and_gradients(weights, image, label)
            checked = 0
            for key, count in SHAPES.items():
                for index in range(count):
                    original = weights[key][index]
                    weights[key][index] = original+epsilon
                    positive = loss_and_gradients(weights, image, label)[0]
                    weights[key][index] = original-epsilon
                    negative = loss_and_gradients(weights, image, label)[0]
                    weights[key][index] = original
                    self.assertAlmostEqual(gradients[key][index], (positive-negative)/(2*epsilon),
                                           delta=2e-6, msg=f'{seed}:{key}[{index}]')
                    checked += 1
            self.assertEqual(checked, 837)

    def test_pool_tie_backward_uses_first_winner(self):
        weights = {key: [0.0]*count for key, count in SHAPES.items()}
        weights['FILTER1'][4] = 1
        weights['W1'][0] = 1
        weights['W2'][0] = 1
        # Each convolution has identical positive values; only pool[0] affects loss.
        image = [.5]*256
        state = CNN(weights).trace(image)
        self.assertEqual(state['winners'][0][0], 0)
        _, gradients = loss_and_gradients(weights, image, 0)
        delta = state['probabilities'][0]-1
        for value in gradients['FILTER1']:
            self.assertAlmostEqual(value, .5*delta, delta=1e-15)
        self.assertEqual(gradients['FILTER2'], [0]*9)

    def test_relu_zero_and_negative_block_backprop(self):
        for filter_value in (0, -1):
            weights = {key: [0.0]*count for key, count in SHAPES.items()}
            weights['FILTER1'] = [filter_value]*9
            weights['FILTER2'] = [filter_value]*9
            weights['W1'] = [1]*784
            weights['W2'] = [1]*24
            _, gradients = loss_and_gradients(weights, [.5]*256, 0)
            for key in ('FILTER1', 'FILTER2', 'W1', 'B1', 'W2'):
                self.assertEqual(gradients[key], [0]*SHAPES[key])
            self.assertAlmostEqual(gradients['B2'][0], -2/3)

    def test_training_decreases_loss_with_partial_batch_and_selects_validation(self):
        rng = random.Random(900)
        # Five examples with batch=3 exercise the last, shorter batch.
        examples = [([rng.uniform(0, 1) for _ in range(256)], 0) for _ in range(5)]
        weights, report = train(examples, examples, epochs=6, batch_size=3, seed=47, verbose=False)
        self.assertLess(metrics(CNN(weights), examples)['cross_entropy'],
                        report['initial_validation']['cross_entropy'])
        best = min(report['history'], key=lambda row: row['validation_cross_entropy'])
        self.assertEqual(report['best_epoch'], best['epoch'])
        self.assertAlmostEqual(metrics(CNN(weights), examples)['cross_entropy'],
                               best['validation_cross_entropy'], delta=1e-15)
        self.assertTrue(all(math.isfinite(v) for values in weights.values() for v in values))


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'JDK no disponible')
class PreprocessingParityTests(unittest.TestCase):
    def test_java_python_pixels_png_pgm_and_resize(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            probe = folder/'PixelProbe.java'
            probe.write_text('''import java.io.File;
public class PixelProbe {
 public static void main(String[] args) throws Exception {
  for (String path : args) {
   double[] values = ClientCli.prepareImage(new File(path)).pixels();
   for (int i=0; i<values.length; i++) System.out.print((i==0 ? "" : ",")+values[i]);
   System.out.println();
  }
 }
}
''', encoding='utf-8')
            compiled = subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(folder),
                                       str(ROOT/'clients-java/ClientCli.java'), str(probe)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            paths = sorted((ROOT/'model/examples').glob('*.png'))
            gray = folder/'gray.bin'
            gray.write_bytes(encode_png(23, 19, [(i*17) % 256 for i in range(23*19)]))
            paths.append(gray)
            for magic in ('P2', 'P5'):
                path = folder/(magic+'.pgm')
                pixels = [10, 32, 50, 100, 0, 25]
                body = bytes(pixels) if magic == 'P5' else ' '.join(map(str, pixels)).encode()
                path.write_bytes((magic+'\r\n# parity\r\n3 2\r\n100\r\n').encode()+body)
                paths.append(path)
            def chunk(kind, body):
                return struct.pack('!I', len(body))+kind+body+struct.pack('!I', zlib.crc32(kind+body))
            rgba = folder/'rgba.png'
            header = struct.pack('!IIBBBBB', 2, 2, 8, 6, 0, 0, 0)
            raw = bytes([0, 255, 0, 0, 128, 0, 255, 0, 255,
                         0, 0, 0, 255, 0, 255, 255, 255, 200])
            rgba.write_bytes(PNG+chunk(b'IHDR', header)+chunk(b'IDAT', zlib.compress(raw))+chunk(b'IEND', b''))
            paths.append(rgba)
            result = subprocess.run(['java', '-Djava.awt.headless=true', '-cp', str(folder),
                                     'PixelProbe', *map(str, paths)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = result.stdout.splitlines()
            self.assertEqual(len(rows), len(paths))
            for path, row in zip(paths, rows):
                actual = list(map(float, row.split(',')))
                self.assertEqual(len(actual), 256)
                for a, b in zip(actual, read_image(path)):
                    self.assertAlmostEqual(a, b, delta=1e-12, msg=str(path))


if __name__ == '__main__':
    unittest.main(verbosity=2)
