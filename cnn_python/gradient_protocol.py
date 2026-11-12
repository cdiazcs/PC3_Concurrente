"""Propuesta privada entrenamiento v1; no cambia contratos de inferencia."""
import hashlib
import json
import math
import os
import platform
import socket
import time
from .model import validate_weights
from .training_math import compute_gradients

MAX_BYTES=2_000_000
FIELDS=('runId','epoch','batchId','taskId','modelVersion','weightsHash','datasetHash')


def encode(value):
    body=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(body)>MAX_BYTES:raise ValueError('training_message_size')
    return body


def weights_hash(weights):
    return hashlib.sha256(encode(validate_weights(weights))).hexdigest()


def decode(body):
    if not isinstance(body,bytes) or len(body)>MAX_BYTES:raise ValueError('training_message_size')
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise ValueError('duplicate_training_key')
            out[key]=value
        return out
    def constant(_):raise ValueError('nonfinite_training_json')
    def number(raw):
        value=float(raw)
        if not math.isfinite(value):raise ValueError('nonfinite_training_json')
        return value
    value=json.loads(body,object_pairs_hook=pairs,parse_constant=constant,parse_float=number)
    if not isinstance(value,dict):raise ValueError('training_object_required')
    return value


def error_result(task,code,correlation_id=None):
    result={}
    for key in FIELDS:
        value=task.get(key)
        if key in ('epoch','batchId','modelVersion'):
            result[key]=value if type(value) is int and value>=0 else None
        else:result[key]=value if isinstance(value,str) and len(value)<=128 else None
    if isinstance(correlation_id,str) and 0<len(correlation_id)<=128:result['taskId']=correlation_id
    return {**result,'schemaVersion':1,'tipo':'TRAIN_ERROR','code':code}


def validate_task(task,dataset_hash,total):
    if type(task.get('schemaVersion')) is not int or task['schemaVersion']!=1 or task.get('tipo')!='TRAIN_TASK':raise ValueError('training_schema')
    for key in ('runId','taskId'):
        if not isinstance(task.get(key),str) or not 0<len(task[key])<=128 or any(c.isspace() for c in task[key]):
            raise ValueError('training_identifier')
    for key,minimum in (('epoch',1),('batchId',0),('modelVersion',0)):
        if type(task.get(key)) is not int or task[key]<minimum:raise ValueError('training_version_or_step')
    if task.get('datasetHash')!=dataset_hash:raise ValueError('training_dataset_mismatch')
    indices=task.get('indices')
    if (not isinstance(indices,list) or not 0<len(indices)<=256
        or any(type(i) is not int or not 0<=i<total for i in indices) or len(set(indices))!=len(indices)):
        raise ValueError('training_indices')
    if type(task.get('count')) is not int or task['count']!=len(indices):raise ValueError('training_count')
    weights=validate_weights(task['weights'])
    if task.get('weightsHash')!=weights_hash(weights):raise ValueError('training_weights_hash')
    return weights


def make_tasks(run,epoch,batch,version,weights,indices,dataset_hash,partitions):
    if type(partitions) is not int or not 1<=partitions<=16:raise ValueError('training_partitions')
    if not indices or len(indices)>256 or len(set(indices))!=len(indices):raise ValueError('training_batch_indices')
    tasks=[];offset=0;n=min(partitions,len(indices));size,remainder=divmod(len(indices),n)
    weights=validate_weights(weights);digest=weights_hash(weights)
    for i in range(n):
        count=size+(i<remainder);part=list(indices[offset:offset+count]);offset+=count
        tasks.append({'schemaVersion':1,'tipo':'TRAIN_TASK','runId':run,'epoch':epoch,'batchId':batch,
            'taskId':f'{run}:{version}:{i}','modelVersion':version,'weightsHash':digest,
            'datasetHash':dataset_hash,'weights':weights,'indices':part,'count':len(part)})
    return tasks


def execute_task(task,examples,dataset_hash):
    started=time.monotonic();cpu_started=time.process_time();weights=validate_task(task,dataset_hash,len(examples))
    loss,gradient=compute_gradients(weights,[examples[i] for i in task['indices']])
    return {**{key:task[key] for key in FIELDS},'schemaVersion':1,'tipo':'TRAIN_GRADIENT_RESULT',
        'count':task['count'],'meanLoss':loss,'gradients':gradient,'workerId':f'{socket.gethostname()}:{os.getpid()}',
        'pid':os.getpid(),'hostname':socket.gethostname(),'os':platform.platform(),
        'computeSeconds':time.monotonic()-started,'computeCpuSeconds':time.process_time()-cpu_started}


def aggregate_gradients(tasks,results):
    if not tasks:raise ValueError('empty_training_step')
    expected={task['taskId']:task for task in tasks}
    if len(expected)!=len(tasks):raise ValueError('duplicate_assigned_partition')
    reference=tasks[0]
    shared=tuple(key for key in FIELDS if key!='taskId')
    seen_indices=set()
    for task in tasks:
        if any(task[key]!=reference[key] for key in shared):raise ValueError('mixed_assigned_versions')
        if seen_indices.intersection(task['indices']):raise ValueError('overlapping_partitions')
        seen_indices.update(task['indices'])
    accepted={}
    for result in results:
        identifier=result.get('taskId');task=expected.get(identifier)
        if task is None:raise ValueError('unassigned_gradient')
        if (type(result.get('schemaVersion')) is not int or result['schemaVersion']!=1
            or result.get('tipo')!='TRAIN_GRADIENT_RESULT' or any(result.get(k)!=task[k] for k in FIELDS)):
            raise ValueError('stale_or_mixed_gradient')
        if type(result.get('count')) is not int or result['count']!=task['count']:raise ValueError('gradient_count')
        try:
            gradients=validate_weights(result['gradients']);loss=float(result['meanLoss'])
        except (KeyError,TypeError,ValueError,OverflowError):raise ValueError('invalid_gradient_values') from None
        if not math.isfinite(loss) or loss<0:raise ValueError('gradient_loss')
        compute=result.get('computeSeconds')
        if not isinstance(compute,(int,float)) or not math.isfinite(compute) or compute<0:
            raise ValueError('invalid_gradient_timing')
        signature=hashlib.sha256(encode([result['count'],loss,gradients])).hexdigest()
        if identifier in accepted:
            if accepted[identifier][0]!=signature:raise ValueError('conflicting_duplicate_gradient')
            continue
        accepted[identifier]=(signature,result['count'],loss,gradients)
    if set(accepted)!=set(expected):raise ValueError('incomplete_training_step')
    ordered=[accepted[task['taskId']] for task in tasks];total=sum(r[1] for r in ordered)
    gradients={key:[math.fsum(r[1]*r[3][key][i] for r in ordered)/total for i in range(len(ordered[0][3][key]))]
               for key in ordered[0][3]}
    return math.fsum(r[1]*r[2] for r in ordered)/total,validate_weights(gradients)
