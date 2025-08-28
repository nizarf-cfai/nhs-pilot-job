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



class RunProcess:
    def __init__(self, process_id):
        self.process_id = process_id

        self.init_patients_data()

    def init_patients_data(self):
        
        patient_pool = gcs_operation.read_json_from_gcs(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.process_id}/patient_pool.json")
        for p in patient_pool:
            gcs_operation.write_json_to_gcs(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.process_id}/patients/{p.get('patient_id')}.json", p)


    def run_patients(self):
        patient_list_path = gcs_operation.list_gcs_children(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.process_id}/patients")
        for p_path in patient_list_path[:3]:
            p_data = gcs_operation.read_json_from_gcs(p_path)

            patientEnrich(p_data).enrich_ehr()

            time.sleep(3)



class patientFlag:
    def __init__(self, process_id, drug_list):
        self.patients_path = "patient_generation/patients"

        if not process_id:
            self.process_id ="process-" + str(uuid.uuid5(uuid.NAMESPACE_DNS, str(datetime.now())))
        else :
            self.process_id = process_id

        self.patient_pool = db_ops.get_dummy_patients_pool()
        self.drug_watch_list = drug_list
        self.query_result = []


    def get_note_patient(self):
        gcs_operation.write_json_to_gcs(f"{config.PROCESS_PATH}/{self.process_id}/patient_pool.json", self.patient_pool)

        for p in self.patient_pool:
            bucket_path = p.get('patient_bucket_path')
            p['notes'] = []
            files = gcs_operation.list_gcs_children(bucket_path)
            for f in files:
                if '.txt' in f:
                    encounter_id = f.split('/').replace('.txt','')
                    note = gcs_operation.read_text_from_gcs(f)
                    p['notes'].append(
                        {
                            "encounter_id" : encounter_id,
                            "note" : note
                        }
                    )

    async def run_flag_agent(self, patient_note):



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

        prompt = f"Check if the patient using drug in drug watch list.\nPatient note :\n{patient_note}\n\nDrug watch list : {self.drug_watch_list}"

        res_obj = CRunner(
            agent = agent_,
            prompt = prompt,
            format_output=CheckFormat
        )


        await res_obj.run_async()
        result = res_obj.output
        return result


    async def run_flag(self):

        for p in self.patient_pool:
            q_res = await self.run_flag_agent(p.get('note',''))
            p.update(q_res)
            # q_res['patient_id'] = p.get('patient_id')
            # self.query_result.append(
            #     q_res
            # )


        gcs_operation.write_json_to_gcs(f"{config.PROCESS_PATH}/{self.process_id}/patient_flag_res.json", self.patient_pool)



        with open(f"{self.output_path}/process_result.json", "w") as f:
            json.dump(self.query_result, f, indent=4)
            
        # enrich = patientEnrich(self.process_id, self.patient_pool)
        # enrich.enrich1()

        print(self.process_id)

        return self.process_id

     

class patientEnrich:
    def __init__(self, patient):
        self.patient = patient

    def add_status(self,process_obj):
        if not self.patient.get('status'):
            self.patient['status'] = []
        
        self.patient['status'].append(process_obj)

        gcs_operation.write_json_to_gcs(f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.patient.get('process_id')}/patients/{self.patient.get('patient_id')}.json", self.patient)

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
        

    def enrich_lab(self):
        bucket_path = self.patient.get('patient_bucket_path')
        if not self.patient.get('ehr_note'):
            self.patient['ehr_note'] = []

        files = gcs_operation.list_gcs_children(bucket_path)
        for f in files:
            if '.txt' in f:
                encounter_id = f.split('/').replace('.txt','')
                note = gcs_operation.read_text_from_gcs(f)
                self.patient['ehr_note'].append(
                    {
                        "encounter_id" : encounter_id,
                        "note" : note
                    }
                )
        

