import os
import queue
from flask import Flask, request, jsonify
from flask_cors import CORS
import saspy
import uuid
import time
import multiprocessing
import sys
import logging
import threading

# build docker image:
# docker build -t <docker_account_name>/<image_name>:1.1 .

# run docker container
# docker run -p 8000:8000 <docker_account_name>/<image_name>:1.1

app = Flask(__name__)

app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.INFO)

CORS(app)

#This is a multiprocessing queue and result dictonary
# We need the multiprocessing type as it is share and accessible among different processes
command_queue = multiprocessing.Queue()
manager = multiprocessing.Manager()
results_dict = manager.dict()

def worker(command_queue, result_dict):
    now = time.time()
    app.logger.info(f"Worker started at {now}")
    sas_session = saspy.SASsession()
    app.logger.info("Created SAS session for process")
    while True:
        try:
            try:
                #If no message is receive in 5 seconds then check in the except block if the sas session needs refreshing
                task_id, command, args, kwargs = command_queue.get(timeout=5)
                sas_session, result, retries = command(*args, **kwargs, sas_session=sas_session)
                result_dict[task_id] = (result, retries)
            except queue.Empty:
                # Check if it's time to restart as there is a high chance the connection is lost if we don't do this
                if time.time() - now > 280:
                    app.logger.info("Refreshing SAS session...")
                    try:
                        sas_session.endsas()
                    except:
                        pass
                    sas_session = saspy.SASsession()
                    now = time.time()
                    time.sleep(1)
        except Exception as e:
            #If we end up in here it means that the sas request faild after multiple retries
            result_dict[task_id] = (f"Failed to get SAS results for query param after multiple retries...", 3)
            raise e

def start_worker_process(task_queue, result_dict):
    app.logger.info("Starting up worker...")
    p = multiprocessing.Process(target=worker, args=(task_queue, result_dict))
    p.start()
    return p

def monitor_and_restart_processes(num_workers, task_queue, result_dict):
    processes = [start_worker_process(task_queue, result_dict) for _ in range(int(num_workers))]
    app.logger.info(f"Starting {num_workers} workers...")
    while True:
        for i, process in enumerate(processes):
            if not process.is_alive():
                # The process was shut down so we need to restart it in order to keep the number of workers alive
                app.logger.warning(f"Restarting process {process.pid} after worker was shut down.")
                processes[i] = start_worker_process(task_queue, result_dict)

        # Implement some delay to prevent this loop from consuming too much CPU
        time.sleep(1)


def sas_submit_call(sas_session, macro, table, libref, result_container):
    try:
        app.logger.info(f'Submitted macro call for table {table}')
        response = sas_session.submit(macro)
        if "SAS process has terminated unexpectedly".lower() in response.get('LOG').lower():
            raise Exception
        app.logger.info(f'SAS session state is: {sas_session}')
        result_df = sas_session.sasdata2dataframe(table=table, libref=libref)
        result_container['data'] = result_df
    except Exception as e:
        result_container['error'] = e


def process_macro_call1(macro, retry=0, sas_session=None):
    try:
        if retry >= 3:
            #If more than 3 retries have been made we want to raise a exception that show us that
            #the SAS server is most likely unreachable at the moment
            raise RuntimeError
        result_container = {}
        sas_thread = threading.Thread(target=sas_submit_call, args=(sas_session, macro, 'available_series', 'work', result_container))
        sas_thread.start()
        sas_thread.join(timeout=int(os.getenv("SAS_REQ_TIMEOUT", 10)))
        if result_container.get('error'):
            raise Exception
        available_series_df = result_container.get('data')
        app.logger.info(f'Result series from macro call 1 is : {available_series_df}')
        dates_available = available_series_df.iloc[0]['begin_year'], available_series_df.iloc[0]['end_year'], available_series_df.iloc[0]['series_id'], available_series_df.iloc[0]['item_code']
    except RuntimeError:
        app.logger.error(f'Could not get data from sas server')
        raise RuntimeError("Failed to connect to SAS server after multiple retries")
    except Exception:
        app.logger.info('SAS session submit timeout or session in a bad state, recreating session...')
        try:
            sas_session.endsas()
        except:
            pass
        return process_macro_call1(macro, retry+1, saspy.SASsession())

    # keep_alive(sas_sessions)
    return sas_session, dates_available, retry


