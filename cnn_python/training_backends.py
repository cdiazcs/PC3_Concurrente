"""Ejecucion local secuencial y pool persistente de procesos (spawn)."""
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
import multiprocessing
import math
import os
import time
from .gradient_protocol import execute_task

_EXAMPLES=None
_DATASET_HASH=None


def _initialize(examples,dataset_hash,barrier):
    global _EXAMPLES,_DATASET_HASH
    _EXAMPLES=examples;_DATASET_HASH=dataset_hash
    barrier.wait(timeout=60)


def _execute(task):
    return execute_task(task,_EXAMPLES,_DATASET_HASH)


def _ready():return os.getpid()


class SequentialBackend:
    def __init__(self,examples,dataset_hash):
        self.examples,self.dataset_hash=examples,dataset_hash
        self.partitions=1;self.stats={'retries':0,'failedTasks':0}

    def map(self,tasks):return [execute_task(task,self.examples,self.dataset_hash) for task in tasks]
    def close(self):pass


class ParallelBackend:
    def __init__(self,examples,dataset_hash,processes=2,timeout=30):
        if type(processes) is not int or not 1<=processes<=16 or not math.isfinite(timeout) or timeout<=0:raise ValueError('parallel_limits')
        self.partitions=processes;self.timeout=timeout
        self.stats={'retries':0,'failedTasks':0};self.failed=False
        context=multiprocessing.get_context('spawn');barrier=context.Barrier(processes)
        started=time.monotonic()
        self.pool=ProcessPoolExecutor(max_workers=processes,mp_context=context,
                                     initializer=_initialize,initargs=(examples,dataset_hash,barrier))
        try:
            futures=[self.pool.submit(_ready) for _ in range(processes)]
            for future in futures:future.result(timeout=timeout)
        except Exception:
            self.failed=True
            if hasattr(self.pool,'terminate_workers'):self.pool.terminate_workers()
            else:self.pool.shutdown(wait=False,cancel_futures=True)
            raise
        self.stats.update(poolStartupSeconds=time.monotonic()-started,configuredProcesses=processes)

    def map(self,tasks):
        futures=[self.pool.submit(_execute,task) for task in tasks];end=time.monotonic()+self.timeout
        try:return [future.result(timeout=max(.001,end-time.monotonic())) for future in futures]
        except Exception:
            self.failed=True;self.stats['failedTasks']+=len(tasks)
            for future in futures:future.cancel()
            # Python 3.14 provides public hard termination; older runtimes finish bounded tasks.
            if hasattr(self.pool,'terminate_workers'):self.pool.terminate_workers()
            else:self.pool.shutdown(wait=False,cancel_futures=True)
            raise

    def close(self):
        if not self.failed:self.pool.shutdown(wait=True,cancel_futures=True)
