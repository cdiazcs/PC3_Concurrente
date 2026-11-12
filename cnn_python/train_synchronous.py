"""Coordinador sincrono compartido: secuencial, procesos locales o RabbitMQ."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import time
import uuid

from .dataset import DEFAULT_DATASET,load_split
from .evaluate import evaluate
from .gradient_protocol import aggregate_gradients,make_tasks
from .model import CNN,DEFAULT_WEIGHTS,save_weights
from .model_state import ModelState,CoordinatorLease
from .train import initial_weights,metrics
from .training_backends import SequentialBackend,ParallelBackend


def train_sync(examples,validation,dataset_hash,backend,*,epochs=3,batch_size=24,seed=20261022,
               learning_rate=.003,indices=None,checkpoint=None,resume=False,max_steps=None,run_id=None):
    if not examples or not validation or type(epochs) is not int or not 1<=epochs<=10000:
        raise ValueError('training_configuration')
    if type(batch_size) is not int or not 1<=batch_size<=256:raise ValueError('training_batch_size')
    if max_steps is not None and (type(max_steps) is not int or max_steps<1):raise ValueError('training_max_steps')
    indices=list(range(len(examples))) if indices is None else list(indices)
    if not indices or len(set(indices))!=len(indices) or any(type(i) is not int or not 0<=i<len(examples) for i in indices):
        raise ValueError('training_selected_indices')
    # Snapshot scheduling is independent of transport/backend, allowing checkpoint resume across modes.
    config={'epochs':epochs,'batchSize':batch_size,'seed':seed,'learningRate':learning_rate,
            'datasetHash':dataset_hash,'indices':indices,
            'validationHash':hashlib.sha256(json.dumps(validation,separators=(',',':')).encode()).hexdigest()}
    if resume:
        if not checkpoint:raise ValueError('resume_requires_checkpoint')
        state,meta=ModelState.load(checkpoint)
        if meta['configuration']!=config:raise ValueError('checkpoint_configuration_mismatch')
    else:
        state=ModelState(initial_weights(seed),learning_rate)
        meta={'runId':run_id or uuid.uuid4().hex,'configuration':config,'history':[],
              'bestLoss':None,'bestEpoch':0,'bestWeights':None,'epochLossSum':0.0}
    started=time.monotonic();rng=random.Random(seed+1);steps=[];worker_records={};paused=False
    if checkpoint and not resume:state.save(checkpoint,meta)
    for epoch in range(1,epochs+1):
        order=indices[:];rng.shuffle(order)
        if epoch<=len(meta['history']):continue
        epoch_started=time.monotonic()
        for batch_id,offset in enumerate(range(0,len(order),batch_size)):
            key=f'{epoch}:{batch_id}'
            if key in state.completed:continue
            batch=order[offset:offset+batch_size];version=state.version
            tasks=make_tasks(meta['runId'],epoch,batch_id,version,state.weights,batch,dataset_hash,backend.partitions)
            step_started=time.monotonic();results=backend.map(tasks);mapped=time.monotonic()
            loss,gradient=aggregate_gradients(tasks,results);aggregated=time.monotonic()
            state.commit(key,version,gradient);updated=time.monotonic()
            meta['epochLossSum']+=loss*len(batch)
            if checkpoint:state.save(checkpoint,meta)
            for result in results:
                worker_records[result['workerId']]={k:result.get(k) for k in ('workerId','pid','hostname','os')}
                worker_records[result['workerId']]['role']='local-gradient-pool-owner' if result.get('localWorkers') else 'gradient-compute'
                for extra in result.get('localWorkers',[]):worker_records[extra['workerId']]={**extra,'role':'gradient-compute'}
            steps.append({'epoch':epoch,'batchId':batch_id,'modelVersionBefore':version,'modelVersionAfter':state.version,
                          'samples':len(batch),'tasks':len(tasks),'meanLoss':loss,
                          'mapSeconds':mapped-step_started,'gradientComputeSecondsSum':sum(r['computeSeconds'] for r in results),
                          'gradientComputeCpuSecondsSum':sum(r.get('computeCpuSeconds',0.0) for r in results),
                          'aggregateSeconds':aggregated-mapped,'updateSeconds':updated-aggregated,
                          'stepSeconds':updated-step_started})
            if max_steps is not None and len(steps)>=max_steps:
                paused=True;break
        if paused:break
        validation_metrics=metrics(CNN(state.weights),validation)
        row={'epoch':epoch,'trainCrossEntropy':meta['epochLossSum']/len(order),
             'validationCrossEntropy':validation_metrics['cross_entropy'],
             'validationAccuracy':validation_metrics['accuracy'],'epochSeconds':time.monotonic()-epoch_started}
        meta['history'].append(row);meta['epochLossSum']=0.0
        if meta['bestLoss'] is None or row['validationCrossEntropy']<meta['bestLoss']:
            meta['bestLoss']=row['validationCrossEntropy'];meta['bestEpoch']=epoch
            meta['bestWeights']={k:v[:] for k,v in state.weights.items()}
        if checkpoint:state.save(checkpoint,meta)
    selected=meta['bestWeights'] if meta['bestWeights'] is not None else state.weights
    report={'runId':meta['runId'],'configuration':config,'complete':not paused,'modelVersion':state.version,
            'adamSteps':state.optimizer.step,'bestEpoch':meta['bestEpoch'],'history':meta['history'],
            'stepsThisInvocation':steps,'secondsThisInvocation':time.monotonic()-started,
            'workersObserved':list(worker_records.values()),'physicalDistributedNodesVerified':False,
            'backendStats':dict(backend.stats),
            'finalTraining':metrics(CNN(selected),[examples[i] for i in indices]),
            'finalValidation':metrics(CNN(selected),validation)}
    return selected,report,state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['sequential','parallel','amqp'],default='sequential')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    parser.add_argument('--epochs',type=int,default=3);parser.add_argument('--batch-size',type=int,default=24)
    parser.add_argument('--seed',type=int,default=20261022);parser.add_argument('--learning-rate',type=float,default=.003)
    parser.add_argument('--processes',type=int,default=2);parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--samples-per-class',type=int,default=0)
    parser.add_argument('--resume',action='store_true');parser.add_argument('--max-steps',type=int)
    args=parser.parse_args();out=args.output.resolve()
    if out.is_relative_to(DEFAULT_WEIGHTS.parent.parent):
        parser.error('output_must_not_target_official_model')
    if out.exists() and not args.resume:parser.error('output_exists')
    if args.resume and not (out/'checkpoint.json').is_file():parser.error('checkpoint_missing')
    out.mkdir(parents=True,exist_ok=True)
    lease=CoordinatorLease(out)
    try:
        examples=load_split(args.dataset,'train');validation=load_split(args.dataset,'validation')
        digest=hashlib.sha256(args.dataset.read_bytes()).hexdigest()
        if args.samples_per_class<0:parser.error('invalid_sample_count')
        indices=None
        if args.samples_per_class:
            indices=[]
            for label in range(3):
                group=[i for i,(_,y) in enumerate(examples) if y==label]
                if args.samples_per_class>len(group):parser.error('samples_exceed_dataset')
                indices.extend(group[:args.samples_per_class])
        if args.mode=='sequential':backend=SequentialBackend(examples,digest)
        elif args.mode=='parallel':backend=ParallelBackend(examples,digest,args.processes,args.timeout)
        else:
            from .training_amqp import AMQPBackend
            backend=AMQPBackend(partitions=args.processes,timeout=args.timeout)
        try:
            selected,report,state=train_sync(examples,validation,digest,backend,epochs=args.epochs,batch_size=args.batch_size,
                seed=args.seed,learning_rate=args.learning_rate,indices=indices,checkpoint=out/'checkpoint.json',
                resume=args.resume,max_steps=args.max_steps)
            report['mode']=args.mode
            if report['complete']:
                report['test'],_=evaluate(CNN(selected),load_split(args.dataset,'test'))
            save_weights(selected,out/'weights.txt')
            report['selectedWeightsSha256']=hashlib.sha256((out/'weights.txt').read_bytes()).hexdigest()
            report['sourceSha256']={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in Path(__file__).parent.glob('*.py')}
            (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
            print(json.dumps({k:report[k] for k in ('mode','complete','modelVersion','secondsThisInvocation','finalTraining','finalValidation')}),flush=True)
        finally:backend.close()
    finally:lease.close()


if __name__=='__main__':main()
