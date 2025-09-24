import asyncio
import sys
import traceback
import gcs_operation
import config
import db_ops   
import requests
from datetime import datetime
import json
import pandas as pd
import uuid
import config
import time
from concurrent.futures import ThreadPoolExecutor
import patient_process
import pairwise
import gcs_operation
import patient_reasoning

# Convert key=value pairs into a dictionary
def parse_key_value_args(args):
    result = {}
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            try:
                # Try parsing as JSON
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                # If not JSON, keep as string
                result[key] = value
    return result

def run_process(args):
    process_batch = patient_process.RunProcess(args.get('process_id'))
    process_batch.run_patients()

def run_pairwise(args):
    pairwise_res = asyncio.run(pairwise.PairwisePatient(args.get('process_id')).run_pairwise())


def process(args):
    process_id = args.get('process_id')
    patient_id = args.get('patient_id')
    query = args.get('query')
    file_path = f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{process_id}/patients/{patient_id}/{patient_id}.json"

    p_data = gcs_operation.read_json_from_gcs(file_path)
    asyncio.run(patient_reasoning.PatientDecom1(p_data)._data_analysis(query))


if __name__ == "__main__":
    try:
        command = sys.argv[1]
        raw_args = sys.argv[2:]
        args = parse_key_value_args(raw_args)

    
        print(f"▶️ Running command: {command} with args: {args}")
        if command == "run_process":
            print("Running process")
            run_process(args)

        elif command == "pairwise":
            run_pairwise(args)

        elif command == "process":
            process(args)

        else:
            print(f"❌ Unknown command: {command}")
            sys.exit(1)
    except Exception:
        err = traceback.print_exc()
        print(err)
        sys.exit(1)
