import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from agents import Agent,  Runner, ModelSettings, WebSearchTool
from copy import deepcopy
import uuid
import re
from fw.custom_runners import CRunner
import asyncio
import copy


class CognitiveDebate:
    def __init__(
        self,
        name = '',
        participants = [],
        cycle = 1,
        input = {
                "main_topic" : "",
                "topic" : ""
            },
        context = "",
        prompt = "",
        path = ""
        ):
        self.prompt = prompt
        self.context = context
        self.participants = participants
        self.cycle = cycle
        self.input = input
        self.name = name if name != '' else "Cognitive Debate" + f" - {self.input.get('topic')[:10]}"
        self.debate_id = self._debate_id(self.name)
        self.debate_dumps = ""
        self.debate_op = []
        self.summary_result = ""
        self.cognitive_perspective_path = "cognitive_perspective.json"
        try:
            with open(self.cognitive_perspective_path, "r") as file:
                self.cognitive_perspective = json.load(file)
        except:
            self.cognitive_perspective = {}
            

        self.extracted_topics = {}
        self.relative_quantify = {}
        self.path = path
        
    def _debate_id(self, name: str) -> str:
        # Convert to lowercase, replace spaces with underscores
        slug = re.sub(r'\W+', '_', name.lower()).strip('_')
        
        # Add short UUID (first 4–6 chars)
        short_uuid = uuid.uuid4().hex[:4]
        
        return f"{slug}_{short_uuid}"
        
    def _run_agent(self, input):
        
        agent_ = input[0]
        mode = input[1]
        perspective = input[2]
        
        prompt = f"""This is main topic : {self.input.get('main_topic')}
                This is target topic : {self.input.get('topic')}
                
                Your goal is to explain target topic in context of main topic, with this perspective :
                {perspective}
                
                In your result you must give reasoning why you generate this result in context of the target topic and main topic.
                
                """
                
        # agent_r = deepcopy(agent_)
        agent_r = copy.copy(agent_)
        agent_r.name = "gemini - " + self.name + " - " +agent_r.name + f" - {mode}"
        res_obj = CRunner(
            agent = agent_r,
            prompt = prompt,

        )
        res_obj.run()
        return res_obj


    async def _run_com(self, input):
        agent_ = input[0]
        mode = input[1]
        perspective = input[2]
        
        prompt = self.prompt + f"""
                Context : \n{self.context}\n\n

                Answer with this perspective : \n{perspective}
                """
                
        # agent_r = deepcopy(agent_)
        agent_r = copy.copy(agent_)
        agent_r.name = "gemini - " + self.name + " - " + agent_r.name + f" - {mode}"
        res_obj = CRunner(
            agent = agent_r,
            prompt = prompt,
            # running_debug=False
        )
        await res_obj.run_async()
        return {
            "agent" : agent_r.name,
            "mode" : mode,
            "perspective" : perspective,
            "output" : res_obj.output
        }

    async def _run_all(self,task_list):
        loop = asyncio.get_running_loop()
        tasks = [loop.create_task(self._run_com(name)) for name in task_list]

        # Wait for all to finish and collect results
        results = await asyncio.gather(*tasks)

        # print("\n📦 All tasks completed. Results:")
        for res in results:
            # deb_res = res.output
            deb_op = f"# Debate answer {res['agent']}:\n\n" + res['output'] + "\n\n--------\n\n"
            
            with open(f"{self.path}/{res['agent']}.txt", "w", encoding="utf-8") as f:
                f.write(deb_op)
                
            self.debate_dumps += deb_op
            self.debate_op.append(
                res
            )

    
    async def _run_participant_async(self):
        count = 1
        args = []
        for _ in range(self.cycle):
            # for k, pers in self.cognitive_perspective.items():
            #     for ag in self.participants:
            #         args.append((ag, k, pers))
            for ag in self.participants:
                args.append((ag, "", ""))
                    
        await self._run_all(args)
    
    def _run_participant(self):
        count = 1
        for _ in range(self.cycle):

            args = []
            for k, pers in self.cognitive_perspective.items():
                for ag in self.participants:
                    args.append((ag, k, pers))
                    
                    
            # for k, pers in self.cognitive_perspective.items():
            #     for ag in self.participants:
            #         args.append((ag, k, pers))
                    

            asyncio.run(self._run_all(args))



    def run(self):
        start_time = time.time()
        last_agent_id = self._run_participant()
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"Debate execution time: {execution_time:.6f} seconds")
        

        
        return {
            "debates_op" : self.debate_dumps,
            "summary" : self.summary_result
        }
        
    async def run_async(self):
        start_time = time.time()
        # last_agent_id = self._run_participant()
        try:
            # print("participant type",type(self.participants))
            await self._run_participant_async()
        

        except Exception as e:
            print("CDebate",self.name," :  ", e)
            import traceback; traceback.print_exc();
        
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"Debate execution time: {execution_time:.6f} seconds")

        
        return {
            "debates_op" : self.debate_dumps,
            "summary" : self.summary_result
        }
        


