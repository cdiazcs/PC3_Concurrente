"""Unit tests independent of other nodes and network services."""
from pathlib import Path
import sys
import unittest
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
MODULES=('test_phase2_contracts','test_cnn.MathTests','test_cnn.ImageTests','test_cnn.DatasetTests','test_cnn.AcceptanceTests','test_cross_language','test_cnn_phase1','test_rabbit_messages','test_rabbit_worker','test_gradient_aggregation',
         'test_parallel_training','test_training_recovery')
if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--member', choices=('all','1','2','3'), default='all')
    args = parser.parse_args()
    modules = MODULES
    if args.member in ('1', '3'):
        modules = ('test_cross_language','test_phase2_contracts')
    elif args.member == '2':
        modules = tuple(name for name in MODULES if name not in ('test_cross_language','test_cnn_phase1','test_phase2_contracts')) + ('test_cnn_phase1.NumericalTests','test_phase2_contracts.DatabaseTransportTests')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(modules))
    sys.exit(not result.wasSuccessful())
