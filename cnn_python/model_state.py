"""Estado global de entrenamiento y checkpoint atomico; un unico propietario."""
import hashlib
import json
import os
import threading
from functools import wraps
from pathlib import Path
from .gradient_protocol import encode,weights_hash
from .model import validate_weights
from .training_math import Adam


def synchronized(method):
    @wraps(method)
    def call(self,*args,**kwargs):
        with self._lock:return method(self,*args,**kwargs)
    return call


class ModelState:
    def __init__(self,weights,learning_rate=.003):
        self._lock=threading.RLock()
        self.weights={k:list(v) for k,v in validate_weights(weights).items()}
        self.optimizer=Adam(learning_rate);self.version=0;self.completed={}

    @synchronized
    def commit(self,step_key,version,gradients):
        digest=hashlib.sha256(encode(validate_weights(gradients))).hexdigest()
        if step_key in self.completed:
            if self.completed[step_key]!=[version,digest]:raise ValueError('conflicting_completed_step')
            return False
        if type(version) is not int or version!=self.version:raise ValueError('stale_model_version')
        updated=self.optimizer.apply(self.weights,gradients)
        self.weights=updated;self.version+=1;self.completed[step_key]=[version,digest]
        return True

    @synchronized
    def save(self,path,metadata):
        payload={'schemaVersion':1,'weights':self.weights,'weightsHash':weights_hash(self.weights),
            'modelVersion':self.version,'adam':{'step':self.optimizer.step,'first':self.optimizer.first,
                'second':self.optimizer.second,'learningRate':self.optimizer.learning_rate},
            'completed':self.completed,'metadata':metadata}
        # Checkpoints can exceed the transport message limit after long runs; JSON itself is finite.
        text=json.dumps(payload,sort_keys=True,allow_nan=False)
        payload['checkpointHash']=hashlib.sha256(text.encode()).hexdigest()
        text=json.dumps(payload,sort_keys=True,allow_nan=False)
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.tmp')
        with temporary.open('w',encoding='utf-8') as file:
            file.write(text);file.flush();os.fsync(file.fileno())
        os.replace(temporary,path)

    @classmethod
    def load(cls,path):
        value=json.loads(Path(path).read_text())
        digest=value.pop('checkpointHash',None)
        if digest!=hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest():
            raise ValueError('checkpoint_integrity')
        if value.get('schemaVersion')!=1:raise ValueError('checkpoint_schema')
        optimizer=value['adam'];state=cls(value['weights'],optimizer['learningRate'])
        version=value['modelVersion']
        if type(version) is not int or version<0 or optimizer['step']!=version:
            raise ValueError('checkpoint_version')
        if value['weightsHash']!=weights_hash(state.weights):raise ValueError('checkpoint_weights_hash')
        state.optimizer.first={k:list(v) for k,v in validate_weights(optimizer['first']).items()}
        state.optimizer.second={k:list(v) for k,v in validate_weights(optimizer['second']).items()}
        if any(v<0 for values in state.optimizer.second.values() for v in values):raise ValueError('checkpoint_variance')
        state.optimizer.step=state.version=version;state.completed=value['completed']
        if len(state.completed)!=version:raise ValueError('checkpoint_completed_steps')
        versions=sorted(item[0] for item in state.completed.values())
        if versions!=list(range(version)):raise ValueError('checkpoint_step_order')
        return state,value['metadata']


class CoordinatorLease:
    """Portable exclusive directory; stale leases require deliberate operator recovery."""
    def __init__(self,output):
        self.path=Path(output)/'coordinator.lock'
        try:self.path.mkdir()
        except FileExistsError:raise ValueError('coordinator_lease_exists_verify_owner_before_removal') from None
        import socket
        self.owner={'pid':os.getpid(),'hostname':socket.gethostname()}
        (self.path/'owner.json').write_text(json.dumps(self.owner))

    def close(self):
        if json.loads((self.path/'owner.json').read_text())!=self.owner:
            raise ValueError('coordinator_lease_owner_changed')
        (self.path/'owner.json').unlink();self.path.rmdir()
