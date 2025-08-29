from agents import Agent,  Runner, ModelSettings, WebSearchTool
from dotenv import load_dotenv

import os
from typing import List, Optional
from langchain.schema import Document
from agents import function_tool

from langchain_community.document_loaders import PyPDFLoader, UnstructuredWordDocumentLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field
from langchain.schema import Document
import ast
from copy import deepcopy
import json
from custom_runners import gemini_2_5_flash_model



question_expand_system = """You are a high-level task expansion agent. Your job is to **analyze a user question or request**, then break it down into structured components for execution and research.

Your output must include:

---

**1. Goal**

* A high-level statement of what the user ultimately wants to achieve.

**2. Objectives**

* 2–5 measurable or concrete milestones that contribute to the goal.

**3. Tasks**
For each task, provide the following:

* **Task Name**: A short, clear label.
* **Task Detail**: A detailed description of what the task involves.
* **Prompt for Research**: A well-formulated research or AI prompt that could help someone perform or explore this task further, elicit explanations, data, evidence, analogies, or frameworks to support decision-making or insight related to this task.

---

**Rules & Behavior:**

* Do **not** answer the question directly.
* Focus on **structuring** the request into actionable and researchable elements.
* Anticipate missing information and reflect that in your prompts.
* Use professional, organized formatting (Markdown preferred unless specified).
"""


question_expand_agent = Agent(
    name="gemini - Question Agent",
    instructions=question_expand_system,
    model=gemini_2_5_flash_model,
)

class TaskItem(BaseModel):
	task_name: str = Field(..., description="Name of the task.")
	task_detail : str = Field(..., description="Detail of the task")
	task_goal : str = Field(..., description="Goal of the task")
	task_prompt : str = Field(..., description="Prompt of the task")

class QuestionObject(BaseModel):
	main_goal : str
	objective : str
	tasks : List[TaskItem]

class TaskGenerate(BaseModel):
	tasks : List[TaskItem]
	

assesment_agent_system = """You are the Assessment Agent in a multi-agent AI system. Your responsibility is to evaluate whether a given result or output fully satisfies the expectations of the assigned topic or task.

You must:

1. Carefully review the topic or task description provided.
2. Examine the result that has been produced in response.
3. Determine whether the result:
   - Fully addresses the topic or task
   - Contains all expected elements or sections
   - Is accurate, coherent, and aligned with the goal
   - Avoids off-topic or redundant content
4. If the result is incomplete, vague, or misaligned, clearly explain why.
5. Provide a structured output that includes:
   - Fulfilled: Yes/No
   - Missing Elements: (if any, provide reasoning)


Be objective and constructive. Your role is not to rewrite the output, but to identify whether it meets expectations and guide next steps if it doesn’t. 


"""
assesment_agent = Agent(
   name="geminin - Step Assesment Agent",
   instructions=assesment_agent_system,
   tools=[],
   model=gemini_2_5_flash_model,
)
class StepAssesment(BaseModel):
   assessment: bool = Field(..., description="Assessment result True if fully addres the topic False if still missing points")
   reasoning: str = Field(..., description="Reasoning of missing element, data, points, etc.")
   



doc_content_system = """You are **StructuredContentGeneratorAgent**, a specialized agent in generating **well-structured, evidence-based content** from clinical and scientific debates. Your outputs must focus on **hard data**, **trial results**, and **measurable outcomes**, not opinions or general statements.

---

### 📦 **You Are Provided With:**
* Diagnostic debates from agents.
* A **target section**.
* Access to a **retrieval tools** that searches structured multi-agent debate transcripts containing clinical data, trial results, research result, and expert claims.
* Context of previous section

---

### 🎯 **Your Responsibilities:** 

#### 1. **Interpret the Structure**

* Understand the **exact analytical goal** of the section based on the heading and description.
* Identify expected **data types**: e.g., response rates, survival curves, adverse event rates, endpoint success rates, statistical significance, etc.

#### 2. **Retrieve High-Quality Evidence**

* Use additional document context if help.

#### 3. **Generate Grounded Analytical Diagnosis Content**

* Base all claims and analysis on **retrieved excerpts only**.

#### 4. **Cite with Precision**
* Cite at end of the content, do not in line
* Maximum 5 citation

---

### 📌 **Strict Output Rules:**
* Provide output in structured text.
* ✅ **Use only retrieved content** — no fabrication, assumptions, or paraphrased general knowledge.
* ✅ **Prioritize data-driven language** — focus on real-world results, clinical statistics, and grounded comparisons.
* ✅ **Cite every factual point** — each claim must link to an identifiable quote.
* ❌ Avoid vague or speculative language.
* ❌ Do not write summaries or general explanations without data support.




"""


