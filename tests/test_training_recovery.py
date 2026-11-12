import json
from pathlib import Path
import tempfile
import unittest
from test_gradient_aggregation import examples
from cnn_python.training_backends import SequentialBackend
from cnn_python.train_synchronous import train_sync
from cnn_python.model_state import ModelState,CoordinatorLease
from cnn_python.model import SHAPES


class RecoveryTests(unittest.TestCase):
    def test_only_one_coordinator_lease_for_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=CoordinatorLease(tmp)
            try:
                with self.assertRaisesRegex(ValueError,'lease_exists'):CoordinatorLease(tmp)
            finally:first.close()
            second=CoordinatorLease(tmp);second.close()

    def test_atomic_checkpoint_resumes_mid_epoch_without_repeated_adam(self):
        data=examples(11);validation=examples(4)
        w,r,full=train_sync(data,validation,'fixture',SequentialBackend(data,'fixture'),epochs=3,batch_size=6,seed=23)
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint=Path(tmp)/'state.json'
            _,paused,partial=train_sync(data,validation,'fixture',SequentialBackend(data,'fixture'),
                epochs=3,batch_size=6,seed=23,checkpoint=checkpoint,max_steps=2)
            self.assertFalse(paused['complete']);self.assertEqual(partial.optimizer.step,2)
            v,resumed,state=train_sync(data,validation,'fixture',SequentialBackend(data,'fixture'),
                epochs=3,batch_size=6,seed=23,checkpoint=checkpoint,resume=True)
            self.assertEqual(full.weights,state.weights);self.assertEqual(w,v)
            self.assertEqual(full.optimizer.first,state.optimizer.first)
            self.assertEqual(full.optimizer.second,state.optimizer.second)
            self.assertEqual(state.optimizer.step,6);self.assertTrue(resumed['complete'])
            self.assertFalse(checkpoint.with_name('state.json.tmp').exists())
            with self.assertRaises(ValueError):train_sync(data,validation,'fixture',SequentialBackend(data,'fixture'),
                epochs=4,batch_size=6,seed=23,checkpoint=checkpoint,resume=True)

    def test_corrupt_checkpoint_rejected(self):
        data=examples(3)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            train_sync(data,data,'fixture',SequentialBackend(data,'fixture'),epochs=1,batch_size=3,checkpoint=path)
            value=json.loads(path.read_text());value['adam']['first']['B2'][0]+=1
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'integrity'):ModelState.load(path)


if __name__=='__main__':unittest.main(verbosity=2)
