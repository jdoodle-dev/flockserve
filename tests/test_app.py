import requests
import subprocess
import aiohttp
import asyncio
import time
import sky
import json

COMMAND = [
    "flockserve",
    "--skypilot_task",
    "examples/serving_tgi_cpu_generate.yaml",
    "--port",
    "8080",
    "--autoscale_up",
    "3",
    "--autoscale_down",
    "1",
    "--max_workers",
    "2",
    "--queue_tracking_window",
    "60",
    "--verbosity",
    "2",
    "--metrics_id",
    "-1",
    "worker_name_prefix",
    "worker",
]

BASE_URL = "http://localhost:8080"
TEST_URL = BASE_URL + "/generate"


async def make_request(url, payload, results_queue, idx):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            # Handle the response as needed
            res = await response.text()
            await results_queue.put((idx, res))


async def send_requests(payloads, url, results_queue):
    tasks = [
        make_request(url, payload, results_queue, idx)
        for idx, payload in enumerate(payloads)
    ]
    await asyncio.gather(*tasks)
    return results_queue


def apply_load(url, payload):
    payloads = [payload] * 500
    results_queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(send_requests(payloads, url, results_queue))
    # Now you can retrieve results from the queue
    while not results_queue.empty():
        result = loop.run_until_complete(results_queue.get())
        print(result)


def kill_flockserve_and_clusters(pid=None):
    while True:
        try:
            clusters = sky.status()
            [sky.down(cluster_name=cluster["name"], purge=True) for cluster in clusters]
            if pid is not None:
                subprocess.Popen(["kill", "-9", f"{pid}"])
            break
        except Exception as e:
            print(f"Error: {e}")
            print(f"Catched the error, will rerun the command again.")
            time.sleep(30)


def test_build(n_minutes_threshold=20, kill_after_test=True):
    """
    If successfull, Either kill the server and return nothing OR not kill the server and return the process
    If not successfull, kill the server and raise an exception

    :param n_minutes_threshold:
    :param kill_after_test:
    :return:
    """

    print(" ".join(COMMAND))
    process = subprocess.Popen(COMMAND)
    print(f"PID: {process.pid}")

    start_time = time.perf_counter()
    # If successfull, Either kill the server and return nothing OR not kill the server and return the process
    while True:
        try:
            r = requests.get(BASE_URL)
            if r.json()["ready_worker_count"] >= 1:
                if kill_after_test:
                    kill_flockserve_and_clusters(process.pid)
                    time.sleep(30)
                else:
                    return process
            else:
                time.sleep(10)
        except:
            time.sleep(10)

        # If not successfull, kill the server and raise an exception
        if time.perf_counter() - start_time > 60 * n_minutes_threshold:
            kill_flockserve_and_clusters()
            time.sleep(30)
            raise Exception(f"Server did not start in {n_minutes_threshold} minutes")


def test_autoscale():
    """
    Test the autoscaling feature of the server.

    If no clusters are running, it will start a new server and apply load to it.
    If a cluster with worker-0 is running, will start the flockserve and it will find the worker and apply load to it.
    If a cluster without worker-0 is running, it will kill the cluster and start a new server and apply load to it.
    :return:
    """

    clusters = sky.status()
    if len(clusters) == 0:
        test_build()
    elif len(clusters) == 1 and "worker-0" in [
        worker["name"] for worker in clusters[0]["workers"]
    ]:
        process = test_build(kill_after_test=False)
    else:
        kill_flockserve_and_clusters(
            pid=None
        )  # Only kills the clusters as we don't know if flockserve process is running and or PID of it

    with open("examples/server_test_tgi_generate.json", "r") as f:
        payload = json.load(f)

    # Apply load to the server and check if it scales up and down
    try:
        r = requests.post(TEST_URL, json=payload)
        assert r.status_code == 200

        apply_load(TEST_URL, payload)

        i = 0
        scale_up_success = False
        while i < 10:
            r = requests.get(BASE_URL)
            if r.json()["ready_worker_count"] > 1:
                scale_up_success = True
                break
            else:
                time.sleep(10)
                i += 1

        assert (
            scale_up_success
        ), "Expected more than one worker to be running after load test."

        i = 0
        scale_down_success = False
        while i < 20:
            r = requests.get(BASE_URL)
            if r.json()["ready_worker_count"] == 1:
                scale_down_success = True
                break
            else:
                time.sleep(30)
                i += 1

        assert (
            scale_down_success
        ), "Expected only one worker to be running after a while load is cut"

    except Exception as e:
        print(f"Error: {e}")

    # Clean up
    finally:
        subprocess.Popen(["kill", "-9", f"{process.pid}"])
        clusters = sky.status()
        [sky.down(cluster_name=cluster["name"], purge=True) for cluster in clusters]


def test_manual_scaling():
    with open("examples/server_test_tgi_generate.json", "r") as f:
        payload = json.load(f)

    try:
        r = requests.post(TEST_URL, json=payload)
        assert r.status_code == 200
    except Exception as e:
        print(f"Error: {e}")

    r = requests.get(
        "http://localhost:8080/add_new_node", headers={"node_control_key": "tmp123"}
    )
    r = requests.get("http://localhost:8080/")
    r = requests.get("http://localhost:8080/health")


if __name__ == "__main__":
    test_flockserve()

