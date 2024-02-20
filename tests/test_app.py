import requests
import subprocess
import aiohttp
import asyncio
import time
import sky
import json

async def make_request(url,payload, results_queue, idx):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            # Handle the response as needed
            res = await response.text()
            await results_queue.put((idx,res))

async def send_requests(payloads, url, results_queue):
    tasks = [make_request(url, payload, results_queue, idx ) for idx, payload in enumerate(payloads)]
    await asyncio.gather(*tasks)
    return results_queue

def apply_load(url, payload):
    payloads = [payload ]*500
    results_queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(send_requests(payloads, url, results_queue))
    # Now you can retrieve results from the queue
    while not results_queue.empty():
        result = loop.run_until_complete(results_queue.get())
        print(result)


def test_flockserve():
    # flockserve --skypilot_task examples/serving_tgi_cpu_generate.yaml --port 8080 --autoscale_up 3 --autoscale_down 1 --max_workers 2 --queue_tracking_window 60 --verbosity 2 --metrics_id 12
    command = ["flockserve", "--skypilot_task", "examples/serving_tgi_cpu_generate.yaml",  "--port", "8080", '--autoscale_up', '3', '--autoscale_down', '1', '--max_workers', '2', '--queue_tracking_window', '60', '--verbosity', '2', '--metrics_id', '12']
    print(' '.join(command))
    process = subprocess.Popen(command)
    print(f'PID: {process.pid}')

    base_url = "http://localhost:8080"
    test_url = base_url + "/generate"

    # Wait for the server to be ready
    while True:
        try:
            r = requests.get(base_url)
            if r.json()['ready_worker_count'] >=1:
                break
            else:
                time.sleep(10)
        except:
            time.sleep(10)


    with open('examples/server_test_tgi_generate.json', "r") as f:
        payload = json.load(f)

    # Apply load to the server and check if it scales up and down
    try:
        r = requests.post(test_url, json=payload)
        assert r.status_code == 200

        apply_load(test_url, payload)

        i =0
        scale_up_success = False
        while i < 10:
            r = requests.get(base_url)
            if r.json()['ready_worker_count'] > 1:
                scale_up_success = True
                break
            else:
                time.sleep(10)
                i += 1

        assert scale_up_success, "Expected more than one worker to be running after load test."

        i =0
        scale_down_success = False
        while i < 20:
            r = requests.get(base_url)
            if r.json()['ready_worker_count'] == 1:
                scale_down_success =  True
                break
            else:
                time.sleep(30)
                i += 1

        assert scale_down_success, "Expected only one worker to be running after a while load is cut"


    except Exception as e:
        print(f'Error: {e}')

    # Clean up
    finally:
        subprocess.Popen(["kill", "-9", f"{process.pid}"])
        clusters = sky.status()
        [sky.down(cluster_name=cluster['name'], purge=True) for cluster in clusters]


def test_manual_scaling():
    command = ["flockserve", "--skypilot_task", "examples/serving_tgi_cpu_generate.yaml",  "--port", "8080", "--node_control_key", "tmp123", '--verbosity', '2', '--metrics_id', '-1']
    process = subprocess.Popen(command)
    print(f'PID: {process.pid}')

    base_url = "http://localhost:8080"
    test_url = base_url + "/generate"


    with open('examples/server_test_tgi_generate.json', "r") as f:
        payload = json.load(f)

    try:
        r = requests.post(test_url, json=payload)
        assert r.status_code == 200
    except Exception as e:
        print(f'Error: {e}')

    r = requests.get("http://localhost:8080/add_new_node", headers={"node_control_key":"tmp123"})
    r = requests.get("http://localhost:8080/")
    r = requests.get("http://localhost:8080/health")





if __name__ =="__main__":
    test_flockserve()