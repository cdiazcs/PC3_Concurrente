"""Real spawn processes, identical schedules and mathematical updates."""
import unittest
from test_gradient_aggregation import examples
from cnn_python.train import initial_weights
from cnn_python.gradient_protocol import make_tasks,aggregate_gradients
from cnn_python.training_backends import SequentialBackend,ParallelBackend
from cnn_python.train_synchronous import train_sync
from cnn_python.model import SHAPES


class ParallelTests(unittest.TestCase):
    def test_real_process_gradients_and_training_match_sequential(self):
        data=examples(24);validation=examples(6)
        sequential=SequentialBackend(data,'fixture');parallel=ParallelBackend(data,'fixture',2,15)
        try:
            tasks=make_tasks('parallel-test',1,0,0,initial_weights(23),list(range(24)),'fixture',2)
            results=parallel.map(tasks)
            self.assertEqual(len({r['pid'] for r in results}),2)
            self.assertEqual([r['modelVersion'] for r in results],[0,0])
            _,a=aggregate_gradients(tasks,sequential.map(tasks));_,b=aggregate_gradients(tasks,results)
            self.assertLess(max(abs(x-y) for k in SHAPES for x,y in zip(a[k],b[k])),1e-12)
            w,report,s=train_sync(data,validation,'fixture',sequential,epochs=3,batch_size=7,seed=23)
            v,other,t=train_sync(data,validation,'fixture',parallel,epochs=3,batch_size=7,seed=23)
            self.assertLess(max(abs(x-y) for k in SHAPES for x,y in zip(w[k],v[k])),1e-10)
            self.assertEqual(s.optimizer.step,12);self.assertEqual(t.optimizer.step,12)
            self.assertAlmostEqual(report['finalValidation']['cross_entropy'],other['finalValidation']['cross_entropy'],delta=1e-10)
        finally:parallel.close()

    def test_worker_exception_does_not_update_model(self):
        data=examples(6);parallel=ParallelBackend(data,'fixture',2,10)
        try:
            tasks=make_tasks('bad',1,0,0,initial_weights(23),list(range(6)),'wrong',2)
            with self.assertRaises(ValueError):parallel.map(tasks)
            self.assertTrue(parallel.failed)
        finally:parallel.close()


if __name__=='__main__':unittest.main(verbosity=2)
