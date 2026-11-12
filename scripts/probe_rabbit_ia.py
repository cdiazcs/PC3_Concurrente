"""Productor/consumidor AMQP real de prueba: colas exclusivas del experimento.

Requiere Pika y RABBITMQ_* en entorno. No inicia ni reconfigura el broker.
python3 scripts/probe_rabbit_ia.py --requests 1 10 50 100 1000 --output build/phase3-load
"""
import argparse
import base64
from dataclasses import replace
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cnn_python.model import CNN, CLASSES
from cnn_python.images import read_image
from workers.python.rabbit_config import Config
from workers.python.rabbit_worker import connection_parameters,declare
from workers.python.rabbit_messages import encode,utc_now


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests',nargs='+',type=int,default=[1,10,50,100,1000])
    parser.add_argument('--inflight',type=int,default=32)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if any(not 1<=n<=10000 for n in args.requests) or not 1<=args.inflight<=256:
        parser.error('invalid_load_limits')
    output=args.output.resolve()
    if output.exists():parser.error('output_exists: preserve previous evidence')
    output.mkdir(parents=True)
    import pika
    prefix='ia-probe-'+uuid.uuid4().hex
    cfg=replace(Config.from_env(),request_queue=prefix+'-input',result_queue=prefix+'-result',
        retry_queue=prefix+'-retry',error_queue=prefix+'-error',publish_control=False,
        worker_id=prefix,metrics_file=str(output/'events.jsonl'))
    weights=Path(cfg.weights) if cfg.weights else ROOT/'model/weights/weights.txt'
    before=hashlib.sha256(weights.read_bytes()).hexdigest()
    model=CNN.load(weights)
    images=[]
    for path in sorted((ROOT/'model/examples').glob('*.png')):
        pixels=read_image(path)
        images.append((path.name,base64.b64encode(path.read_bytes()).decode(),','.join(map(str,pixels)),
                       model.predict(pixels).probabilities))
    env={**os.environ,'IA_REQUEST_QUEUE':cfg.request_queue,'IA_RESULT_QUEUE':cfg.result_queue,
         'IA_RETRY_QUEUE':cfg.retry_queue,'IA_ERROR_QUEUE':cfg.error_queue,'IA_WORKER_ID':cfg.worker_id,
         'IA_METRICS_FILE':cfg.metrics_file,'IA_PUBLISH_CONTROL':'0'}
    connection=pika.BlockingConnection(connection_parameters(cfg,pika));channel=connection.channel();declare(channel,cfg)
    log=(output/'worker.log').open('w')
    process=subprocess.Popen([sys.executable,'workers/python/rabbit_worker.py'],cwd=ROOT,env=env,
                             stdout=log,stderr=subprocess.STDOUT)
    reports=[];all_rows=[]
    try:
        end=time.monotonic()+20
        while time.monotonic()<end:
            status=channel.queue_declare(cfg.request_queue,passive=True).method
            if status.consumer_count==cfg.concurrency:break
            if process.poll() is not None:raise RuntimeError('worker_exited')
            time.sleep(.05)
        else:raise RuntimeError('worker_not_ready')
        for count in args.requests:
            sent=0;pending={};rows=[];ready_peak=0;started=time.monotonic();deadline=started+180
            while sent<count or pending:
                if time.monotonic()>deadline:raise TimeoutError('load_deadline')
                while sent<count and len(pending)<args.inflight:
                    identifier=f'{prefix}-{count}-{sent}'
                    name,b64,pixels,expected=images[sent%len(images)]
                    backend=sent%2==0
                    request={'schemaVersion':1,'idSolicitud':identifier,'idCliente':'probe-client',
                      'timestamp':utc_now(),'modeloDestino':'A','intento':1,
                      'tipo':'INFERENCIA' if backend else 'CLASIFICAR_IMAGEN',
                      'payload':{'modo':'SEQUENTIAL'} if backend else {'mimeType':'image/png','imagenBase64':b64}}
                    if backend:request['imagenBase64']=pixels
                    pending[identifier]=(time.monotonic(),name,expected)
                    channel.basic_publish(exchange='',routing_key=cfg.request_queue,body=encode(request),mandatory=True,
                        properties=pika.BasicProperties(delivery_mode=2,content_type='application/json',correlation_id=identifier))
                    sent+=1
                method,props,body=channel.basic_get(cfg.result_queue,auto_ack=False)
                if method:
                    result=json.loads(body);identifier=result['idSolicitud']
                    if identifier not in pending or props.correlation_id!=identifier:raise RuntimeError('unexpected_correlation')
                    sent_at,name,expected=pending.pop(identifier)
                    ok=result['estado']=='COMPLETADA'
                    if ok:
                        values=result['payload']['probabilidades']
                        values=[values[c] for c in CLASSES] if isinstance(values,dict) else values
                        ok=(len(values)==3 and all(math.isfinite(v) and abs(v-e)<=1e-8 for v,e in zip(values,expected))
                            and abs(sum(values)-1)<=1e-8 and result.get('versionPesos')==before)
                    rows.append({'load':count,'idSolicitud':identifier,'image':name,'ok':ok,
                                 'latencyMs':(time.monotonic()-sent_at)*1000,
                                 'inferenceMs':result.get('payload',{}).get('duracionMs')})
                    channel.basic_ack(method.delivery_tag)
                else:
                    connection.process_data_events(time_limit=.001)
                status=channel.queue_declare(cfg.request_queue,passive=True).method
                ready_peak=max(ready_peak,status.message_count)
            seconds=time.monotonic()-started
            latencies=sorted(row['latencyMs'] for row in rows)
            report={'requests':count,'success':sum(row['ok'] for row in rows),
                    'errors':sum(not row['ok'] for row in rows),'meanMs':statistics.mean(latencies),
                    'p95Ms':latencies[math.ceil(.95*len(latencies))-1],
                    'throughputRps':sum(row['ok'] for row in rows)/seconds,'totalSeconds':seconds,
                    'readyQueuePeakObserved':ready_peak,'consumerCount':status.consumer_count}
            reports.append(report);all_rows.extend(rows);print(json.dumps(report),flush=True)
        if any(r['errors'] for r in reports):raise RuntimeError('numeric_or_processing_errors')
    finally:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        log.close()
        if connection.is_open:
            for queue in (cfg.request_queue,cfg.result_queue,cfg.error_queue,cfg.retry_queue):channel.queue_delete(queue)
            connection.close()
    assert hashlib.sha256(weights.read_bytes()).hexdigest()==before
    with (output/'requests.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(all_rows[0]));writer.writeheader();writer.writerows(all_rows)
    summary={'scope':'real RabbitMQ isolated queues localhost; not backend/BD/client transaction test',
             'timestamp':utc_now(),'pika':pika.__version__,'python':sys.version.split()[0],
             'configuration':{'concurrency':cfg.concurrency,'prefetchPerConsumer':cfg.prefetch,
                 'inflight':args.inflight,'profiles':'alternating repository-v1/backend-8901cfb',
                 'brokerHost':cfg.host,'brokerPort':cfg.port,'vhost':cfg.vhost,
                 'requestQueue':cfg.request_queue,'resultQueue':cfg.result_queue},
             'weights_sha256':before,'weights_unchanged':True,'loads':reports,
             'csv_sha256':hashlib.sha256((output/'requests.csv').read_bytes()).hexdigest(),
             'unackedQueueMessages':'not measured: management API not enabled',
             'latency_scope':'publish until producer receives result; includes confirms, polling and instrumentation'}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
