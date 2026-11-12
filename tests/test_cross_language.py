"""Actual Gson serialization -> Python validation/CNN -> Gson deserialization."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from build import compile_java, classpath
from workers.python.rabbit_config import Config
from workers.python.rabbit_messages import parse,validate
from workers.python.ia_service import IAService

@unittest.skipUnless(shutil.which('java') and shutil.which('javac'),'NO VERIFICADO: JDK requerido')
class CrossLanguageTests(unittest.TestCase):
    def test_java_request_python_cnn_java_response(self):
        with tempfile.TemporaryDirectory() as directory:
            compile_java(directory)
            cp=classpath(directory)
            subprocess.run(['javac','--release','17','-cp',cp,'-d',directory,str(ROOT/'tests/ContractChecks.java')],check=True)
            request=subprocess.check_output(['java','-cp',cp,'ContractChecks'])
            cfg=Config(user='unit',password='unit-only')
            data=parse(request,cfg)
            self.assertNotIn('imagenBase64',data)
            self.assertEqual(data['payload']['imagen']['formato'],'VECTOR_NORMALIZADO')
            result,_=IAService(cfg).process(validate(data,cfg,data['idSolicitud']))
            subprocess.run(['java','-cp',cp,'ContractChecks',json.dumps(result)],check=True)
