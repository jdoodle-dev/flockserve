"""Module for monitoring and managing worker processes."""

import asyncio
import aiohttp
import multiprocessing
from dataclasses import dataclass, field
from typing import Optional, Dict, List
import sky
from .utils import record_metrics, is_health_failed
import time
import logging
from datetime import datetime


@dataclass
class WorkerHandler:
    worker_name: str
    worker_type: str
    capacity: int
    queue_length: int = 0
    initializing: bool = True
    post_initialization_done: bool = False
    ready: bool = False
    session: Optional[aiohttp.ClientSession] = field(default=None, init=False)
    base_url: Optional[str] = None
    # NOTE: assuming there wouldn't be any need for lock when modifying this field as one part of the code modifying health records while other part modifying/reading wouldn't be a problem
    health_records: List[tuple] = field(
        default_factory=list
    )  # [(timestemp, readiness)]    -1: initializing, 0: Setup phase      1: not healthy,     2:healthy
    initialization_time: float = field(default_factory=time.time)

    # handle: Optional[Any] = None


class WorkerManager:
    def __init__(self, flockserve):
        self.worker_lock = asyncio.Lock()
        self.worker_handlers = []
        self.flockserve = flockserve

    async def start_skypilot_worker(
        self, worker_id, worker_type="skypilot", reinit=False
    ):
        worker_name = (
            self.flockserve.worker_name_prefix + "-" + str(worker_id)
        )  # + generate_random_string(length=5)
        self.launcher_sub_process = multiprocessing.Process(
            target=WorkerManager.launch_task_process,
            args=(
                worker_name,
                sky.Task.from_yaml(self.flockserve.skypilot_task),
                reinit,
            ),
        )
        self.worker_handlers.append(
            WorkerHandler(
                worker_name,
                worker_type,
                self.flockserve.worker_capacity,
                queue_length=0,
                initializing=True,
                ready=False,
                initialization_time=time.time(),
            )
        )
        return self.launcher_sub_process.start()

    @staticmethod
    def launch_task_process(worker_name, skypilot_task, reinit):
        if reinit:
            sky.cancel(cluster_name=worker_name, all=True)
        # try:
        if WorkerManager.any_running_jobs(worker_name):
            self.logger.info("Job already running, skipping launch.")
            pass
        else:
            sky.launch(
                skypilot_task,
                cluster_name=worker_name,
                retry_until_up=False,
                detach_run=True,
                # dryrun=True,
            )
            print("Sky launch done.")
        # except Exception as e:
        #     #pass
        #     print("Error:", e)

    async def finished_initializing(self, worker_handler: WorkerHandler):
        cluster_statuses = sky.status(cluster_names=None, refresh=False)
        cluster_status = next(
            (x for x in cluster_statuses if x["name"] == worker_handler.worker_name),
            None,
        )
        self.flockserve.logger.debug(f"cluster_status: {cluster_status}")

        # Head IP only exists for the workers that have initialization completed.
        if cluster_status and isinstance(cluster_status.get("handle", {}).head_ip, str):
            return True
        else:
            return False

    async def worker_ready(self, worker_handler: WorkerHandler):
        try:
            async with worker_handler.session.get(
                f"{worker_handler.base_url}{self.flockserve.worker_ready_path}"
            ) as response:
                return response.status == 200
        except Exception as e:
            return False

    @staticmethod
    def worker_exists(worker_name):
        return len(sky.status(cluster_names=worker_name, refresh=False)) != 0

    @staticmethod
    def worker_available(worker: WorkerHandler):
        return (
            worker.capacity - worker.queue_length > 0
            and not worker.initializing
            and worker.ready
        )

    async def ready_worker_count(self):
        return sum([(not w.initializing) and (w.ready) for w in self.worker_handlers])

    async def shutdown_workers(self):
        for worker in self.worker_handlers:
            await self.delete_worker(worker)

    @staticmethod
    def any_running_jobs(worker_name):
        if not WorkerManager.worker_exists(worker_name):
            return False
        else:
            skypilot_job_queue = sky.queue(cluster_name=worker_name)
            return next(
                (
                    True
                    for job in skypilot_job_queue
                    if job.get("status").value == "RUNNING"
                ),
                False,
            )

    async def setup_initialized_worker(self, worker_handler: WorkerHandler, port):
        if await self.finished_initializing(worker_handler):
            # Set base_url
            cluster_statuses = sky.status(cluster_names=None, refresh=False)
            cluster_status = next(
                (
                    x
                    for x in cluster_statuses
                    if x["name"] == worker_handler.worker_name
                ),
                None,
            )
            worker_handler.base_url = (
                "http://" + cluster_status["handle"].head_ip + f":{port}"
            )
            worker_handler.session = aiohttp.ClientSession()

    async def periodic_load_check(self, queue_length_running_mean):
        try:
            worker_load = sum([w.queue_length for w in self.worker_handlers])
            ready_worker_count = await self.ready_worker_count()

            record_metrics(
                self.flockserve.metrics.meters,
                {
                    "worker_meter": len(self.worker_handlers),
                    "live_worker_meter": ready_worker_count,
                    "worker_load_meter": worker_load,
                    "queue_length_running_mean": round(queue_length_running_mean, 2),
                },
            )

            self.flockserve.logger.info(
                f"Workers: {len(self.worker_handlers)}, "
                f"Workers Ready: {ready_worker_count}, "
                f"Worker Load: {worker_load}, "
                f"QLRM: {round(queue_length_running_mean,2)}"
            )

            scale = await self.flockserve.autoscaler.autoscale(
                queue_length_running_mean, self.worker_handlers, ready_worker_count
            )
            if scale > 0:
                self.flockserve.logger.warning("High load detected, creating worker")
                await self.start_skypilot_worker(
                    worker_id=self.get_next_worker_id(), reinit=False
                )
            elif scale < 0:
                self.flockserve.logger.warning("Low load detected, deleting worker")
                await self.delete_worker(
                    min(
                        [
                            worker
                            for worker in self.worker_handlers
                            if not worker.initializing
                        ],
                        key=lambda w: w.queue_length,
                    )
                )
        except Exception as e:
            self.flockserve.logger.info("Error below in periodic_load_check;")
            self.flockserve.logger.info(e)

    async def periodic_worker_check(self):
        while True:
            for worker in list(self.worker_handlers):
                try:
                    self.flockserve.logger.debug(
                        f"Checking worker: {worker.worker_name}"
                    )
                    self.flockserve.logger.debug(f"initializing: {worker.initializing}")
                    self.flockserve.logger.debug(f"ready: {worker.ready}")

                    if worker.initializing:
                        worker.health_records.append(
                            (time.time(), -1)
                        )  # Still initializing
                        if await self.finished_initializing(worker):

                            async with self.worker_lock:
                                try:
                                    await self.setup_initialized_worker(
                                        worker, self.flockserve.port
                                    )
                                    worker.initializing = False
                                    self.flockserve.logger.info(
                                        f"Worker: {worker.worker_name}, "
                                        f"initialization completed: {worker.base_url}"
                                    )
                                except Exception as e:
                                    worker.initializing = True
                                    self.flockserve.logger.info(
                                        f"Error during initialization : {e}"
                                    )

                    else:
                        try:
                            if await self.worker_ready(worker):
                                worker.health_records.append((time.time(), 1))
                                if not (worker.ready):
                                    worker.ready = True

                                self.flockserve.logger.info(
                                    f"Worker ready: {worker.worker_name} "
                                )
                                record_metrics(
                                    self.flockserve.metrics.meters,
                                    {"readiness_meter": 1},
                                )
                            else:
                                worker.health_records.append((time.time(), 0))
                                self.flockserve.logger.info(
                                    f"Worker not ready: {worker.worker_name} "
                                )
                                record_metrics(
                                    self.flockserve.metrics.meters,
                                    {"readiness_meter": 0},
                                )
                                worker.ready = False
                        except Exception as e:
                            self.flockserve.logger.info(
                                f"Error during health check : {e}"
                            )
                            worker.ready = False
                except Exception as e:
                    self.flockserve.logger.info(f"Error during health check : {e}")
            await asyncio.sleep(30)

    async def health_history_check(
        self, initialization_n_min_limit, health_n_min_limit
    ):
        while True:
            for worker in list(self.worker_handlers):
                self.flockserve.logger.debug("=" * 50)
                self.flockserve.logger.debug(f"Worker Name: {worker.worker_name}")
                self.flockserve.logger.debug("=" * 50)
                if self.flockserve.logger.getEffectiveLevel() <= logging.DEBUG:
                    self.flockserve.logger.debug(f"Worker health records below: ")
                    for record in worker.health_records:
                        self.flockserve.logger.debug(record)

                # initilization check
                if (
                    time.time() - worker.initialization_time
                    > initialization_n_min_limit * 60
                ):  # If worker started to be provisioned just initialization_n_min_limit ago don't take any action
                    if (
                        worker.initializing
                    ):  # If provisioned more thaninitialization_n_min_limit ago still initializing --> Delete Worker
                        self.flockserve.logger.info("=" * 50)
                        self.flockserve.logger.info(
                            f"Initialization failed for {worker.worker_name}"
                        )
                        self.flockserve.logger.info("=" * 50)

                        self.flockserve.logger.info(
                            f"Init time:{datetime.fromtimestamp(worker.initialization_time).strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        self.flockserve.logger.info(
                            f"Current time:{datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')}"
                        )

                        await self.delete_worker(worker)
                        # If provisioned more thaninitialization_n_min_limit ago AND not healthy more than last health_n_min_limit --> Delete Worker
                    elif is_health_failed(
                        worker.health_records, last_n_sec=health_n_min_limit * 60
                    ):
                        self.flockserve.logger.info("=" * 50)
                        self.flockserve.logger.info(
                            f"Health history Failed for {worker.worker_name}"
                        )
                        self.flockserve.logger.info("=" * 50)
                        await self.delete_worker(worker)
                    worker.health_records = [
                        rec
                        for rec in worker.health_records
                        if time.time() - rec[0] < 30 * 60
                    ]  # Remove entries older than 30mins
            await asyncio.sleep(60)

    def get_next_worker_id(self):
        existing_worker_names = [w.worker_name for w in self.worker_handlers]
        worker_id = 0
        while (
            self.flockserve.worker_name_prefix + "-" + str(worker_id)
            in existing_worker_names
        ):
            worker_id += 1
        return worker_id

    async def delete_worker(self, worker: WorkerHandler) -> None:
        self.flockserve.logger.info(f"Deleting worker: {worker.worker_name}")
        async with self.worker_lock:
            i = 0
            while worker.queue_length > 0 and i < 20:  # Assumes max 2 min response
                i += 1
                await asyncio.sleep(6)
            if worker in self.worker_handlers:
                while True:
                    try:
                        # await worker.session.close()
                        # self.flockserve.logger.info(
                        # f"Cut the connection session with {worker.worker_name}"
                        # )
                        if WorkerManager.worker_exists(worker.worker_name):
                            sky.down(cluster_name=worker.worker_name, purge=True)
                            self.flockserve.logger.info(
                                f"Run skydown for {worker.worker_name}"
                            )
                        if worker.worker_name in [
                            w.worker_name for w in self.worker_handlers
                        ]:
                            self.worker_handlers.remove(worker)
                            self.flockserve.logger.info(
                                f"Removed  {worker.worker_name} from worker_handlers"
                            )
                        break
                    except Exception as e:
                        self.flockserve.logger.error(
                            f"Following Error During Deleting {worker.worker_name}\n\n{e}"
                        )
                        self.flockserve.logger.info(
                            f"Retrying Deleting {worker.worker_name}"
                        )
