"""Module for monitoring and managing worker processes."""
import asyncio
import aiohttp
import multiprocessing
from dataclasses import dataclass, field
from typing import Optional
import sky

@dataclass
class WorkerHandler:
	worker_name: str
	worker_type: str
	capacity: int
	queue_length: int = 0
	initializing: bool = True
	ready: bool = False
	session: Optional[aiohttp.ClientSession] = field(default=None, init=False)
	base_url: Optional[str] = None
	# handle: Optional[Any] = None
	

class WorkerManager():
	def __init__(self, flockserve):
		self.worker_lock = asyncio.Lock()
		self.worker_handlers = []
		self.flockserve = flockserve

	async def start_skypilot_worker(self, worker_id, worker_type='skypilot', reinit=False):
		worker_name = self.flockserve.worker_name_prefix + '-' + str(worker_id)
		self.launcher_sub_process = multiprocessing.Process(target=WorkerManager.launch_task_process, args=(
			worker_name, self.flockserve.skypilot_task, reinit))
		self.worker_handlers.append(WorkerHandler(worker_name, worker_type, self.flockserve.worker_capacity,
		                                          queue_length=0, initializing=True, ready=False))
		return self.launcher_sub_process.start()

	@staticmethod
	def launch_task_process(worker_name, skypilot_task, reinit):
		if reinit:
			sky.cancel(cluster_name=worker_name, all=True)
		# try:
		if WorkerManager.any_running_jobs(worker_name):
			# self.logger.info("Job already running, skipping launch.")
			pass
		else:
			sky.launch(skypilot_task, cluster_name=worker_name, retry_until_up=False)
			print("Sky launch done.")
		# except Exception as e:
		#     #pass
		#     self.logger.info("Error:", e)


	@staticmethod
	async def finished_initializing(worker_handler: WorkerHandler):
		cluster_statuses = sky.status(cluster_names=None, refresh=False)
		cluster_status = next((x for x in cluster_statuses if x['name'] == worker_handler.worker_name), None)
		# Add verbosity-based logging
		# print('='*50)
		# print("cluster_status")
		# print('='*50)
		# print(cluster_status)

		# Head IP only exists for the workers that have initialization completed.
		if cluster_status and isinstance(cluster_status.get('handle', {}).head_ip, str):
			return True
		else:
			return False

	async def worker_ready(self, worker_handler: WorkerHandler):
		try:
			async with (worker_handler.session.get(f"{worker_handler.base_url}{self.flockserve.worker_ready_path}")
			            as response):
				return response.status == 200
		except Exception as e:
			return False
		
	@staticmethod
	def worker_exists(worker_name):
		return len(sky.status(cluster_names=worker_name, refresh=False)) != 0

	@staticmethod
	def worker_available(worker:WorkerHandler):
		return worker.capacity - worker.queue_length > 0 and not worker.initializing and worker.ready

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
			return next((True for job in skypilot_job_queue if job.get('status').value == 'RUNNING'), False)

	@staticmethod
	async def setup_initialized_worker(worker_handler: WorkerHandler, port):
		if await WorkerManager.finished_initializing(worker_handler):
			# Set base_url
			cluster_statuses = sky.status(cluster_names=None, refresh=False)
			cluster_status = next((x for x in cluster_statuses if x['name'] == worker_handler.worker_name), None)
			worker_handler.base_url = "http://" + cluster_status['handle'].head_ip + f":{port}"
			worker_handler.session = aiohttp.ClientSession()

	async def periodic_load_check(self, queue_length_running_mean):
		try:
			worker_load = sum([w.queue_length for w in self.worker_handlers])
			ready_worker_count = await self.ready_worker_count()
			self.flockserve.logger.info(f"Workers: {len(self.worker_handlers)}, "
			                            f"Workers Ready: {ready_worker_count}, "
			                            f"Worker Load: {worker_load}, "
			                            f"QLRM: {round(queue_length_running_mean,2)}")

			scale = await self.flockserve.autoscaler.autoscale(queue_length_running_mean, self.worker_handlers,
			                                                   ready_worker_count)
			if scale > 0:
				self.flockserve.logger.warning("High load detected, creating worker")
				await self.start_skypilot_worker(worker_id=self.get_next_worker_id(), reinit=False)
			elif scale < 0:
				self.flockserve.logger.warning("Low load detected, deleting worker")
				await self.delete_worker(min([worker for worker in self.worker_handlers if not worker.initializing],
											 key=lambda w: w.queue_length))

		except Exception as e:
			self.flockserve.logger.info("Error below in periodic_load_check;")
			self.flockserve.logger.info(e)

	async def periodic_worker_check(self):
		while True:
			for worker in list(self.worker_handlers):
				# Add verbosity levels
				# print('Checking worker: ', worker.worker_name)
				# print('initializing: ', worker.initializing)
				# print('ready: ', worker.ready)

				if worker.initializing:
					if await self.finished_initializing(worker):
						try:
							await self.setup_initialized_worker(worker, self.flockserve.port)
							worker.initializing = False
							self.flockserve.logger.info(f"Worker: {worker.worker_name}, "
							                 f"initialization completed: {worker.base_url}")
						except Exception as e:
							worker.initializing = True
							self.flockserve.logger.info(f"Error during initialization : {e}")

				else:
					try:
						if await self.worker_ready(worker):
							if not(worker.ready):
								worker.ready = True
								self.flockserve.logger.info(f"Worker ready: {worker.worker_name} ")
						else:
							self.flockserve.logger.info(f"Worker not ready: {worker.worker_name} ")
							worker.ready = False
					except Exception as e:
						self.flockserve.logger.info(f"Error during health check : {e}")
						worker.ready = False

				await asyncio.sleep(20)

	def get_next_worker_id(self):
		existing_worker_names = [w.worker_name for w in self.worker_handlers]
		worker_id = 0
		while self.flockserve.worker_name_prefix + "-" + str(worker_id) in existing_worker_names:
			worker_id += 1

		return worker_id

	async def delete_worker(self, worker: WorkerHandler) -> None:
		self.flockserve.logger.info(f"Deleting worker: {worker.base_url}")
		async with self.worker_lock:
			i = 0
			while worker.queue_length > 0 and i < 20: # Assumes max 2 min response
				i += 1
				await asyncio.sleep(6)
			if worker in self.worker_handlers:
				await worker.session.close()
				sky.down(cluster_name=worker.worker_name, purge=True)
				self.worker_handlers.remove(worker)

