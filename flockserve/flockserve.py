import asyncio
import logging
import time
import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import uvicorn
import json
import sky
from flockserve.telemetry import OTLPMetricsGenerator, get_logger

from typing import Dict, Any
from flockserve.loadbalancer import LeastConnectionLoadBalancer
from flockserve.autoscaler import RunningMeanLoadAutoscaler
from flockserve.utils import time_weighted_mean
from flockserve.workermanager import WorkerManager
from flockserve.database_connector import SQLiteConnector


class FlockServe:
    def __init__(
            self,
            skypilot_task: str,
            worker_capacity: int = 30,
            worker_name_prefix: str = 'skypilot-worker',
            host: str = '0.0.0.0',
            port: int = -1,
            worker_ready_path: str = "/health",
            min_workers: int = 1,
            max_workers: int = 2,
            autoscale_up: int = 7,
            autoscale_down: int = 4,
            queue_tracking_window: int = 600,
            node_control_key: str = None,
            metrics_id: int = 1,
            verbosity: int = 1,  # 0: no logging, 1: info, 2: debug
            otel_collector_endpoint: str = "http://localhost:4317",
            otel_metrics_exporter_settings: Dict[str, Any] = {},
    ) -> None:
        self.skypilot_task = sky.Task.from_yaml(skypilot_task)
        self.worker_capacity = worker_capacity
        self.worker_name_prefix = worker_name_prefix
        self.host = host
        self.port = self._determine_port(port)
        self.worker_ready_path = worker_ready_path
        self.queue_tracking_window = queue_tracking_window
        self.node_control_key = node_control_key

        self.app: FastAPI = FastAPI()
        FastAPIInstrumentor.instrument_app(self.app)
        self.queue_length: int = 0
        self.queue_tracker: Dict[float, int] = {time.time(): 0}  # {timestemp: queuelength at that time}
        self.queue_length_running_mean: float = 0
        self.app.state.http_client: aiohttp.ClientSession = None
        self.worker_manager = WorkerManager(self)
        self.load_balancer = LeastConnectionLoadBalancer(self)
        self.autoscaler = RunningMeanLoadAutoscaler(self, autoscale_up, autoscale_down=autoscale_down,
                                                    max_workers=max_workers, min_workers=min_workers)
        self.metrics = OTLPMetricsGenerator(metrics_id=metrics_id, otel_collector_endpoint=otel_collector_endpoint,
                                            otel_metrics_exporter_settings=otel_metrics_exporter_settings)
        self.logger = get_logger(verbosity)
        self.start_time = time.time()
        self.total_requests = 0
        self.db_connector = SQLiteConnector(db_name='flockserve.db', table_name='requests',
                                            extra_schema={'user'            : 'TEXT', 'platform': 'TEXT',
                                                          'request__task'   : 'TEXT', 'request__language': 'TEXT',
                                                          'request__inputs' : 'TEXT', 'request__inputs2': 'TEXT',
                                                          'response__status': 'TEXT', 'response__content': 'TEXT'})
        self.insert_dicts = []


        @self.app.get("/")
        async def root_handler():
            ready_worker_count = await self.worker_manager.ready_worker_count()
            return {"ready_worker_count"                              : ready_worker_count, "queue_length_running_mean":
                self.queue_length_running_mean, "current_queue_length": self.queue_length,
                    "uptime"                                          : time.time() - self.start_time,
                    "total_requests"                                  : self.total_requests}

        @self.app.get("/health")
        async def health_handler():
            return {"status": "healthy"}

        @self.app.get("/remove_existing_node")
        async def remove_existing_node(request: Request):
            headers = request.headers
            node_name = headers.get('node_name', None)
            if headers['node_control_key'] == self.node_control_key:
                try:
                    if node_name:
                        await self.worker_manager.delete_worker(
                            [worker for worker in self.worker_manager.worker_handlers if
                             worker.worker_name == node_name][0])
                    else:
                        await self.worker_manager.delete_worker(
                            min([worker for worker in self.worker_manager.worker_handlers if
                                 not worker.is_initializing],
                                key=lambda w: w.queue))
                    return {"message": "Removed the node."}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Error during processing: {e}")

        @self.app.get("/add_new_node")
        async def add_new_node(request: Request):
            headers = request.headers
            if headers['node_control_key'] == self.node_control_key:
                try:
                    await self.worker_manager.start_skypilot_worker(worker_id=self.worker_manager.get_next_worker_id(),
                                                                    reinit=False)
                    return {"message": "New node added."}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Error during processing: {e}")

        @self.app.on_event("startup")
        async def on_startup():
            await self.init_session()
            await self.worker_manager.start_skypilot_worker(worker_id=0, reinit=False)
            asyncio.create_task(self.set_queue_tracker())
            asyncio.create_task(self.run_periodic_load_check())
            asyncio.create_task(self.worker_manager.periodic_worker_check())
            asyncio.create_task(self.run_periodic_db_inserts())

        @self.app.on_event("shutdown")
        async def on_shutdown():
            await self.close_session()
            await self.worker_manager.shutdown_workers()

        @self.app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
        async def forward_request(request: Request, full_path: str):
            headers = {key: value for key, value in request.headers.items()}
            data = await request.body()
            if full_path == "generate":
                # stream = json.loads(data.decode('utf-8')).get('parameters', {}).get('stream', False)
                # if stream:
                #     return StreamingResponse(self.handle_stream_request(data, headers, f"/{full_path}"),
                #                              media_type="text/plain")
                # else:
                try:
                    s = time.perf_counter()
                    response = await self.handle_inference_request(data, headers, f"/{full_path}")
                    e = time.perf_counter()

                    incoming_req = json.loads(data.decode('utf-8'))

                    self.insert_dicts.append({'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                                   "execution_time": round(e - s, 2),
                                   'request'  : json.dumps(incoming_req),
                                   'response': response,
                                   'user'     : incoming_req.get('user', ''),
                                   'platform' : incoming_req.get('platform', ''),
                                   'request__task'   : incoming_req.get('task', ''),
                                   'request__language': incoming_req.get('language', ''),
                                   'request__inputs' :  incoming_req.get('inputs', ''),
                                   'request__inputs2': incoming_req.get('outputs', ''),
                                   })



                    return response
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Error during processing: {e}")
            else:
                # Handle other endpoints
                try:
                    return await self.handle_inference_request(data, headers, f"/{full_path}")
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Error during processing: {e}")

    def _determine_port(self, port: int) -> int:
        if port < 0:
            try:
                return int(list(self.skypilot_task.resources)[0].ports[0])
            except Exception as e:
                self.logger.error(f"Couldn't get port from Skypilot task: {e}")
                raise e  # Or set a default port value
        return port

    async def init_session(self) -> None:
        self.app.state.http_client = aiohttp.ClientSession()

    async def close_session(self) -> None:
        if self.app.state.http_client:
            await self.app.state.http_client.close()
            self.app.state.http_client = None

    async def set_queue_tracker(self):
        while True:
            self.queue_tracker[time.time()] = self.queue_length
            self.queue_tracker = {k: v for k, v in self.queue_tracker.items()
                                  if time.time() - k < self.queue_tracking_window}
            self.queue_length_running_mean = time_weighted_mean(self.queue_tracker)
            await asyncio.sleep(10)

    async def run_periodic_load_check(self):
        while True:
            await self.worker_manager.periodic_load_check(self.queue_length_running_mean)
            await asyncio.sleep(30)

    async def run_periodic_db_inserts(self):
        while True:
            try:
                if len(self.insert_dicts) > 1:
                    await self.db_connector.insert(self.insert_dicts)
                    self.insert_dicts = []
            except Exception as e:
                self.logger.error(f"Error during db inserts: {e}")
                for ins in self.insert_dicts:
                    print(ins)

            await asyncio.sleep(60)


    async def handle_inference_request(self, data: bytes, headers, endpoint_path) -> str:
        selected_worker = await self.load_balancer.select_worker()
        try:
            if (endpoint_path == "/generate" or endpoint_path == "/v1/completions/" or
                    endpoint_path == "/v1/chat/completions"):
                # Add to queue only for the requests coming to /generate
                try:
                    selected_worker.queue_length += 1
                    self.queue_length += 1
                    self.total_requests += 1

                    start = time.perf_counter()
                    async with self.app.state.http_client.post(f"{selected_worker.base_url}{endpoint_path}", data=data,
                                                               headers=headers) as response:
                        result = await response.text()
                        end = time.perf_counter()
                        if end - start > 30:
                            self.logger.warning(f"Time taken for inference: {end - start}"
                                                f"Input: {data.decode('utf-8')}"
                                                f"Output: {result}")
                        return result
                except Exception as e:
                    self.logger.error(f"Error handling request for worker {selected_worker.base_url}: {e}")
                    raise
                finally:
                    self.queue_length -= 1
                    selected_worker.queue_length -= 1
            elif endpoint_path == "/":
                async with self.app.state.http_client.get(f"{selected_worker.base_url}/", headers=headers) as response:
                    result = await response.text()
            else:
                return None
        except Exception as e:
            self.logger.error(f"Error handling request for worker {selected_worker.base_url}: {e}")
            raise
        return result

    async def handle_stream_request(self, data: bytes, headers, endpoint_path: str):
        selected_worker = await self.load_balancer.select_worker()

        async with self.app.state.http_client.post(f"{selected_worker.base_url}{endpoint_path}",
                                                   json=json.loads(data.decode('utf-8')),
                                                   headers=headers, timeout=None) as response:
            # Check if the response status is OK
            if response.status == 200:
                # Process the streamed data line by line
                async for line in response.content:
                    decoded_line = line.decode('utf-8').strip()
                    self.logger.info(f"decoded_line: {decoded_line}")
                    # Yield each line
                    yield decoded_line

    def run(self):
        uvicorn.run(self.app, host=self.host, port=self.port, timeout_keep_alive=5)