def process_macro_call2(macro, retry=0, sas_session=None):
    try:
        if retry >= 3:
            # If more than 3 retries have been made we want to raise a exception that show us that
            # the SAS server is most likely unreachable at the moment
            raise RuntimeError
        result_container = {}
        sas_thread = threading.Thread(target=sas_submit_call,
                                      args=(sas_session, macro, 'calc_type_data', 'work', result_container))
        sas_thread.start()
        sas_thread.join(timeout=int(os.getenv("SAS_REQ_TIMEOUT", 10)))
        if result_container.get('error'):
            raise Exception
        graph_ready_df = result_container.get('data')
        # Reorder the columns to ensure x-variable comes before 'value'
        if 'value' in graph_ready_df.columns and 'value' != graph_ready_df.columns[-1]:
            cols = [col for col in graph_ready_df.columns if col != 'value'] + ['value']
            graph_ready_df = graph_ready_df[cols]
    except RuntimeError:
        app.logger.error(f'Could not get data from sas server')
        raise RuntimeError("Failed to connect to SAS server after multiple retries")
    except Exception:
        app.logger.info('SAS session submit timeout or session in a bad state, recreating session...')
        try:
            sas_session.endsas()
        except:
            pass
        return process_macro_call2(macro, retry+1, saspy.SASsession())
    return sas_session, graph_ready_df.to_csv(index=False), retry


# We want to wait for the results for the sumbitted request
# We do that by watting to have an entry with the unique ID for the request we submitted
# in our shared result_dict object. Default timeout is 60 sec id we don't get a response we raise an error
def get_results(task_id, timeout=60):
    start_time = time.time()
    while True:
        if task_id in results_dict:
            app.logger.info(f"Task with id of {task_id} retrieved")
            # Retrieve and remove the result from the result dict
            data, retries = results_dict.pop(task_id)
            return {"data": data, "retries": retries}

        if time.time() - start_time > timeout:
            return {"data" : "Result retrieval timed out.", "retries": None}

        time.sleep(0.1)  # Sleep briefly to avoid high CPU usage

@app.route('/',methods=['GET'])
def health_check():
    app.logger.info('Health check endpoint hit!')
    return {"status": "Healthy"}


@app.route('/getAvailableSeries',methods=['POST','GET'])
def get_available_series():
    # get the request arguments
    args = request.args

    results = []

    # read the contents of the file to get the existing macro
    with open('macro1.txt', 'r') as f:
        macro_code = f.read()

    #Make unique ids for each SAS request we are going to make
    task_ids = [uuid.uuid4() for _ in args.keys()]
    # make a macro call for each itemCode user sent in from frontend
    for idx, arg in enumerate(args.keys()):
        item_code = args.get(arg, 'default_value')
        # create a macro call based on the user input
        macro_call = f"%get_available_series('{item_code}');"
        # concatenate the existing macro and macro_call
        macro = macro_code + '\n' + macro_call
        # Use one SAS session per arg # blocks until a session is available
        command_queue.put((task_ids[idx], process_macro_call1, (macro, 0), {}))
        app.logger.info(f"Task with id {task_ids[idx]} submitted")

    results = [get_results(task_id) for task_id in task_ids]
    return jsonify(results)

@app.route('/makeGraphReadyData',methods=['POST','GET'])
def make_graph_ready_data():
    args_dict = {}

    for i in range(1, 6):
        key = str(i)
        if key in request.args:
            start_year, end_year, calc_type, source_file, series_id = request.args.get(key).split(',')
            args_dict[key] = {
                'start_year': start_year,
                'end_year': end_year,
                'calc_type': calc_type,
                'source_file': source_file,
                'series_id': series_id
            }

    csv_dict = {}

    # Make unique ids for each SAS request we are going to make
    task_ids = [uuid.uuid4() for _ in args_dict.keys()]

    for idx, (key, values) in enumerate(args_dict.items()):
        start_year = values['start_year']
        end_year = values['end_year']
        calc_type = values['calc_type']
        source_file = values['source_file']
        series_id = values['series_id']

        macro_call = f"%makeGraphReadyData({start_year}, {end_year}, {calc_type}, {source_file}, {series_id});"

        with open('macro2.txt', 'r') as f:
            macro_code = f.read()

        macro = macro_code + '\n' + macro_call

        # Use one SAS session per key
        command_queue.put((task_ids[idx], process_macro_call2, (macro, 0), {}))
        app.logger.info(f"Task with id {task_ids[idx]} submitted")

    for key, result in zip(args_dict.keys(), [get_results(task_id) for task_id in task_ids]):
            csv_dict[key] = result

    return csv_dict



num_workers = int(os.getenv("NUM_WORKERS", 4))

# Populate the task_queue with tasks...

monitoring_process = multiprocessing.Process(target=monitor_and_restart_processes,
                                             args=(num_workers, command_queue, results_dict))
monitoring_process.start()
