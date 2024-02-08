from opentelemetry import metrics
from opentelemetry.exporter.cloud_monitoring import (
    CloudMonitoringMetricsExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.cloud_trace_propagator import (
    CloudTraceFormatPropagator,
)



class GCP_metrics_collector():
    def __init__(self, ENVIRONMENT_NAME, metrics_id, service_name):
        self.ENVIRONMENT_NAME = ENVIRONMENT_NAME
        self.metrics_id = metrics_id

        tracer_provider = TracerProvider()
        cloud_trace_exporter = CloudTraceSpanExporter()
        tracer_provider.add_span_processor(
            # BatchSpanProcessor buffers spans and sends them in batches in a
            # background thread. The default parameters are sensible, but can be
            # tweaked to optimize your performance
            BatchSpanProcessor(cloud_trace_exporter)
        )
        trace.set_tracer_provider(tracer_provider)

        set_global_textmap(CloudTraceFormatPropagator())

        tracer = trace.get_tracer(__name__)

        metrics.set_meter_provider(
            MeterProvider(
                metric_readers=[
                    PeriodicExportingMetricReader(
                        CloudMonitoringMetricsExporter(), export_interval_millis=25000
                    )
                ],
                resource=Resource.create(
                    {
                        "service.name"       : f"{ENVIRONMENT_NAME}-{service_name}",
                        "service.namespace"  : f"{ENVIRONMENT_NAME}-namespace",
                        "service.instance.id": f"{ENVIRONMENT_NAME}-instance",
                    }
                ),
            )
        )

        meter = metrics.get_meter(__name__)
        self.meters = {}
        self.meters['task_queue_meter'] = meter.create_up_down_counter(name=f"taskqueuecounter{metrics_id}",
                                                                       description="Number of requests in queue")
        self.meters['worker_meter'] = meter.create_histogram(name=f"allworkers{metrics_id}",
                                                             description="Number of Workers",
                                                             unit="1")
        self.meters['live_worker_meter'] = meter.create_histogram(name=f"liveworkers{metrics_id}",
                                                                  description="Number of live Workers", unit="1")
        self.meters['worker_load_meter'] = meter.create_histogram(name=f"workerload{metrics_id}",
                                                             description="Queue length / Total capacity of all workers",
                                                             unit="%")
        self.meters['health_meter'] = meter.create_histogram(name=f"healthstatus{metrics_id}",
                                                        description="Status Showing Healthy",
                                                        unit="1")
        self.meters['load_meter'] = meter.create_histogram(name=f"load{metrics_id}", description="Load")
        self.meters['queue_length_running_mean'] = meter.create_histogram(name=f"queuelengthrunningmean{metrics_id}",
                                                                     description="Queue Length Running Mean")
        self.meters['request_counter'] = meter.create_counter(name=f"requestcounter{metrics_id}", unit='1',
                                                         description="Total Requests Counter")
