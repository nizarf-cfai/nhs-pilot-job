import os, json
from pydantic import BaseModel, Field
import asyncio
import copy

from custom_runners import CRunner, gemini_2_5_flash_model, gemini_2_5_flash_vertex
from cognitive_debate import CognitiveDebate
import agent_list
from visualize import AgentGraph
import uuid
from datetime import datetime
from agents import Agent, function_tool, Runner

import config
import gcs_operation

class PatientDecom1:
    def __init__(self, patient):
        self.patient = patient
        self.patient_id = self.patient.get('patient_id')


        self.p_json_path = f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.patient.get('process_id')}/patients/{self.patient.get('patient_id')}/{self.patient.get('patient_id')}.json"

        self.patient_path = f"gs://{config.BUCKET}/{config.PROCESS_PATH}/{self.patient.get('process_id')}/patients/{self.patient.get('patient_id')}"


        self.patient_path = f"patient_generation/patients/{self.patient_id}"
        self.decom_path = f"{self.patient_path}/debate_category"

        os.makedirs(self.decom_path, exist_ok=True)
        self.add_status(
            {
                "process" : 'debate_category',
                'status' : 'runnning'
            }
        )

        self.max_research = 1
        self.question = "Analyze patient condition"

        self.risk_cat = {}
        self.report_path = ""

        self.graph = AgentGraph("Process Graph")
        self.start_node_id = self.graph.add_entry_exit("__start__")

    def add_status(self,process_obj):
        if not self.patient.get('status'):
            self.patient['status'] = []
        
        self.patient['status'].append(process_obj)

        gcs_operation.write_json_to_gcs(self.p_json_path, self.patient)
        return self.patient

    def get_patient_note(self):
        story_str = ""

        for n in self.patient.get('ehr_note'):
            story_str += f"# Encounter\n{n.get('note')}\n\n----\n\n"
        return story_str
    
    async def _get_patient_data(self, patient_note):
        prompt = f"Structurize this patient note.\nPatinent note :\n{patient_note}"
        res_obj = CRunner(
            agent = agent_list.patient_data_agent,
            prompt = prompt,
            format_output=agent_list.PatientData
        )

        await res_obj.run_async()
        res = res_obj.output
        self.patient['patient_data'] = res
        # with open(f"{self.decom_path}/patient_{self.patient_id}.json", "w") as f:
        #     json.dump(res, f, indent=4)

    async def init_question(self, prompt=""):
        res_obj = CRunner(
            agent = agent_list.question_expand_agent,
            prompt = prompt,
            format_output=agent_list.QuestionObject
        )

        await res_obj.run_async()
        res = res_obj.output

        return res

    def collect_debate_outputs(self, data):
        outputs = []

        def recurse(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "debate_output":
                        outputs.append(str(v))  # collect the value
                    recurse(v)
            elif isinstance(obj, list):
                for item in obj:
                    recurse(item)

        recurse(data)
        return "\n\n".join(outputs) 

    async def _assessment(self,step, goal,result):

            
        prompt_ = f"""Assess if the result is covers the step task of main question.\n\n
        This is main question : \n{self.question}\n\n
        
        This is the step task : {step}
        This is the step task goal: {goal}
        
        This is the step result  :\n{result}
        """


        res_obj = CRunner(
            agent = agent_list.assesment_agent,
            prompt = prompt_,
            format_output = agent_list.StepAssesment,
        )

        await res_obj.run_async()
        
        return res_obj
            
            
    async def _task_generator(self, topic,reason):
        agent_ = Agent(
                    name="gemini - Task Gen Agent",
                    instructions="Your goal is to generate task to cover the missing point.",
                    model=gemini_2_5_flash_model,
                )
        
        
        prompt_ = f"""So i have this topic :\n{topic}\n\n
        
        Missing point :\n{reason}\n
        
        Generate tasks to cover the missing point
        """
        
        res_obj = CRunner(
            agent = agent_,
            prompt = prompt_,
            format_output=agent_list.TaskGenerate
        )

        
        await res_obj.run_async()
        
        
        q_res = res_obj.output

        return q_res['tasks']
            
            
    def _add_txt(self,output_dumps, md_path):
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
                
            updated_content = existing_content + "\n\n" + output_dumps
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            return updated_content
        else:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(output_dumps)
            return output_dumps

    def call_ct_agent(self, tools, mode=''):
        agents_participants = []
        
        agent_files = os.listdir('debate_agents')

        for a in agent_files:
            file_path = f"debate_agents/{a}"
            agent_name = a.replace('.txt','')

            with open(file_path, "r", encoding="utf-8") as f:
                system_str = f.read()

            agent_ = Agent(
                name = f"gemini - {agent_name}",
                instructions = system_str,
                tools = tools ,
                model = gemini_2_5_flash_model,
            )
            
            agents_participants.append(agent_)
            
        return agents_participants
    

    async def debate_patient(self):
        print("Start Patient Debate")
        results = []

        patient_story = self.get_patient_note()
        await self._get_patient_data(patient_story)

        print('Patient Story :\n',patient_story[:100])
        print('')

        main_prompt = "Analyze the patient information, diagnose and determine whether there is an indication of liver injury. Consider drug-induced liver injury, underlying liver conditions, comorbidities, and other potential causes."

        analysis_context = f"Patient ID : \n{self.patient_id}\n\nPatient Encounters Note:\n{patient_story}\n\n"

        step_gather = self.graph.add_item(f"Start Decomposition for :\n {self.patient_id}", self.start_node_id, color='purple',style="rounded,filled")
        
        init_obj = await self.init_question(prompt= main_prompt)
            

        for task in init_obj['tasks']:
            task_name = task['task_name']
            
            taks_dir = f"{self.decom_path}/" + task_name.replace(' ','_').lower()
            os.makedirs(taks_dir, exist_ok=True)
            
            debate_res = await self._recursive_decom(task,taks_dir,step_gather, context=analysis_context)
            
            task['debate_result'] = debate_res
            
        
        

        gcs_operation.write_json_to_gcs(f"{self.patient_path}/decomposition_{self.patient_id}.json", init_obj)
        # with open(f"{self.decom_path}/decomposition_{self.patient_id}.json", "w") as f:
        #     json.dump(init_obj, f, indent=4)


        return init_obj

    async def _recursive_decom(self,task, path, parent, level=0, context="", tools=[], mode=''):
        task = copy.deepcopy(task)
        task_name = task['task_name']
        task_goal = task['task_goal']
        
        task_detail = task['task_detail']
        task_prompt = task['task_prompt']
        
        step_task = self.graph.add_item(task_name + "\n" + task_detail, parent)
        debate_agents = self.call_ct_agent(tools=tools, mode=mode)
        
        prompt  = f"""This is main question : {self.question}
        This is task : {task_name}
        This is task goal: {task_goal}
        Detail : {task_detail}
        
        
        {task_prompt}
        """
        
        debate_dir = f"{path}/{task_name.lower().replace(' ','_')}"
        os.makedirs(debate_dir, exist_ok=True)
        
        debate = CognitiveDebate(
            # name = f"Explorative - {task_name}",
            name = task_name,
            participants=debate_agents,
            input={
                "main_topic" : self.question,
                "topic" : task_prompt
            },
            prompt = prompt,
            context=context,
            path = debate_dir
        )
        
        await debate.run_async()
        debate_label = f"Explorative Debate - {task_name}\n"
        
        debate_id_ = self.graph.add_item(debate_label, step_task, color='lightyellow')
        
        deb_res = f"{debate.debate_dumps}\n\n"
        
        # all_deb = self._add_txt(deb_res, path)
        
        task['debate_output'] = deb_res
        
        # assessment_obj = await self._assessment(task_name,task_goal, self.token_check(deb_res))
        assessment_obj = await self._assessment(task_name,task_goal, deb_res)
        assessment = assessment_obj.output

        if assessment['assessment']:
            task['branch'] = []
            asssessment_id = self.graph.add_item("Step Assessment", debate_id_, color='lightgreen', style="rounded,filled")
            print(f"Assessment {level}", True)
            
        else:
            print(f"Assessment {level}", False)
            
            assessment_id = self.graph.add_item("Step Assessment", debate_id_, color='pink', style="rounded,filled")
            
            new_tasks = await self._task_generator(task_name, assessment.get('reasoning'))
            if level < self.max_research :

                tasks = []

                for task_ in new_tasks:
                    task_sync = asyncio.create_task(
                        self._recursive_decom(
                            task=task_, 
                            path=path,
                            parent=assessment_id,
                            level=level+1,
                            context=context,
                            tools=tools,
                            mode=mode
                        )
                    )
                    tasks.append(task_sync)

                branch_result = await asyncio.gather(*tasks)
                task['branch'] = branch_result
        return task
    
    async def _get_risk_category(self):
        doc_str = gcs_operation.read_text_from_gcs(f"{self.patient_path}/debate_category_doc_{self.patient_id}.txt")

        # with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt", "r", encoding="utf-8") as f:
        #     doc_str = f.read()


        prompt = f"Extract Liver adverse event risk on this patient diagnosis document.\nDocument :\n{doc_str}"


        res_obj = CRunner(
            agent = agent_list.risk_cat_agent,
            prompt = prompt,
            format_output=agent_list.RiskCheck
        )

        await res_obj.run_async()
        res = res_obj.output
        self.patient['debate_category'] = res
        # with open(f"{self.decom_path}/risk_cat_{self.patient_id}.json", "w") as f:
        #     json.dump(res, f, indent=4)

    async def generate_risk_percentage(self):
        # with open(f"{self.decom_path}/risk_cat_{self.patient_id}.json", "r", encoding="utf-8") as f:
        #     risk_cat = json.load(f)
        risk_cat = self.patient.get('debate_category')
        doc_str = gcs_operation.read_text_from_gcs(f"{self.patient_path}/debate_category_doc_{self.patient_id}.txt")
        # with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt", "r", encoding="utf-8", errors="replace") as file:
        #     doc_str = file.read()

        prompt = f"Calculate risk percentage of this patient having liver adverse event.\nDocument :\n{doc_str}\nRisk level : {risk_cat.get('risk')}\nReasoning :\n{risk_cat.get('reasoning')}\nEvidence :\n{risk_cat.get('evidence')}"

        res_obj = CRunner(
            agent = agent_list.risk_percentage_agent,
            prompt = prompt,
            format_output=agent_list.RiskPercent
        )


        await res_obj.run_async()
        risk_percent = res_obj.output
        self.patient['debate_category']['probability'] = {
            'percentage' : risk_percent.get('percentage'),
            'reasoning' : risk_percent.get('reasoning'),
        }
        # with open(f"{self.decom_path}/risk_percent_{self.patient_id}.json", "w") as f:
        #     json.dump(risk_percent, f, indent=4)

    async def document_generate(self):

        # with open(f"{self.decom_path}/decomposition_{self.patient_id}.json", 'r', encoding='utf-8') as file:
        #     debate_res = json.load(file)
        debate_res = gcs_operation.read_json_from_gcs(f"{self.patient_path}/decomposition_{self.patient_id}.json")
        debate_res_str = self.collect_debate_outputs(debate_res)


        with open("doc_structure/debate_category_structure.json", "r", encoding="utf-8") as f:
            structure_doc = json.load(f)

        doc_context = ""
        doc_res_str = ""

        for sec in structure_doc:
            sec_name = sec.get('section')
            detail_path = sec.get('details_path')

            with open(detail_path, 'r', encoding='utf-8') as file:
                detail_str = file.read()

            prompt = f"""You are a medical diagnosis expert for patient id {self.patient_id}. For the section titled: {sec_name}, generate content for this section with this detail:

            {detail_str}

            This is context of previous section :\n{doc_context}


            This is debate outputs :\n{debate_res_str}


            """

            result = await self.doc_content(prompt, [])
            doc_context += f"{result}\n\n"
            sec['result'] = result

            doc_res_str += f"# {sec_name}\n"
            doc_res_str += f"{result}\n\n"


        gcs_operation.write_json_to_gcs(f"{self.patient_path}/debate_category_doc_{self.patient_id}.json", structure_doc)
        # with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.json", "w") as f:
        #     json.dump(structure_doc, f, indent=4)

        gcs_operation.write_text_to_gcs(f"{self.patient_path}/debate_category_doc_{self.patient_id}.txt", doc_res_str)

        # with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt", "w", encoding="utf-8") as file:
        #     file.write(doc_res_str)

        self.report_path = f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt"

    async def doc_content(self, prompt, tools):
        res_obj = CRunner(
            agent = agent_list.doc_content_agent,
            prompt = prompt,
            tools = tools

        )


        await res_obj.run_async()
        content = res_obj.output

        return content
    

    async def generate_action(self):
        doc_str = gcs_operation.read_text_from_gcs(f"{self.patient_path}/debate_category_doc_{self.patient_id}.txt")
        # with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt", "r", encoding="utf-8", errors="replace") as file:
        #     doc_str = file.read()

        prompt = f"Generate action for this diagnosis analysis document.\nDocument :\n{doc_str}"

        res_obj = CRunner(
            agent = agent_list.action_agent,
            prompt = prompt,
            format_output=agent_list.ActionData
        )


        await res_obj.run_async()
        action = res_obj.output
        action['action_id'] = f"action-{str(uuid.uuid5(uuid.NAMESPACE_DNS, str(datetime.now())))}"
        self.patient['action'] = action

        # with open(f"{self.decom_path}/action_{self.patient_id}.json", "w") as f:
        #     json.dump(action, f, indent=4)

    async def announce_refine(self):
        # with open(f"{self.decom_path}/risk_percent_{self.patient_id}.json", "r", encoding="utf-8") as f:
        #     risk_percent = json.load(f)

        risk_object  =self.patient.get('debate_category')

        # with open(f"{self.decom_path}/action_{self.patient_id}.json", "r", encoding="utf-8") as f:
        #     action = json.load(f)

        action = self.patient.get('action')

        prompt = f"Refine this patient annoucement.\nPatient annoucement : {action.get('patient_announcement')}\nRisk level : {risk_object.get('risk')}\nPercentage : {risk_object.get('probability',{}).get('percentage')}\nReasoning : {risk_object.get('probability',{}).get('reasoning')}"

        res_obj = CRunner(
            agent = agent_list.annouce_agent_refine,
            prompt = prompt,
        )


        await res_obj.run_async()
        annouce = res_obj.output
        self.patient['action']['patient_announcement'] = annouce

        # action['patient_announcement'] = annouce
        # with open(f"{self.decom_path}/annouce_doc_{self.patient_id}.txt", "w", encoding="utf-8") as file:
        #     file.write(annouce)


        # with open(f"{self.decom_path}/action_{self.patient_id}.json", "w") as f:
        #     json.dump(action, f, indent=4)


    def action_track(self):
        self.patient['action_tracking'] = {
            "action_id" : self.patient.get('action',{}).get('action_id'),
            "actions" : [
                {
                    "patient_id" : self.patient.get('patient_id'),
                    "action": "patient_annoucement",
                    "status" : "sent"
                },
                {
                    "patient_id" : self.patient.get('patient_id'),
                    "action": "doctor_annoucement",
                    "status" : "sent"
                },
                {
                    "patient_id" : self.patient.get('patient_id'),
                    "action": "patient_response",
                    "status" : "pending"
                },
                {
                    "patient_id" : self.patient.get('patient_id'),
                    "action": "doctor_response",
                    "status" : "pending"
                }
            ]
        }

    async def run(self):
        self.add_status(
            {"process" : "debate_category",
            "status" : "running"}
        )
        await self.debate_patient()
        await self.document_generate()
        await self._get_risk_category()

        await self.generate_risk_percentage()

        self.add_status(
            {"process" : "debate_category",
            "status" : "finish"}
        )

        return self.patient
    
    async def get_action(self):
        self.add_status(
            {"process" : "debate_reasoning",
            "status" : "running"}
        )

        await self.generate_action()
        await self.announce_refine()
        self.action_track()

        self.add_status(
            {"process" : "debate_reasoning",
            "status" : "finish"}
        )

        return self.patient





class PatientDecom2:
    def __init__(self, patient_id):
        self.patient_id = patient_id
        self.patient_path = f"patient_generation/dummy_patients/{self.patient_id}"
        self.decom_path = f"{self.patient_path}/debate1"

        os.makedirs(self.decom_path, exist_ok=True)


        self.max_research = 1
        self.question = "Analyze patient condition"

        self.graph = AgentGraph("Process Graph")
        self.start_node_id = self.graph.add_entry_exit("__start__")

    def get_patient_note(self):
        story_str = ""
        story_paths = [i for i in os.listdir(self.patient_path) if '.txt' in i]
        for path in story_paths:
            with open(f"{self.patient_path}/{path}", "r", encoding="utf-8", errors="replace") as file:
                story_ = file.read()

            story_str += f"{story_}\n\n"
        return story_str
    

    async def init_question(self, prompt=""):
        res_obj = CRunner(
            agent = agent_list.question_expand_agent,
            prompt = prompt,
            format_output=agent_list.QuestionObject
        )

        await res_obj.run_async()
        res = res_obj.output

        return res

    def collect_debate_outputs(self, data):
        outputs = []

        def recurse(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "debate_output":
                        outputs.append(str(v))  # collect the value
                    recurse(v)
            elif isinstance(obj, list):
                for item in obj:
                    recurse(item)

        recurse(data)
        return "\n\n".join(outputs) 

    async def _assessment(self,step, goal,result):

            
        prompt_ = f"""Assess if the result is covers the step task of main question.\n\n
        This is main question : \n{self.question}\n\n
        
        This is the step task : {step}
        This is the step task goal: {goal}
        
        This is the step result  :\n{result}
        """


        res_obj = CRunner(
            agent = agent_list.assesment_agent,
            prompt = prompt_,
            format_output = agent_list.StepAssesment,
        )

        await res_obj.run_async()
        
        return res_obj
            
            
    async def _task_generator(self, topic,reason):
        agent_ = Agent(
                    name="gemini - Task Gen Agent",
                    instructions="Your goal is to generate task to cover the missing point.",
                    model=gemini_2_5_flash_model,
                )
        
        
        prompt_ = f"""So i have this topic :\n{topic}\n\n
        
        Missing point :\n{reason}\n
        
        Generate tasks to cover the missing point
        """
        
        res_obj = CRunner(
            agent = agent_,
            prompt = prompt_,
            format_output=agent_list.TaskGenerate
        )

        
        await res_obj.run_async()
        
        
        q_res = res_obj.output

        return q_res['tasks']
            
            
    def _add_txt(self,output_dumps, md_path):
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
                
            updated_content = existing_content + "\n\n" + output_dumps
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            return updated_content
        else:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(output_dumps)
            return output_dumps

    def call_ct_agent(self, tools, mode=''):
        agents_participants = []
        
        agent_files = os.listdir('debate_agents')

        for a in agent_files:
            file_path = f"debate_agents/{a}"
            agent_name = a.replace('.txt','')

            with open(file_path, "r", encoding="utf-8") as f:
                system_str = f.read()

            agent_ = Agent(
                name = f"gemini - {agent_name}",
                instructions = system_str,
                tools = tools ,
                model = gemini_2_5_flash_model,
            )
            
            agents_participants.append(agent_)
            
        return agents_participants
    
    def call_adversarial_agent(self, tools=[]):
        agents_participants = []
        
        agent_files = os.listdir('adversarial_agents')

        for a in agent_files:
            file_path = f"adversarial_agents/{a}"
            agent_name = a.replace('.txt','')

            with open(file_path, "r", encoding="utf-8") as f:
                system_str = f.read()

            agent_ = Agent(
                name = f"gemini - {agent_name}",
                instructions = system_str,
                tools = tools ,
                model = gemini_2_5_flash_model,
            )
            
            agents_participants.append(agent_)
            
        return agents_participants

    async def debate_patient(self):
        print("Start Patient Debate")
        results = []

        patient_story = self.get_patient_note()
        print('Patient Story :\n',patient_story[:100])
        print('')

        main_prompt = "Analyze the patient information, diagnose and determine whether there is an indication of liver injury. Consider drug-induced liver injury, underlying liver conditions, comorbidities, and other potential causes."

        analysis_context = f"Patient ID : \n{self.patient_id}\n\nPatient Encounters Note:\n{patient_story}\n\n"

        step_gather = self.graph.add_item(f"Start Decomposition for :\n {self.patient_id}", self.start_node_id, color='purple',style="rounded,filled")
        
        init_obj = await self.init_question(prompt= main_prompt)
            

        for task in init_obj['tasks']:
            task_name = task['task_name']
            
            taks_dir = f"{self.decom_path}/" + task_name.replace(' ','_').lower()
            os.makedirs(taks_dir, exist_ok=True)
            
            debate_res = await self._recursive_decom(task,taks_dir,step_gather, context=analysis_context)
            
            task['debate_result'] = debate_res
            
        
        

            
        with open(f"{self.decom_path}/decomposition_{self.patient_id}.json", "w") as f:
            json.dump(init_obj, f, indent=4)


        return init_obj

    async def _recursive_decom(self,task, path, parent, level=0, context="", tools=[], mode=''):
        task = copy.deepcopy(task)
        task_name = task['task_name']
        task_goal = task['task_goal']
        
        task_detail = task['task_detail']
        task_prompt = task['task_prompt']
        
        step_task = self.graph.add_item(task_name + "\n" + task_detail, parent)
        debate_agents = self.call_ct_agent(tools=tools, mode=mode)
        
        prompt  = f"""This is main question : {self.question}
        This is task : {task_name}
        This is task goal: {task_goal}
        Detail : {task_detail}
        
        
        {task_prompt}
        """
        
        debate_dir = f"{path}/{task_name.lower().replace(' ','_')}"
        os.makedirs(debate_dir, exist_ok=True)
        
        debate = CognitiveDebate(
            # name = f"Explorative - {task_name}",
            name = task_name,
            participants=debate_agents,
            input={
                "main_topic" : self.question,
                "topic" : task_prompt
            },
            prompt = prompt,
            context=context,
            path = debate_dir
        )
        
        await debate.run_async()
        debate_label = f"Explorative Debate - {task_name}\n"
        
        debate_id_ = self.graph.add_item(debate_label, step_task, color='lightyellow')
        
        deb_res = f"{debate.debate_dumps}\n\n"
        
        # all_deb = self._add_txt(deb_res, path)
        
        task['debate_output'] = deb_res
        
        # assessment_obj = await self._assessment(task_name,task_goal, self.token_check(deb_res))
        assessment_obj = await self._assessment(task_name,task_goal, deb_res)
        assessment = assessment_obj.output

        if assessment['assessment']:
            task['branch'] = []
            asssessment_id = self.graph.add_item("Step Assessment", debate_id_, color='lightgreen', style="rounded,filled")
            print(f"Assessment {level}", True)
            
        else:
            print(f"Assessment {level}", False)
            
            assessment_id = self.graph.add_item("Step Assessment", debate_id_, color='pink', style="rounded,filled")
            
            new_tasks = await self._task_generator(task_name, assessment.get('reasoning'))
            if level < self.max_research :

                tasks = []

                for task_ in new_tasks:
                    task_sync = asyncio.create_task(
                        self._recursive_decom(
                            task=task_, 
                            path=path,
                            parent=assessment_id,
                            level=level+1,
                            context=context,
                            tools=tools,
                            mode=mode
                        )
                    )
                    tasks.append(task_sync)

                branch_result = await asyncio.gather(*tasks)
                task['branch'] = branch_result
        return task
    
    async def _get_adversarial(self, debate_output):

        adversarial_agent = self.call_adversarial_agent()
        adversarial_str = ""


        for agent_ in adversarial_agent:
            res_obj = CRunner(
                agent = agent_,
                prompt = f"Do adversarial for this debate output.\nDebate output :\n{debate_output}",
            )

            await res_obj.run_async()

            adversarial_str += f"{res_obj.output}\n\n"

        return adversarial_str

    async def adversarial(self):
        with open(f"{self.decom_path}/decomposition_{self.patient_id}.json", 'r', encoding='utf-8') as file:
            debate_res = json.load(file)

        debate_agents = self.call_ct_agent(tools=[], mode='')
        taks_dir = f"{self.decom_path}/adversarial"
        os.makedirs(taks_dir, exist_ok=True)

        results = []

        for t in debate_res.get('tasks'):
            deb = t.get('debate_result')
            if deb:
                debate_output = deb.get('debate_output')

                adversarial_str = await self._get_adversarial(debate_output)

                prompt  = f"""This is main question : {self.question}
                This is task : {deb.get('task_name')}
                This is task goal: {deb.get('task_goal')}
                Detail : {deb.get('task_detail')}    
                Prompt : {deb.get('task_prompt')}

                Debate output : {debate_output}


                Please do adversarial on the debate output
                """

                debate = CognitiveDebate(
                    # name = f"Explorative - {task_name}",
                    name = deb.get('task_name'),
                    participants=debate_agents,
                    input={
                        "main_topic" : self.question,
                        "topic" : ""
                    },
                    prompt = prompt,
                    context=f"Debate output :\n{debate_output}",
                    path = taks_dir
                )
                await debate.run_async()


                deb['adversarial'] = f"{debate.debate_dumps}\n\n"

                results.append(deb)

        with open(f"{self.decom_path}/adversarial_{self.patient_id}.json", "w") as f:
            json.dump(results, f, indent=4)



    async def document_generate(self):
        with open(f"{self.decom_path}/decomposition_{self.patient_id}.json", 'r', encoding='utf-8') as file:
            debate_res = json.load(file)

        debate_res_str = self.collect_debate_outputs(debate_res)


        with open("debate1_doc.json", "r", encoding="utf-8") as f:
            structure_doc = json.load(f)

        doc_context = ""
        doc_res_str = ""

        for sec in structure_doc:
            sec_name = sec.get('section')
            detail_path = sec.get('details_path')

            with open(detail_path, 'r', encoding='utf-8') as file:
                detail_str = file.read()

            prompt = f"""You are a medical diagnosis expert for patient id {self.patient_id}. For the section titled: {sec_name}, generate content for this section with this detail:

            {detail_str}

            This is context of previous section :\n{doc_context}


            This is debate outputs :\n{debate_res_str}


            """

            result = await self.doc_content(prompt, [])
            doc_context += f"{result}\n\n"
            sec['result'] = result

            doc_res_str += f"# {sec_name}\n"
            doc_res_str += f"{result}\n\n"

        with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.json", "w") as f:
            json.dump(structure_doc, f, indent=4)

        with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt", "w", encoding="utf-8") as file:
            file.write(doc_res_str)

    async def doc_content(self, prompt, tools):
        res_obj = CRunner(
            agent = agent_list.doc_content_agent,
            prompt = prompt,
            tools = tools

        )


        await res_obj.run_async()
        content = res_obj.output

        return content
    
    async def generate_risk_percentage(self):
        with open(f"{self.decom_path}/risk_cat_{self.patient_id}.json", "r", encoding="utf-8") as f:
            risk_cat = json.load(f)
        
        with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt", "r", encoding="utf-8", errors="replace") as file:
            doc_str = file.read()

        prompt = f"Calculate risk percentage of this patient having liver adverse event.\nDocument :\n{doc_str}\nRisk level : {risk_cat.get('risk')}\nReasoning :\n{risk_cat.get('reasoning')}\nEvidence :\n{risk_cat.get('evidence')}"

        res_obj = CRunner(
            agent = agent_list.risk_percentage_agent,
            prompt = prompt,
            format_output=agent_list.RiskPercent
        )


        await res_obj.run_async()
        risk_percent = res_obj.output
        with open(f"{self.decom_path}/risk_percent_{self.patient_id}.json", "w") as f:
            json.dump(risk_percent, f, indent=4)

    async def generate_action(self):

        with open(f"{self.decom_path}/diagnosis_doc_{self.patient_id}.txt", "r", encoding="utf-8", errors="replace") as file:
            doc_str = file.read()

        prompt = f"Generate action for this diagnosis analysis document.\nDocument :\n{doc_str}"

        res_obj = CRunner(
            agent = agent_list.action_agent,
            prompt = prompt,
            format_output=agent_list.ActionData
        )


        await res_obj.run_async()
        action = res_obj.output
        with open(f"{self.decom_path}/action_{self.patient_id}.json", "w") as f:
            json.dump(action, f, indent=4)


    async def announce_refine(self):
        with open(f"{self.decom_path}/risk_percent_{self.patient_id}.json", "r", encoding="utf-8") as f:
            risk_percent = json.load(f)


        with open(f"{self.decom_path}/action_{self.patient_id}.json", "r", encoding="utf-8") as f:
            action = json.load(f)

        prompt = f"Refine this patient annoucement.\nPatient annoucement : {action.get('patient_announcement')}\nRisk level : {risk_percent.get('risk_level')}\nPercentage : {risk_percent.get('percentage')}\nReasoning : {risk_percent.get('reasoning')}"

        res_obj = CRunner(
            agent = agent_list.annouce_agent_refine,
            prompt = prompt,
        )


        await res_obj.run_async()
        annouce = res_obj.output
        action['patient_announcement'] = annouce
        # with open(f"{self.decom_path}/annouce_doc_{self.patient_id}.txt", "w", encoding="utf-8") as file:
        #     file.write(annouce)


        with open(f"{self.decom_path}/action_{self.patient_id}.json", "w") as f:
            json.dump(action, f, indent=4)


    async def run(self):
        # await self.debate_patient()
        # await self.document_generate()
        await self.generate_action()
        await self.generate_risk_percentage()
        await self.announce_refine()
        