doc_content_agent = Agent(
	name="Document Content Agent",
	instructions=doc_content_system,
	model=gemini_2_5_flash_model,
   # model_settings=ModelSettings(temperature=0.1, tool_choice="required"),
   # tools = [WebSearchTool(search_context_size='low')]
)


stage1_check_system = """
You are a **medical data assistant** specialized in analyzing **patient medical stories** to identify potential **liver adverse events (AE)**.

### **Input:**

* A general medical story or summary of a fictional patient
* Includes history of medications, lab tests, symptoms, and any clinical encounters

### **Task:**

* Review the provided patient story
* Determine if there is a **potential liver adverse event**
* Provide a concise **reasoning statement** explaining your conclusion

### **Output Requirements:**

Return a **JSON object** with the following fields:

1. **stage\_1\_check**: Boolean (`true` if the patient shows potential signs of liver AE, `false` otherwise)
2. **reason**: String explaining **why the patient was flagged or not**, referencing:

   * Abnormal liver lab values (ALT, AST, ALP, bilirubin, GGT, etc.)
   * Relevant medication history (hepatotoxic drugs, chronic use, overdoses)
   * Relevant symptoms (fatigue, abdominal discomfort, jaundice, etc.)
   * Patterns over multiple encounters if mentioned

### **Rules & Guidance:**

1. Use **clinical reasoning**, considering trends in labs, medications, and symptoms.
2. Be **conservative**: only flag if there is **plausible evidence** from the story.
3. **Do not invent new patient details**; use only the information provided in the story.
4. Keep the **reason concise but specific**, explaining which factors influenced your judgment.
5. The output **must be valid JSON** with exactly the fields `stage_1_check` and `reason`.

### **Example Input:**

```
Patient is a 55-year-old with rheumatoid arthritis on methotrexate and leflunomide. Over the past year, ALT, AST, and ALP tests have been elevated in the last two encounters. Bilirubin remains normal. The patient reports mild fatigue and occasional abdominal discomfort.
```

### **Example Output:**

```json
{
  "stage_1_check": true,
  "reason": "Elevated ALT, AST, and ALP over multiple encounters in a patient on methotrexate and leflunomide suggest potential hepatotoxicity."
}
```


"""


stage1_check_agent = Agent(
	name="Stage 1 Check Agent",
	instructions=stage1_check_system,
	model=gemini_2_5_flash_model,
   # model_settings=ModelSettings(temperature=0.1, tool_choice="required"),
   # tools = [WebSearchTool(search_context_size='low')]
)


class Stage1Check(BaseModel):
   stage_1_check: bool = Field(..., description="Check result")
   reason: str = Field(..., description="Reasoning of the check result.")
   


risk_category_system = """
You are an expert clinical reasoning assistant.
You will be given a structured analysis document about a single patient (sections may include: Patient Information, Initial Observations, Differential Diagnosis, Risk Stratification, Agent Perspectives, Consensus, Recommendations, and Liver Adverse Event Risk).

**Your task:** Identify the patient’s **Liver Adverse Event (LAE) Risk level**, provide a **brief reasoning**, and list the **supporting evidence**.

---

### Rules

1. **Primary source of truth:** If present, use **Section 8: Liver Adverse Event Risk**.
2. **Fallback order if Section 8 is missing/empty:**

   * Section 6: **Consensus (Post-Debate)**
   * Section 4: **Risk Stratification**
   * Otherwise, derive from Sections 1–3 + Agent Perspectives, using explicit evidence only.
3. **Allowed risk levels:** `"low"`, `"medium"`, `"high"`.
   If the document lacks sufficient evidence to decide, return `"low"`.
4. **Reasoning requirements:**

   * Provide a concise **paragraph** summarizing why the risk level was chosen.
   * Highlight how the evidence supports the conclusion, referencing **symptoms/signs**, **drug exposures + timing**, **lab values if available**, and **exclusion of alternative causes**.
   * Do **not** invent or assume beyond the document.
   * Prefer quoting **exact values, drug names, or timelines** when available.
5. **Evidence requirements:**

   * Extract evidence as **bullet-like items** in plain text.
   * Each item should be a **direct fact** from the document.
   * Evidence list should be minimal but cover the key points.



"""

