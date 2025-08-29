import json, os, uuid

from datetime import datetime
from typing import List, Optional
from agents import Agent
from pydantic import BaseModel, Field
import asyncio

from custom_runners import CRunner, gemini_2_5_flash_model, gemini_2_5_flash_vertex
import db_ops
import gcs_operation
import config
import time

import patient_reasoning



class RunProcess:
    def __init__(self, process_id):
        self.process_id = process_id

        self.init_patients_data()
        self.patient_pool = []

    def init_patients_data(self):
        
        patient_pool = gcs_operation.read_json_from_gcs(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.process_id}/patient_pool.json")
        for p in patient_pool:
            gcs_operation.write_json_to_gcs(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.process_id}/patients/{p.get('patient_id')}/{p.get('patient_id')}.json", p)


    def run_patients(self):
        patient_list_path = gcs_operation.list_gcs_children(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.process_id}/patients")

        for p_path in patient_list_path[:3]:
            p_json_path = p_path + f"{p_path.split('/')[-2]}.json"
            print("patient json path :", p_json_path)

            p_data = gcs_operation.read_json_from_gcs(p_json_path)

            p_data = patientEnrich(p_data).enrich_ehr()

            time.sleep(3)

            p_data = asyncio.run(patientFlag(p_data).run_flag())

            time.sleep(3)

            p_data = patientEnrich(p_data).add_status(
                {
                    "process" : "retrieve",
                    "source" : "EHR"
                }
            )

            p_data = patient_reasoning.PatientDecom1(p_data)



class patientFlag:
    def __init__(self, patient):
        self.patient = patient
        self.p_json_path = f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.patient.get('process_id')}/patients/{self.patient.get('patient_id')}/{self.patient.get('patient_id')}.json"

    def add_status(self,process_obj):
        if not self.patient.get('status'):
            self.patient['status'] = []
        
        self.patient['status'].append(process_obj)

        gcs_operation.write_json_to_gcs(self.p_json_path, self.patient)

    async def run_flag_agent(self):

        patient_note = ""
        for n in self.patient.get('ehr_note',[]):
            patient_note += f"{n.get('note')}\n\n------\n\n"

        agent_file = "drug_flag.txt"
        with open(f"patient_generation/agents/{agent_file}", "r", encoding="utf-8") as file:
            instructions = file.read()

        agent_ = Agent(
            name="gemini - Flag Check Agent",
            instructions=instructions,
            model=gemini_2_5_flash_vertex,
        )
        class CheckFormat(BaseModel):
            drug_flag: bool = Field(..., description="Drug flag")
            drug_list: List[str] = Field(..., description="List of matched drug")

        prompt = f"Check if the patient using drug in drug watch list.\nPatient note :\n{patient_note}\n\nDrug watch list : {self.patient.get('drug_watch')}"

        res_obj = CRunner(
            agent = agent_,
            prompt = prompt,
            format_output=CheckFormat
        )


        await res_obj.run_async()
        result = res_obj.output
        return result


    async def run_flag(self):
        self.add_status(
            {
                "process":'drug_flag',
                "status":'running',
            }
        )

        q_res = await self.run_flag_agent()
        self.patient.update(q_res)



        self.add_status(
            {
                "process":'drug_flag',
                "status":'finish',
            }
        )
        return self.patient




     

class patientEnrich:
    def __init__(self, patient):
        self.patient = patient
        self.p_json_path = f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.patient.get('process_id')}/patients/{self.patient.get('patient_id')}/{self.patient.get('patient_id')}.json"


    def add_status(self,process_obj):
        if not self.patient.get('status'):
            self.patient['status'] = []
        
        self.patient['status'].append(process_obj)

        gcs_operation.write_json_to_gcs(self.p_json_path, self.patient)
        return self.patient
    

    def enrich_ehr(self):
        bucket_path = self.patient.get('patient_bucket_path')
        if not self.patient.get('ehr_note'):
            self.patient['ehr_note'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                encounter_id = f.split('/')[-1].replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['ehr_note'].append(
                    {
                        "encounter_id" : encounter_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "EHR"
        })
        return self.patient
        

    def enrich_lab(self):
        bucket_path = self.patient.get('patient_bucket_path') + '/labs'
        if not self.patient.get('ehr_note'):
            self.patient['lab_result'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                lab_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['ehr_note'].append(
                    {
                        "lab_id" : lab_id,
                        "note" : note
                    }
                )
        self.add_status({
            "process" : "retrieve",
            "source" : "lab"
        })
        return self.patient
