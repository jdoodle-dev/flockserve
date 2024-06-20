"""Module for load balancing algorithms."""
import asyncio
from typing import List
from flockserve.workermanager import WorkerManager, WorkerHandler

import random

class LoadBalancer:
    """
    Base class for a load balancer.
    """
    def __init__(self, flockserve):
        self.flockserve = flockserve

    async def select_worker(self) -> WorkerHandler:
        """Selects an appropriate worker based on the implemented strategy."""
        raise NotImplementedError


class LeastConnectionLoadBalancer(LoadBalancer):
    """
    Selects the worker with the least number of queued tasks.
    """
    def __init__(self, flockserve):
        super().__init__(flockserve)

    async def select_worker(self) -> WorkerHandler:
        """Selects the worker with the least number of connections."""
        while True:
            available_workers: List[WorkerHandler] = [
                worker for worker in self.flockserve.worker_manager.worker_handlers
                if WorkerManager.worker_available(worker)
            ]
            if available_workers:
                # selected_worker = min(available_workers, key=lambda w: w.queue_length)
                selected_worker = random.choice(available_workers)
                break
            await asyncio.sleep(1)
        return selected_worker
