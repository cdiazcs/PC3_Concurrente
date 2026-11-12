"""Fundamental phase IV tests, all math uses the validated backward."""
from concurrent.futures import ThreadPoolExecutor
import copy
import math
from pathlib import Path
import random
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cnn_python.train import initial_weights
from cnn_python.training_math import compute_gradients
from cnn_python.gradient_protocol import make_tasks,execute_task,aggregate_gradients,validate_task,decode
from cnn_python.model_state import ModelState
from cnn_python.model import SHAPES


def examples(count=7):
    rng=random.Random(19)
    return [(tuple(rng.uniform(.02,.98) for _ in range(256)),i%3) for i in range(count)]


class GradientTests(unittest.TestCase):
    def setUp(self):
        self.data=examples();self.weights=initial_weights(23)
        self.tasks=make_tasks('unit-run',1,0,0,self.weights,list(range(7)),'fixture',3)
        self.results=[execute_task(task,self.data,'fixture') for task in self.tasks]

    def test_fundamental_unequal_partitions_gradients_and_one_update(self):
        self.assertEqual([t['count'] for t in self.tasks],[3,2,2])
        original=copy.deepcopy(self.weights)
        serial_loss,serial=compute_gradients(self.weights,self.data)
        loss,merged=aggregate_gradients(self.tasks,list(reversed(self.results)))
        self.assertAlmostEqual(loss,serial_loss,delta=1e-12)
        self.assertEqual(self.weights,original)
        self.assertLess(max(abs(a-b) for key in SHAPES for a,b in zip(serial[key],merged[key])),1e-12)
        a=ModelState(self.weights);b=ModelState(self.weights)
        a.commit('1:0',0,serial);b.commit('1:0',0,merged)
        self.assertLess(max(abs(x-y) for key in SHAPES for x,y in zip(a.weights[key],b.weights[key])),1e-12)
        self.assertEqual(a.optimizer.step,b.optimizer.step)

    def test_weighted_known_values_not_average_of_means(self):
        tasks=make_tasks('known',1,0,0,self.weights,[0,1,2],'fixture',2)
        results=[execute_task(t,self.data,'fixture') for t in tasks]
        for r,g,l in zip(results,(1,3),(2,8)):
            r['gradients']={k:[g]*n for k,n in SHAPES.items()};r['meanLoss']=l
        loss,gradient=aggregate_gradients(tasks,results)
        self.assertEqual(loss,4)
        self.assertTrue(all(abs(v-5/3)<1e-15 for values in gradient.values() for v in values))

    def test_duplicates_and_concurrent_commit_are_idempotent(self):
        _,gradient=aggregate_gradients(self.tasks,self.results+[self.results[0]])
        state=ModelState(self.weights)
        with ThreadPoolExecutor(max_workers=8) as pool:
            committed=list(pool.map(lambda _:state.commit('1:0',0,gradient),range(24)))
        self.assertEqual(sum(committed),1);self.assertEqual(state.version,1);self.assertEqual(state.optimizer.step,1)
        with self.assertRaises(ValueError):state.commit('other-step',0,gradient)

    def test_invalid_stale_incomplete_conflicting_and_nonfinite(self):
        with self.assertRaises(ValueError):aggregate_gradients(self.tasks,self.results[:-1])
        variants=[('modelVersion',1),('runId','other'),('epoch',2),('batchId',9),('count',999),
                  ('weightsHash','other'),('datasetHash','other'),('meanLoss',math.nan)]
        for key,value in variants:
            bad=copy.deepcopy(self.results);bad[0][key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):aggregate_gradients(self.tasks,bad)
        for values in ([math.inf]*9,[0]*8):
            bad=copy.deepcopy(self.results);bad[0]['gradients']['FILTER1']=values
            with self.assertRaises(ValueError):aggregate_gradients(self.tasks,bad)
        duplicate=copy.deepcopy(self.results[0]);duplicate['gradients']['B2']=list(duplicate['gradients']['B2']);duplicate['gradients']['B2'][0]+=1
        with self.assertRaises(ValueError):aggregate_gradients(self.tasks,self.results+[duplicate])
        with self.assertRaises(ValueError):decode(b'{"x":NaN}')
        with self.assertRaises(ValueError):decode(b'{"x":1e999}')
        with self.assertRaises(ValueError):decode(b'{"x":1,"x":2}')

    def test_task_validation_dataset_weights_indices_and_version(self):
        for key,value in (('datasetHash','wrong'),('weightsHash','wrong'),('indices',[-1]),
                          ('modelVersion',-1),('schemaVersion',True)):
            task=copy.deepcopy(self.tasks[0]);task[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_task(task,'fixture',7)


if __name__=='__main__':unittest.main(verbosity=2)
