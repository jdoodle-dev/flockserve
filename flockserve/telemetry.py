from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
import logging, sys, os


def get_logger(verbosity):
    log_level = 10 if verbosity >= 2 else 20 if verbosity == 1 else 40

    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)

    log_file_path = os.path.join(os.path.expanduser("~"), "flockserve.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(log_level)  # Set the logging level for the file
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)  # Set the logging level for stdout
    logger.addHandler(stream_handler)

    return logger


class OTLPMetricsGenerator:
    def __init__(
        self, metrics_id, otel_collector_endpoint, otel_metrics_exporter_settings
    ):
        """
        If metrics_id smaller than 0,  then no metrics are generated.
        """
        self.metrics_id = metrics_id

        if metrics_id >= 0:
            # Configure OTLP exporter
            otlp_exporter = OTLPMetricExporter(
                # Endpoint and other configurations specific to your environment
                endpoint=otel_collector_endpoint,
                **otel_metrics_exporter_settings,
            )

            # Set the MeterProvider
            metrics.set_meter_provider(
                MeterProvider(
                    metric_readers=[
                        PeriodicExportingMetricReader(
                            exporter=otlp_exporter, export_interval_millis=120000
                        )
                    ],
                )
            )

            # Obtain a meter
            meter = metrics.get_meter(__name__)

            self.meters = {}
            self.meters["task_queue_meter"] = meter.create_up_down_counter(
                name=f"taskqueuecounter{self.metrics_id}",
                description="Number of requests in queue",
            )
            self.meters["worker_meter"] = meter.create_histogram(
                name=f"allworkers{self.metrics_id}",
                description="Number of Workers",
                unit="1",
            )
            self.meters["live_worker_meter"] = meter.create_histogram(
                name=f"liveworkers{self.metrics_id}",
                description="Number of live Workers",
                unit="1",
            )
            self.meters["worker_load_meter"] = meter.create_histogram(
                name=f"workerload{self.metrics_id}",
                description="Queue length / Total capacity of all workers",
                unit="%",
            )
            self.meters["readiness_meter"] = meter.create_histogram(
                name=f"readinessstatus{self.metrics_id}",
                description="Status Showing Healthy",
                unit="1",
            )
            self.meters["load_meter"] = meter.create_histogram(
                name=f"load{self.metrics_id}", description="Load"
            )
            self.meters["queue_length_running_mean"] = meter.create_histogram(
                name=f"queuelengthrunningmean{self.metrics_id}",
                description="Queue Length Running Mean",
            )
            self.meters["request_counter"] = meter.create_counter(
                name=f"requestcounter{self.metrics_id}",
                unit="1",
                description="Total Requests Counter",
            )

        else:
            self.meters = {}
