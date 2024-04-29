"""Module for autoscaling algorithms."""

from typing import Any


class Autoscaler:
    """
    Base class for an autoscaler.

    Attributes:
        flockserve: FlockServe server to be autoscaled.
    """

    def __init__(
        self,
        flockserve,
        autoscale_up: int = 7,
        autoscale_down: int = 4,
        max_workers: int = 2,
        min_workers: int = 1,
    ) -> None:
        self.flockserve = flockserve
        self.autoscale_up = autoscale_up
        self.autoscale_down = autoscale_down
        self.max_workers = max_workers
        self.min_workers = min_workers


class RunningMeanLoadAutoscaler(Autoscaler):
    """
    Autoscaler that scales the server based on the running mean of requests on the workers.

    Attributes:
        autoscale_up (int): The threshold for scaling up.
        autoscale_down (int): The threshold for scaling down.
    """

    def __init__(
        self,
        flockserve,
        autoscale_up: int = 7,
        autoscale_down: int = 4,
        max_workers: int = 2,
        min_workers: int = 1,
    ) -> None:
        super().__init__(
            flockserve, autoscale_up, autoscale_down, max_workers, min_workers
        )

    async def autoscale(
        self,
        queue_length_running_mean: float,
        worker_handlers: list,
        live_worker_count: int,
    ) -> int:
        """Determines whether to scale up, down, or hold based on the running mean of the queue length."""
        if len(worker_handlers) < self.min_workers:
            return 1
        elif len(worker_handlers) > self.max_workers:
            return -1
        if live_worker_count != len(worker_handlers):
            return 0  # Autoscaling under way, don't change nodes
        elif (
            queue_length_running_mean > self.autoscale_up
            and len(worker_handlers) < self.max_workers
        ):
            return 1  # Scale up
        elif (
            queue_length_running_mean < self.autoscale_down
            and live_worker_count > self.min_workers
        ):
            return -1  # Scale down
        return 0  # No action
