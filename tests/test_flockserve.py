import pytest
import aiohttp
from unittest.mock import Mock, patch, create_autospec, AsyncMock
from flockserve.flockserve import (
    FlockServe,
)  # adjust import according to your project structure
import json, logging
from functools import partial

logger = logging.getLogger(__name__)
# Set logger to debug level
logger.setLevel(logging.DEBUG)
# Create a console handler
console = logging.StreamHandler()
# Set level to debug
console.setLevel(logging.DEBUG)
# Add the console handler to the logger
logger.addHandler(console)


payload_fixture_names = [
    "payload_1498777",
    "payload_929368",
    "payload_1765342",
    "payload_2369314",
    "payload_2280559",
    "payload_2168603",
    "payload_2185029",
    "payload_1466073",
]

response_fixture_names = [
    name.replace("payload", "response") for name in payload_fixture_names
]


payload_files = [
    f"tests/fixtures/{fixture_name}" for fixture_name in payload_fixture_names
]
response_files = [
    f"tests/fixtures/{fixture_name}.txt" for fixture_name in response_fixture_names
]


@pytest.fixture
def load_payload():
    def _load_payload(file_name):
        with open(file_name) as f:
            return json.load(f)

    return _load_payload


@pytest.fixture
def mocked_flockserve():

    # 'mock_init' here is a mock object representing '__init__'.
    # We don't directly call or manipulate it in this test, but it's present as an argument.
    with patch("flockserve.flockserve.FlockServe", "__init__"):  # , return_value=None

        # For mocked initializations, create_autospec initiates an object with same methods and attributes without calling Flockserve.__init__()
        flockserve_obj = create_autospec(FlockServe, instance=True)
        flockserve_obj.worker_manager = (
            Mock()
        )  # Creates the worker_manager attribute on the mock
        flockserve_obj.load_balancer = Mock()
        flockserve_obj.insert_dicts = []
        # Change the start_skypilot_worker method on the fake instance to not do anything
        flockserve_obj.worker_manager.start_skypilot_worker = Mock(return_value=None)
        flockserve_obj.app = Mock()
        flockserve_obj.app.state = Mock()

        # Replace the mocked function handle_stream_request3 with the real one, bound to the mock object
        flockserve_obj.handle_stream_request3 = partial(
            FlockServe.handle_stream_request3, flockserve_obj
        )
        logger.debug(flockserve_obj.handle_stream_request3)

        return flockserve_obj


def test_flock_serve_creation(mocked_flockserve):
    # Your test code here using the mocked_flock_serve fixture
    assert mocked_flockserve is not None
    assert isinstance(mocked_flockserve, FlockServe)


# async def async_line_reader(filename):
#     with open(filename, "r") as f:
#         while line := f.readline():
#             yield line.encode()  # encoding to bytes as `iter_any` yields bytes
#

# @pytest.fixture(params=response_files)  # example fixture files
# def mock_stream(request):
#     return async_line_reader(
#         request.param
#     )  # special fixture to access provided pararms
#


async def async_line_reader(filename, chunk_size=1024):
    with open(filename, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            logger.debug(f"yielding chunk: {chunk.decode('utf-8')}")
            if not chunk:
                break
            logger.debug(f"yielding chunk: {chunk.decode('utf-8')}")
            yield chunk


@pytest.fixture(params=response_files)  # example fixture files
def mock_stream(request):
    logger.debug("request param:" + request.param)
    return async_line_reader(request.param)
    # return lambda size: async_line_reader(
    # request.param, chunk_size=size
    # )  # it now takes a size argument


# TODO:This test is not ready yet,
@pytest.mark.asyncio
async def test_handle_stream_request3(mock_stream, mocked_flockserve):
    headers = {}  # Your headers here
    endpoint_path = "/test_path"

    # Mock the select_worker function to return a worker with a specific base url
    with patch.object(
        mocked_flockserve.load_balancer, "select_worker", new_callable=AsyncMock
    ) as mock_select_worker:

        mock_select_worker.return_value = Mock()  # Create a simple mock object
        mock_select_worker.return_value.base_url = "http://test_url"
        print(f"selected worker: {mock_select_worker.return_value.base_url}")

        # Mock the http_client.post function to return a dummy response
        with patch.object(
            mocked_flockserve.app.state.http_client, "post", new_callable=AsyncMock
        ) as mock_post:
            # with patch.object(aiohttp.ClientSession, "post", new_callable=AsyncMock) as mock_post:
            # Create a dummy HTTPResponse with iter_any replaced by our async_line_reader
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.content.iter_any.side_effect = mock_stream
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = (
                None  # this can be a mock too, if necessary
            )
            # logger.debug("mock_post:\n")
            # logger.debug(type(mock_post))
            # logger.debug(mock_post.__dict__)

            # Now call handle_stream_request2
            data = '{"Comment.nvim": { "branch": "master", "commit": "0236521ea582747b58869cb72f70ccfa967d2e89" }}'.encode()  # Provide the appropriate payload for the post body
            stream_generator = mocked_flockserve.handle_stream_request3(
                data, headers, endpoint_path
            )

            # Gather all the results from the stream
            result = [res async for res in stream_generator]
            # result = [res async for res in await stream_generator]
            mock_post.assert_called()

            # Test assertions here
            logger.info(result)
