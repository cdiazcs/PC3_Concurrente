"""REAL SQL + broker. Only isolated pc3_test_* DBs; never opt in on shared data."""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
import uuid
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from build import classpath
from rabbit_java_integration import exchange,free_port

@unittest.skipUnless(os.environ.get('PC3_PHASE2_INTEGRATION')=='1','NO VERIFICADO: requiere dos SQL de prueba y RabbitMQ reales')
class Phase2IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pika
        import mysql.connector
        from workers.python.rabbit_config import Config
        from workers.python.rabbit_worker import connection_parameters
        if any(not os.environ.get(name,'').startswith('pc3_test_') for name in ('POSTGRES_DB','MARIADB_DATABASE')):
            raise RuntimeError('isolated_database_required')
        cls.processes=[];cls.logs=[];cls.addClassCleanup(cls.cleanup)
        cls.folder=ROOT/'build'/('phase2-'+uuid.uuid4().hex);cls.folder.mkdir()
        cls.environment={**os.environ,'SYSTEM_PIPELINE':'FULL','INFERENCE_TRANSPORT':'RABBITMQ',
            'POSTGRES_ENABLED':'false','BACKEND_BIND_HOST':'127.0.0.1','BACKEND_CLIENT_TIMEOUT_MS':'80000',
            'CLIENT_TIMEOUT_MS':'80000','VALIDATION_TIMEOUT_MS':'3000','PERSISTENCE_TIMEOUT_MS':'3000',
            'RABBITMQ_REQUEST_TIMEOUT_MS':'5000','IA_WORKER_CONCURRENCY':'4','CLIENT_PROTOCOL':'V2'}
        token='phase2-'+uuid.uuid4().hex
        for key,suffix in {'IA_REQUEST_QUEUE':'-ia','IA_RESULT_QUEUE':'-ia-result','IA_RETRY_QUEUE':'-ia-retry',
            'IA_ERROR_QUEUE':'-ia-error','QUEUE_VALIDATION':'-validation','QUEUE_VALIDATION_RESULTS':'-validation-result',
            'QUEUE_PERSISTENCE':'-pg','QUEUE_PERSISTENCE_RESULTS':'-pg-result'}.items():cls.environment[key]=token+suffix
        cls.queues=[cls.environment[key] for key in ('IA_REQUEST_QUEUE','IA_RESULT_QUEUE','IA_RETRY_QUEUE','IA_ERROR_QUEUE',
            'QUEUE_VALIDATION','QUEUE_VALIDATION_RESULTS','QUEUE_PERSISTENCE','QUEUE_PERSISTENCE_RESULTS')]
        cls.queues += [cls.environment['QUEUE_VALIDATION']+suffix for suffix in ('.retry','.errores')]
        cls.queues += [cls.environment['QUEUE_PERSISTENCE']+'.errores']
        cfg=Config.from_env();cls.pika=pika
        cls.connection=pika.BlockingConnection(connection_parameters(cfg,pika));cls.channel=cls.connection.channel()
        for source in ('01_schema.sql','02_phase2.sql'):cls.sql((ROOT/'databases/postgresql'/source).read_text())
        cls.maria=mysql.connector.connect(host=os.environ['MARIADB_HOST'],port=int(os.environ['MARIADB_PORT']),
            user=os.environ['MARIADB_USER'],password=os.environ['MARIADB_PASSWORD'],database=os.environ['MARIADB_DATABASE'],autocommit=True)
        for source in ('01_schema.sql','03_phase2.sql','02_seed_clientes.sql'):
            for statement in '\n'.join(line for line in (ROOT/'databases/mariadb'/source).read_text().splitlines() if not line.lstrip().startswith('--')).split(';'):
                if statement.strip():
                    with cls.maria.cursor() as cursor:cursor.execute(statement)
        cls.port=free_port();cls.gateway_port=free_port()
        cls.start('validator',[sys.executable,'databases/mariadb/validator_worker.py'])
        cls.start('ia',[sys.executable,'workers/python/rabbit_worker.py'])
        cls.start('persistence',['java','-cp',classpath(ROOT/'build'),'db.PersistenceWorker'])
        cls.start('backend',['java','-Dopenaicubes.maxClients=256','-cp',classpath(ROOT/'build'),
            'CentralServer',str(cls.port),'127.0.0.1:'+str(free_port())])
        cls.start('gateway',[sys.executable,'web-server/http_gateway.py','--host','127.0.0.1','--port',str(cls.gateway_port),
            '--backend-host','127.0.0.1','--backend-port',str(cls.port)])
        for port in (cls.port,cls.gateway_port):
            end=time.monotonic()+15
            while time.monotonic()<end:
                try:
                    with socket.create_connection(('127.0.0.1',port),.1):break
                except OSError:time.sleep(.05)
            else:raise RuntimeError('service_startup_failed: '+str(cls.folder))
        cls.wait_consumers()
        cls.raw=(ROOT/'model/examples/circulo-0.png').read_bytes();cls.image=base64.b64encode(cls.raw).decode()
        android=ROOT/'clients/android/protocol/src'
        subprocess.run(['javac','--release','17','-cp',classpath(ROOT/'build'),'-d',str(ROOT/'build'),
            str(android/'main/java/uni/openaicubes/Protocol.java'),'tests/Phase2Clients.java','tests/PostgresTransactionChecks.java'],cwd=ROOT,check=True)

    @classmethod
    def sql(cls,text):
        env={**os.environ,'PGHOST':os.environ['POSTGRES_HOST'],'PGPORT':os.environ['POSTGRES_PORT'],
            'PGUSER':os.environ['POSTGRES_USER'],'PGPASSWORD':os.environ['POSTGRES_PASSWORD'],'PGDATABASE':os.environ['POSTGRES_DB']}
        return subprocess.check_output([os.environ.get('PSQL','psql'),'-X','-A','-t','-v','ON_ERROR_STOP=1','-c',text],
            env=env,text=True,stderr=subprocess.PIPE).strip()

    @classmethod
    def start(cls,name,command):
        log=(cls.folder/(name+'-'+uuid.uuid4().hex+'.txt')).open('w');cls.logs.append(log)
        process=subprocess.Popen(command,cwd=ROOT,env=cls.environment,stdout=log,stderr=subprocess.STDOUT)
        cls.processes.append(process);setattr(cls,name.replace('-','_'),process)
        return process

    @classmethod
    def wait_consumers(cls):
        for key in ('IA_REQUEST_QUEUE','QUEUE_VALIDATION','QUEUE_PERSISTENCE'):
            end=time.monotonic()+15
            while time.monotonic()<end:
                probe=cls.connection.channel()
                try:
                    if probe.queue_declare(cls.environment[key],passive=True).method.consumer_count:
                        probe.close();break
                except cls.pika.exceptions.ChannelClosedByBroker:pass
                finally:
                    if probe.is_open:probe.close()
                cls.connection.process_data_events(time_limit=.05)
            else:raise RuntimeError('consumer_not_ready '+key+' logs '+str(cls.folder))

    @classmethod
    def cleanup(cls):
        for process in reversed(getattr(cls,'processes',[])):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=8)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        if hasattr(cls,'connection') and cls.connection.is_open:
            for queue in cls.queues:cls.channel.queue_delete(queue)
            cls.connection.close()
        if hasattr(cls,'maria'):cls.maria.close()
        for log in cls.logs:log.close()

    def classify(self,id,client='cliente-demo-01',image=None):
        return exchange(self.port,f'IDENTIFY2|{id}|{client}|SEQUENTIAL|image/png|{image or self.image}')

    def test_a_active_blocked_unknown_and_invalid_image(self):
        self.assertTrue(self.classify('active-1').startswith('RESULT|active-1|1|3|'))
        for client in ('cliente-bloqueado-01','no-such-client','bench-unknown'):
            id='reject-'+client
            self.assertEqual(self.classify(id,client),'ERROR|'+id+'|client_rejected')
            self.assertEqual(self.sql("SELECT count(*) FROM solicitudes WHERE id_solicitud='"+id+"'"),'0')
        self.assertEqual(self.classify('bad-image',image='AQID'),'ERROR|bad-image|invalid_image')
        self.assertEqual(exchange(self.port,'IDENTIFY|legacy|'+','.join(['0']*256)), 'ERROR|legacy|client_identity_required')
        with self.maria.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM clientes WHERE id_cliente IN ('no-such-client','bench-unknown')")
            self.assertEqual(cursor.fetchone()[0],0)

    def test_b_duplicate_and_concurrent_races(self):
        first=self.classify('duplicate-1');self.assertTrue(first.startswith('RESULT|'))
        with ThreadPoolExecutor(max_workers=10) as pool:
            replies=list(pool.map(lambda _:self.classify('duplicate-1'),range(10)))
        self.assertTrue(all(reply.startswith('RESULT|duplicate-1|') for reply in replies),replies)
        self.assertEqual(self.sql("SELECT count(*) FROM clasificaciones WHERE id_solicitud='duplicate-1'"),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM historial_consultas WHERE id_solicitud='duplicate-1'"),'1')
        self.assertEqual(self.classify('duplicate-1','cliente-web-01'),'ERROR|duplicate-1|validation_failed')

    def test_c_real_mariadb_races_and_immutable_verdict(self):
        spec=importlib.util.spec_from_file_location('phase2_validator',ROOT/'databases/mariadb/validator_worker.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);pool=module.create_db_pool()
        with ThreadPoolExecutor(max_workers=8) as executor:
            values=list(executor.map(lambda _:module.validar_solicitud_idempotente(pool,'race-maria','cliente-demo-01'),range(40)))
        self.assertEqual(len(set(values)),1);self.assertTrue(values[0][0])
        with self.maria.cursor() as cursor:cursor.execute("UPDATE clientes SET estado='BLOQUEADO' WHERE id_cliente='cliente-demo-01'")
        try:self.assertEqual(module.validar_solicitud_idempotente(pool,'race-maria','cliente-demo-01'),values[0])
        finally:
            with self.maria.cursor() as cursor:cursor.execute("UPDATE clientes SET estado='ACTIVO' WHERE id_cliente='cliente-demo-01'")
        with self.assertRaises(ValueError):module.validar_solicitud_idempotente(pool,'race-maria','cliente-web-01')

    def test_d_postgres_atomic_rollback(self):
        self.sql("""CREATE OR REPLACE FUNCTION phase2_abort() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.id_solicitud LIKE 'rollback-%' THEN RAISE EXCEPTION 'forced test rollback'; END IF; RETURN NEW; END $$;
            CREATE TRIGGER phase2_rollback BEFORE UPDATE ON solicitudes FOR EACH ROW EXECUTE FUNCTION phase2_abort();""")
        try:
            self.assertEqual(self.classify('rollback-1'),'ERROR|rollback-1|persistence_failed')
            for table in ('solicitudes','clasificaciones','historial_consultas','outbox_persistencia'):
                self.assertEqual(self.sql("SELECT count(*) FROM "+table+" WHERE id_solicitud='rollback-1'"),'0')
        finally:self.sql('DROP TRIGGER phase2_rollback ON solicitudes; DROP FUNCTION phase2_abort()')

    def test_e_ten_fifty_hundred_concurrent(self):
        for count in (10,50,100):
            ids=['concurrent-'+str(count)+'-'+str(i) for i in range(count)]
            with ThreadPoolExecutor(max_workers=count) as executor:replies=list(executor.map(self.classify,ids))
            for id,reply in zip(ids,replies):self.assertTrue(reply.startswith('RESULT|'+id+'|1|3|'),reply)
            self.assertEqual(self.sql("SELECT count(*) FROM clasificaciones WHERE id_solicitud LIKE 'concurrent-"+str(count)+"-%'"),str(count))
            print(f'REAL: {count}/{count} solicitudes concurrentes BD2 -> CNN -> BD1, IDs y COMMIT confirmados',flush=True)

    def test_f_desktop_android_shared_contract_and_web(self):
        for kind in ('desktop','android','desktop-ui'):
            id='client-'+kind
            result=subprocess.run(['java','-Djava.awt.headless=true','-cp',classpath(ROOT/'build'),'Phase2Clients',kind,
                '127.0.0.1',str(self.port),id,'cliente-desktop-01' if kind.startswith('desktop') else 'cliente-android-01',str(ROOT/'model/examples/circulo-0.png')],
                env=self.environment,cwd=ROOT,text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            if kind=='desktop-ui':
                actual=result.stdout.strip().split()[0]
                self.assertEqual(self.sql("SELECT count(*) FROM clasificaciones WHERE id_solicitud='"+actual+"'"),'1')
            else:self.assertIn(id,result.stdout)
        from cnn_python.images import read_image
        body={'idSolicitud':'client-web','idCliente':'cliente-web-01','modeloDestino':'A','modo':'SEQUENTIAL',
              'payload':{'imagenBase64':self.image,'pixels':read_image(ROOT/'model/examples/circulo-0.png')}}
        request=urllib.request.Request('http://127.0.0.1:'+str(self.gateway_port)+'/api/classify',
            data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=20) as response:
            value=json.load(response);self.assertEqual(value['idSolicitud'],'client-web')
        self.assertEqual(self.sql("SELECT count(*) FROM clasificaciones WHERE id_solicitud IN ('client-desktop','client-android','client-web')"),'3')

        # Actual HTTP error paths, same full backend and SQL services.
        for client in ('cliente-bloqueado-01','not-registered-web'):
            body['idSolicitud']='web-reject-'+client;body['idCliente']=client
            request=urllib.request.Request('http://127.0.0.1:'+str(self.gateway_port)+'/api/classify',
                data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as failure:urllib.request.urlopen(request,timeout=20)
            self.assertEqual(failure.exception.code,422)
            failure.exception.close()
        row=json.loads(self.sql("SELECT json_build_object('idSolicitud',s.id_solicitud,'idCliente',s.id_cliente,'estado',s.estado,'etiqueta',c.etiqueta,'probabilidades',c.probabilidades,'sha256',s.sha256_imagen,'historial',(SELECT count(*) FROM historial_consultas h WHERE h.id_solicitud=s.id_solicitud),'outbox',(SELECT count(*) FROM outbox_persistencia o WHERE o.id_solicitud=s.id_solicitud)) FROM solicitudes s JOIN clasificaciones c USING(id_solicitud) WHERE s.id_solicitud='client-web'"))
        with self.maria.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT id_solicitud,id_cliente,aprobado,motivo FROM validaciones WHERE id_solicitud='client-web'")
            row['validacionMariaDB']=cursor.fetchone()
        (self.folder/'solicitud-completa.json').write_text(json.dumps(row,indent=2))

    def test_g_outbox_commit_before_publish_recovery(self):
        from cnn_python.model import CNN
        from cnn_python.images import read_image
        import hashlib
        p=CNN.load().predict(read_image(ROOT/'model/examples/circulo-0.png')).probabilities
        message={'schemaVersion':1,'tipo':'GUARDAR_RESULTADO','idSolicitud':'outbox-recovery','idCliente':'cliente-demo-01',
            'modeloDestino':'A','timestamp':'2026-11-12T00:00:00Z','payload':{'etiqueta':'circulo','probabilidad':p[0],
            'probabilidades':list(p),'duracionMs':1.0,'imagen':{'nombre':'recovery','mimeType':'image/png','sha256':hashlib.sha256(self.raw).hexdigest()}}}
        source=self.folder/'commit.json';source.write_text(json.dumps(message))
        subprocess.run(['java','-cp',classpath(ROOT/'build'),'PostgresTransactionChecks',str(source)],
            cwd=ROOT,env=self.environment,check=True,stdout=subprocess.DEVNULL)
        # Commit exists with no AMQP publication. Stop only our backend so we can inspect replay.
        self.backend.terminate();self.backend.wait(timeout=10)
        message['payload']['duracionMs']=2.0
        message['payload']=dict(reversed(list(message['payload'].items())))
        try:
            self.channel.basic_publish('',self.environment['QUEUE_PERSISTENCE'],json.dumps(message).encode(),
                properties=self.pika.BasicProperties(correlation_id='outbox-recovery',delivery_mode=2))
            end=time.monotonic()+5
            while time.monotonic()<end:
                method,props,body=self.channel.basic_get(self.environment['QUEUE_PERSISTENCE_RESULTS'],auto_ack=False)
                if method:
                    result=json.loads(body);self.channel.basic_ack(method.delivery_tag)
                    self.assertEqual(result['estado'],'PERSISTIDA')
                    self.assertEqual(props.correlation_id,'outbox-recovery')
                    break
                time.sleep(.05)
            else:self.fail('outbox_replay_not_published')
            self.assertEqual(self.sql("SELECT count(*) FROM outbox_persistencia WHERE id_solicitud='outbox-recovery'"),'1')
            self.assertEqual(self.sql("SELECT count(*) FROM historial_consultas WHERE id_solicitud='outbox-recovery'"),'1')
            cases=[]
            changed=json.loads(json.dumps(message));changed['payload']['imagen']['sha256']='a'*64
            cases.append((self.environment['QUEUE_PERSISTENCE'],self.environment['QUEUE_PERSISTENCE_RESULTS'],changed,'idempotency_conflict'))
            invalid={'schemaVersion':2,'tipo':'VALIDAR_CLIENTE','idSolicitud':'invalid-amqp','idCliente':'cliente-demo-01',
                'modeloDestino':'A','timestamp':'2026-11-12T00:00:00Z','payload':{}}
            cases.append((self.environment['QUEUE_VALIDATION'],self.environment['QUEUE_VALIDATION_RESULTS'],invalid,'invalid_database_message'))
            malformed={'schemaVersion':1,'tipo':'GUARDAR_RESULTADO','idSolicitud':'null-client','idCliente':None,
                'modeloDestino':'A','timestamp':'2026-11-12T00:00:00Z','payload':{}}
            cases.append((self.environment['QUEUE_PERSISTENCE'],self.environment['QUEUE_PERSISTENCE_RESULTS'],malformed,'invalid_persistence_message'))
            for queue,result_queue,value,error in cases:
                self.channel.basic_publish('',queue,json.dumps(value).encode(),properties=self.pika.BasicProperties(
                    correlation_id=value['idSolicitud'],delivery_mode=2))
                end=time.monotonic()+5
                while time.monotonic()<end:
                    method,props,body=self.channel.basic_get(result_queue,auto_ack=False)
                    if method:
                        result=json.loads(body);self.channel.basic_ack(method.delivery_tag)
                        self.assertEqual(result['estado'],'ERROR');self.assertEqual(result['error'],error)
                        break
                    time.sleep(.05)
                else:self.fail('database_error_response_missing')
        finally:
            self.start('backend',['java','-Dopenaicubes.maxClients=256','-cp',classpath(ROOT/'build'),
                'CentralServer',str(self.port),'127.0.0.1:'+str(free_port())])
            end=time.monotonic()+10
            while time.monotonic()<end:
                try:
                    with socket.create_connection(('127.0.0.1',self.port),.1):break
                except OSError:time.sleep(.05)

    def test_h_disconnected_validation_inference_and_persistence(self):
        for name,expected in [('validator','validation_timeout'),('ia','inference_timeout'),('persistence','persistence_pending')]:
            process=getattr(self,name);process.terminate();process.wait(timeout=10)
            id='offline-'+name
            self.assertEqual(self.classify(id),'ERROR|'+id+'|'+expected)
            command={'validator':[sys.executable,'databases/mariadb/validator_worker.py'],
                'ia':[sys.executable,'workers/python/rabbit_worker.py'],
                'persistence':['java','-cp',classpath(ROOT/'build'),'db.PersistenceWorker']}[name]
            self.start(name,command);self.wait_consumers()