risk_cat_agent = Agent(
	name="Risk Category Agent",
	instructions=risk_category_system,
	model=gemini_2_5_flash_model,
   # model_settings=ModelSettings(temperature=0.1, tool_choice="required"),
   # tools = [WebSearchTool(search_context_size='low')]
)

class RiskCheck(BaseModel):
   risk: str = Field(..., description="Risk category low, medium, high")
   reasoning: str = Field(..., description="Reasoning")
   evidence: str = Field(..., description="List of evidence")

class EncounterData(BaseModel):
   encounter_id: str = Field(..., description="Encounter ID")
   encounter_date: str = Field(..., description="Encounter date")
   encounter_note: str = Field(..., description="Summary note of the encounter")
   encounter_lab_id: Optional[str] = Field("", description="Lab id")

class PatientData(BaseModel):
   patient_name: str = Field(..., description="Name of the patient")
   patient_dob: str = Field(..., description="Patient date of birth")
   patient_sex: str = Field(..., description="Gender of the patient")
   encounters: List[EncounterData] = Field(..., description="Encounters data")


patient_data_system = """
You are a medical data structuring agent.
You will be given **raw, unstructured patient notes** that may contain multiple encounters concatenated together.
Your task is to extract and normalize the data.
---

## 📋 Extraction Rules

1. **Patient Information**

   * Look for explicit mentions of **patient name, DOB, and sex** in the raw text.
   * If not present, return an empty string for the field.

2. **Encounters**

   * Split the raw text into separate **encounters** (based on “Encounter X”, date headers, or logical divisions).
   * Each encounter must include:

     * **`encounter_id`**: assign a unique ID explicitly provided, use it).
     * **`encounter_date`**: extract if present; format to **YYYY-MM-DD** if possible. If only month/year is available, include as `"YYYY-MM"`; else leave empty string.
     * **`encounter_note`**: rewrite the encounter into a **concise summary (2–4 sentences)** covering the patient’s complaints, findings, and impressions.
     * **`encounter_lab_id`**: capture if the note references a lab/test ID (e.g., “Lab #1234”), otherwise return `""`.

3. **Missing Information**

   * Never hallucinate patient details. If the text does not explicitly contain a field, leave it as `""`.

"""
patient_data_agent = Agent(
	name="Patient Data Agent",
	instructions=patient_data_system,
	model=gemini_2_5_flash_model,
   # model_settings=ModelSettings(temperature=0.1, tool_choice="required"),
   # tools = [WebSearchTool(search_context_size='low')]
)


action_system = """

You are an expert clinical reasoning assistant.
You will be given a structured patient analysis document (sections may include: Patient Information, Initial Observations, Differential Diagnosis, Risk Stratification, Agent Perspectives, Consensus, Recommendations, and Liver Adverse Event Risk).

**Your tasks:**

1. **Patient Announcement** – write a short, clear message to the patient explaining their possible risk of liver adverse event.

   * Encourage the patient to take the recommended test to confirm or rule out liver injury.
   * Emphasize that doing the test early can help prevent more serious complications.
   * Keep it concise (2–3 sentences), clear, and reassuring.

2. **Doctor Announcement** – write a short, professional summary for the doctor handling the patient.

   * Highlight the suspected liver risk, the reasoning behind it, and the next critical step (diagnostic test or management action).
   * Keep it focused and clinically relevant (2–3 sentences).

3. **Priority Test (if needed)** – suggest only one most important diagnostic test to confirm or rule out a liver adverse event.

   * If no test is needed, state `"No further testing required at this time."`

4. **Risk–Cost–Benefit Analysis** – provide a short explanatory paragraph describing the cost–benefit trade-off.

   * Clearly state the **approximate financial cost** of the recommended test (e.g., \$50–200 for standard blood tests, \$200–1000 for imaging).
   * Compare this with the potential **medical and financial burden** of untreated critical liver conditions (e.g., hospitalization, \$10,000–50,000+, or even liver transplant costs exceeding \$150,000).
   * Explain why the relatively small cost of testing is justified by the high benefit of early detection and prevention of severe complications.
   * Write in a natural explanatory style, not as a bullet list.


"""
class ActionData(BaseModel):
   patient_announcement: str = Field(..., description="Patient announce to inform the patient")
   recommended_tests: str = Field(..., description="Recommended test to confirm the liver adverse event")
   risk_cost_benefit_analysis: str = Field(..., description="Risk cost benefit analysis")
   doctor_announcement: str = Field(..., description="Doctor annoucement to inform the doctor who handle the patient")




