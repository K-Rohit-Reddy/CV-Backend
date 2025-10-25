"""
Service: Interview Preparation

Purpose:
- Generate tailored interview questions and corresponding answers using job and resume data.

Environment variables:
- GROQ_API_KEY: API key for Groq
- GROQ_MODEL: Model name for generation

Key functions:
- generate_interview_questions(job_data, resume_data, interview_type, count) -> List[str]
	- interview_type: "technical" | "behavioral" | "system_design" | "mixed"
	- count: number of questions to generate

- generate_interview_answers(job_data, resume_data, interview_type, questions) -> List[str]
	- questions: list returned by generate_interview_questions (same order)

Output format:
- Both functions return a Python List[str] parsed from a strict JSON payload {"items": [ ... ]}.

Example usage (async):
		qs = await generate_interview_questions(job_data, resume_data, "technical", 8)
		ans = await generate_interview_answers(job_data, resume_data, "technical", qs)
"""
from groq import Groq
from dotenv import load_dotenv
from typing import Any, Dict, List
import os
import json

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = os.getenv("GROQ_MODEL")


async def generate_interview_questions(
	job_data: Dict[str, Any],
	resume_data: Dict[str, Any],
	interview_type: str,
	count: int,
) -> List[str]:
	"""
	Generate interview questions as a strict JSON array of strings.
	Inputs:
	- job_data: output from job_parser (JOB_TEMPLATE shape)
	- resume_data: output from resume_parser (RESUME_TEMPLATE shape)
	- interview_type: e.g., "technical", "behavioral", "system_design", "mixed"
	- count: desired number of questions
	Returns: List[str]
	"""

	job_json = json.dumps(job_data, indent=2, ensure_ascii=False)
	resume_json = json.dumps(resume_data, indent=2, ensure_ascii=False)

	prompt = f"""
<INSTRUCTIONS>
You MUST return ONLY a JSON object with a single key "items" whose value is a JSON array of strings. Each string is ONE interview question.
Rules:
- Output strictly a JSON object: {"items": ["question1", "question2", ...]}
- Use double quotes only, valid JSON, no trailing commas, no markdown.
- Tailor questions to BOTH the job requirements and the candidate resume.
- Avoid generic questions; be specific and relevant.
- Interview type: {interview_type}
- Number of questions: {count}

Scoping guidance by interview type:
- technical: focus on technologies, architecture, problem-solving, code reasoning.
- behavioral: focus on past experiences, teamwork, leadership, conflict resolution (STAR-oriented).
- system_design: focus on scalability, reliability, trade-offs, diagrams mental models.
- mixed: balanced mixture of technical and behavioral.

Return ONLY the JSON object with the key "items".
</INSTRUCTIONS>

<JOB_DATA>
{job_json}
</JOB_DATA>

<RESUME_DATA>
{resume_json}
</RESUME_DATA>
"""

	messages = [
		{
			"role": "system",
			"content": "You return ONLY valid JSON objects with the single key 'items' containing an array of strings. No markdown or extra text.",
		},
		{"role": "user", "content": prompt},
	]

	try:
		completion = client.chat.completions.create(
			model=MODEL_NAME,
			messages=messages,
			temperature=0.0,
			response_format={"type": "json_object"},
		)

		raw = completion.choices[0].message.content.strip()
		obj = json.loads(raw)
		items = obj.get("items", [])
		if not isinstance(items, list):
			raise ValueError("Model returned invalid structure: 'items' is not a list")
		# Ensure all elements are strings
		return [str(x) for x in items]
	except Exception as e:
		raise Exception(f"Failed to generate questions: {str(e)}")


async def generate_interview_answers(
	job_data: Dict[str, Any],
	resume_data: Dict[str, Any],
	interview_type: str,
	questions: List[str],
) -> List[str]:
	"""
	Generate answers for the given questions as a strict JSON array of strings.
	Inputs:
	- job_data: output from job_parser
	- resume_data: output from resume_parser
	- interview_type: type guidance (technical/behavioral/system_design/mixed)
	- questions: List[str] previously generated or supplied
	Returns: List[str] (same length and order as questions)
	"""

	job_json = json.dumps(job_data, indent=2, ensure_ascii=False)
	resume_json = json.dumps(resume_data, indent=2, ensure_ascii=False)
	questions_json = json.dumps(questions, indent=2, ensure_ascii=False)

	prompt = f"""
<INSTRUCTIONS>
You MUST return ONLY a JSON object with a single key "items" whose value is a JSON array of strings. Each string is ONE answer to the corresponding question in the same order.
Rules:
- Output strictly a JSON object: {"items": ["answer1", "answer2", ...]}
- Use double quotes only, valid JSON, no trailing commas, no markdown.
- Be concise, professional, and specific (avoid single-word answers).
- Ground answers in BOTH the job requirements and the candidate's resume.
- Interview type: {interview_type}; adapt tone and content accordingly.
- Where useful, structure answers implicitly per STAR (Situation-Task-Action-Result) without labeling.
- Avoid revealing that you used a resume or job posting; speak as the candidate.
Return ONLY the JSON object with the key "items".
</INSTRUCTIONS>

<JOB_DATA>
{job_json}
</JOB_DATA>

<RESUME_DATA>
{resume_json}
</RESUME_DATA>

<QUESTIONS>
{questions_json}
</QUESTIONS>
"""

	messages = [
		{
			"role": "system",
			"content": "You return ONLY valid JSON objects with the single key 'items' containing an array of strings. Answer concisely and professionally.",
		},
		{"role": "user", "content": prompt},
	]

	try:
		completion = client.chat.completions.create(
			model=MODEL_NAME,
			messages=messages,
			temperature=0.0,
			response_format={"type": "json_object"},
		)
		raw = completion.choices[0].message.content.strip()
		obj = json.loads(raw)
		items = obj.get("items", [])
		if not isinstance(items, list):
			raise ValueError("Model returned invalid structure: 'items' is not a list")
		return [str(x) for x in items]
	except Exception as e:
		raise Exception(f"Failed to generate answers: {str(e)}")

