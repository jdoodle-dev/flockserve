# FlockServe

## Open-source Sky Computing Inference Endpoint

### Overview

FlockServe is an open-source library for deploying production-ready AI inference endpoints. Similar to
closed-source commercial inference endpoints, FlockServe adds the capabilities of autoscaling, load balancing,
and monitoring to an inference engine server, turning these into production-ready solutions for serving AI
predictions at dynamic request rates and high volumes.

FlockServe uses SkyPilot as the node provisioner, taking SkyPilot task files for single inference engine servers and
autoscales these based on request volume. Due to using SkyPilot, an inference endpoint developed with FlockServe will
work natively across multiple clouds, and can be migrated between providers just by changing the SkyPilot configuration.

Any inference engine server can be used, and examples of SkyPilot task files are given for vLLM and TGI. Both the
OpenAI and /generate APIs used by these are supported. FlockServe runs on FastAPI and uvicorn, so requests are
processed fully asynchronously.

FlockServe has a modular design, and different solutions for autoscaling and load balancing can be used. The default
option for autoscaling uses a running mean estimate of request queue lengths, which is effective for LLM autoscaling.
The default option for load balancing uses Least Connection Load Balancing, which is also well suited for serving LLMs.

### Features

- **Scalability:** Easily scale your inference endpoint based on the demand using cloud resources.
- **Skypilot Integration:** Leverages the power of skypilot for sky computing free from vendor lock-in
- **Flexible Model Support:** Supports any inference engine such as vLLM and TGI, and models supported by these.
- **RESTful API:** Simple and intuitive API for interacting with the inference endpoint.
- **Monitoring and Logging:** Monitor the performance and logs of deployed models for effective debugging and
  optimization.

### Getting Started

#### Prerequisites

- Python >= 3.7, < 3.12
- Docker (if using containerized deployment)

#### Installation

You can install FlockServe from PyPI with pip:

```
pip install flockserve
```

#### Usage

Running from command line:

```
flockserve --skypilot_task serving_tgi_cpu_openai.yaml
```

From Python:

```
from flockserve import FlockServe
fs = FlockServe(skypilot_task="serving_tgi_cpu_generate.yaml")
fs.run()
```

The mandatory argument is skypilot_task. The available arguments are:

| Argument                         | Default Value           | Description                                                          |
|----------------------------------|-------------------------|----------------------------------------------------------------------|
| `skypilot_task`                  | *Required*              | The path to a YAML file defining the SkyPilot task.                  |
| `worker_capacity`                | `30`                    | Maximum number of tasks a worker can handle concurrently.            |
| `worker_name_prefix`             | `'skypilot-worker'`     | Prefix for naming workers.                                           |
| `host`                           | `'0.0.0.0'`             | The host IP address to bind the server.                              |
| `port`                           | `-1`                    | The port number to listen on. If <0, port is read from skypilot task |
| `worker_ready_path`              | `"/health"`             | Path to check worker readiness.                                      |
| `min_workers`                    | `1`                     | Minimum number of workers to maintain.                               |
| `max_workers`                    | `2`                     | Maximum number of workers allowed.                                   |
| `autoscale_up`                   | `7`                     | Load threshold to trigger scaling up of workers.                     |
| `autoscale_down`                 | `4`                     | Load threshold to trigger scaling down of workers.                   |
| `queue_tracking_window`          | `600`                   | Time window in seconds to track queue length for autoscaling.        |
| `node_control_key`               | `None`                  | Secret key for node management operations.                           |
| `metrics_id`                     | `1`                     | Suffix for generated OTEL metrics -- Set different for Prod & QA     |
| `verbosity`                      | `1`                     | 0: No logging, 1: Info,  2: Debug                                    |
| `otel_collector_endpoint`        | `http://localhost:4317` | Address of OTEL collector to export Telemetry to                     |
| `otel_metrics_exporter_settings` | `{}`                    | Extra settings for OTEL metrics exporter in key-value pair format    |

Once FlockServe is started, it will print the outputs from SkyPilot, as well as report FlockServe metrics periodically:

```
INFO:flockserve.flockserve:Workers: 1, Workers Ready: 0, Worker Load: 0, QLRM: 0.0
```

Once "Workers Ready" is more than 0, you can send requests:

```
curl -X POST -H "Content-Type: application/json" 0.0.0.0:3000/v1/chat/completions -d "@server_test_tgi_openai.json"
```

### Acknowledgments

FlockServe was developed at [JDoodle](https://www.jdoodle.com/), the AI-powered online platform for coding. 