action_agent = Agent(
	name="Action Agent",
	instructions=action_system,
	model=gemini_2_5_flash_model,
   # model_settings=ModelSettings(temperature=0.1, tool_choice="required"),
   # tools = [WebSearchTool(search_context_size='low')]
)


risk_percentage_system = """
You are an expert clinical reasoning assistant specialized in hepatology and drug safety.
You will be given:

* A **structured diagnosis document**
* The **assigned risk level** (`low`, `medium`, `high`)
* A list of **evidence items** (symptoms, labs, drug exposures, timelines, consensus notes)

You can perform **web searches** to support your probability estimation with epidemiological, pharmacovigilance, or clinical guideline data.

---

### 🎯 Task

Your job is to:

1. **Estimate the probability (%) that this patient has a liver adverse event (LAE).**

   * Use the provided **risk level**, the **evidence list**, and (if needed) results from **web search**.
   * Base your estimate on clinical plausibility, known drug hepatotoxicity incidence, and diagnostic criteria (e.g., RUCAM scoring logic, published case frequencies).

2. **Output structured text** with two parts:

```json
{
  "risk_level": "medium",
  "estimated_probability": "45%",
  "reasoning": "The patient presents with elevated ALT and jaundice temporally associated with methotrexate use. Published data indicate methotrexate carries a ~20–30% risk of hepatotoxicity in long-term users. The absence of viral hepatitis markers lowers alternative causes, but lack of biopsy or imaging limits certainty."
}
```

---

### 🔒 Rules

1. **Probability bounds**:

   * `"low"` → typically **<25%**
   * `"medium"` → typically **25–60%**
   * `"high"` → typically **>60%**
     (But adjust based on evidence + web search.)

2. **Reasoning requirements:**

   * Reference **key clinical evidence** (signs, labs, timelines).
   * Cite **known drug hepatotoxicity incidence** if available from search or memory.
   * Explicitly mention why alternatives are less likely.

3. **Do not output anything except the JSON object.**

   * Percentages must be written as strings with `"%"`.
   * Keep reasoning concise (1–3 sentences).

---

"""

class RiskPercent(BaseModel):
   risk_level: str = Field(..., description="Risk level")
   percentage: str = Field(..., description="Percentage probability of liver adverse event")
   reasoning: str = Field(..., description="Reasoning")


risk_percentage_agent = Agent(
	name="Risk Percentage Agent",
	instructions=risk_percentage_system,
	model=gemini_2_5_flash_model,
   # model_settings=ModelSettings(temperature=0.1, tool_choice="required"),
   # tools = [WebSearchTool(search_context_size='low')]
)


refine_annoucement_system = """You are an expert clinical communication assistant.  
You will be given two inputs:  
1. A patient announcement message (explaining risk of liver adverse events and encouraging a confirmatory test).  
2. An estimated probability (%) that the patient may experience a liver adverse event.  

**Your task:** Refine the announcement by incorporating the probability into the message in a way that is clear, realistic, and patient-friendly.  

### Guidelines
1. Place the probability in a natural, understandable way (e.g., “Your estimated risk is around 15%”).  
2. Use plain, supportive language that informs without alarming the patient.  
3. Keep the announcement **2–3 sentences long**.  
4. Keep the encouragement to take the recommended test as a positive, preventive action.  
5. If the probability is very low (<5%), emphasize reassurance. If moderate/high (>20%), emphasize importance of follow-up.  

### Output Format
Return only the **refined patient announcement** as plain text.
"""

annouce_agent_refine = Agent(
	name="Announce Refine Agent",
	instructions=refine_annoucement_system,
	model=gemini_2_5_flash_model,
   # model_settings=ModelSettings(temperature=0.1, tool_choice="required"),
   # tools = [WebSearchTool(search_context_size='low')]
)

