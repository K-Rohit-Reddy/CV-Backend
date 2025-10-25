"""
Service: Resume Enhancer (HTML + PDF)

Purpose:
- Generate enhanced resume HTML by filling a chosen HTML template with the candidate's data (no fabrication),
	optionally converting it to PDF using an external Puppeteer server.

Environment variables:
- GROQ_API_KEY: API key for Groq
- GROQ_MODEL: Model name (default gpt-oss-120b)
- PDF_SERVER_URL: Puppeteer API endpoint (default http://localhost:3000/generate-pdf)

Templates:
- Place numeric HTML templates as Backend/templates/{id}.html (preferred) or CVbackend/templates/{id}.html
	Example: Backend/templates/1.html for template_id="1".

Key function:
- generate_enhanced_resume(resume_data, job_data, optimization_tips, template_id="1", return_pdf=True) -> {"html": str, "pdf_path": Optional[str]}
	- html: final HTML with placeholders replaced, preserving styles and structure
	- pdf_path: path saved under Backend/Resumes/resume-<uuid>.pdf if PDF server succeeds, else None

Example usage (async):
		result = await generate_enhanced_resume(resume_data, job_data, tips, template_id="1", return_pdf=True)
		# result["html"] and result["pdf_path"]
"""
from __future__ import annotations

import os
import json
import base64
from typing import Any, Dict, List, Optional
import uuid

from dotenv import load_dotenv
import requests
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "gpt-oss-120b")
PDF_SERVER_URL = os.getenv("PDF_SERVER_URL", "http://localhost:3000/generate-pdf")

client = Groq(api_key=GROQ_API_KEY)


def _json(o: Any) -> str:
	return json.dumps(o, ensure_ascii=False, indent=2)


def _load_template_html(template_id: str) -> str:
	"""Load an HTML template by id from Backend/templates/{id}.html."""
	here = os.path.dirname(__file__)
	path = os.path.abspath(os.path.join(here, "..", "templates", f"{template_id}.html"))
	if not os.path.exists(path):
		raise FileNotFoundError(
			f"HTML template not found at: {path}. Place an HTML file as Backend/templates/{template_id}.html"
		)
	with open(path, "r", encoding="utf-8") as f:
		return f.read()


def _call_groq_generate_html(template_html: str, resume_data: Dict[str, Any], job_data: Dict[str, Any], optimization_tips: List[str]) -> str:
	"""Ask Groq to produce final HTML by preserving the template's structure and replacing content only."""
	schema = {"html": ""}
	rules = (
		"You must return ONLY valid JSON with the shape {\"html\": \"...\"}.\n"
		"The html must be a complete HTML document ready for printing (no markdown).\n"
		"Strict rules (NO FABRICATION):\n"
		"- Use ONLY information present in resume_data.\n"
		"- You MAY tailor phrasing and ordering using job_data and optimization_tips, but DO NOT add new projects, roles, degrees, dates, or achievements not present in resume_data.\n"
		"- You MAY rephrase bullet points for clarity and impact, quantify only when actual numbers exist in resume_data.\n"
		"- You MAY reorder sections or bullets to prioritize role-relevant info.\n"
		"Template constraints:\n"
		"- Preserve the original template's structure, layout, class names, and inline styles.\n"
		"- Replace placeholders like {{ full_name }}, {{ skills_chips }}, etc. with actual content from resume_data.\n"
		"- Keep semantic sections (Summary, Skills, Experience, Education, Projects, Achievements).\n"
	)

	prompt = f"""
Return ONLY valid JSON with this exact shape:
{_json(schema)}

{rules}

<TEMPLATE_HTML>
{template_html}
</TEMPLATE_HTML>

<RESUME_DATA>
{_json(resume_data)}
</RESUME_DATA>

<JOB_DATA>
{_json(job_data)}
</JOB_DATA>

<OPTIMIZATION_TIPS>
{_json(optimization_tips)}
</OPTIMIZATION_TIPS>
"""

	completion = client.chat.completions.create(
		model=GROQ_MODEL,
		messages=[
			{"role": "system", "content": "You transform resume_data into final HTML using the provided template. Return ONLY a JSON object {\"html\": \"...\"}. Never fabricate."},
			{"role": "user", "content": prompt},
		],
		temperature=0.1,
		response_format={"type": "json_object"},
	)
	content = completion.choices[0].message.content.strip()
	data = json.loads(content)
	html = data.get("html", "")
	if not html or "<html" not in html.lower():
		raise ValueError("Groq did not return valid HTML.")
	return html


def _generate_pdf_via_puppeteer_api(html: str) -> Optional[bytes]:
	"""POST HTML to a Puppeteer server (Node) and return the PDF bytes. Returns None on failure."""
	try:
		resp = requests.post(PDF_SERVER_URL, json={"html": html}, timeout=60)
		if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("application/pdf"):
			return resp.content
		return None
	except Exception:
		return None


async def generate_enhanced_resume(
	resume_data: Dict[str, Any],
	job_data: Dict[str, Any],
	optimization_tips: List[str],
	template_id: str = "default",
	return_pdf: bool = True,
) -> Dict[str, Any]:
	"""
	Generate enhanced resume HTML (no fabrication) using an HTML template and optional PDF via Puppeteer API.

	Inputs:
	- resume_data: parsed resume JSON (from resume_parser)
	- job_data: parsed job JSON (from job_parser)
	- optimization_tips: list of short strings (from candidate analysis)
	- template_id: HTML template filename (without .html) under templates_html/
	- return_pdf: if True, tries to hit PDF_SERVER_URL to get a PDF

	Returns: {"html": str, "pdf_path": Optional[str]}
	"""
	template_html = _load_template_html(template_id)

	# Ask Groq to produce the final HTML using the template
	final_html = _call_groq_generate_html(template_html, resume_data, job_data, optimization_tips)

	result: Dict[str, Any] = {"html": final_html}

	if return_pdf:
		pdf_bytes = _generate_pdf_via_puppeteer_api(final_html)
		if pdf_bytes:
			# Ensure Resumes directory exists
			resumes_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Resumes"))
			os.makedirs(resumes_dir, exist_ok=True)
			file_name = f"resume-{uuid.uuid4().hex}.pdf"
			pdf_path = os.path.join(resumes_dir, file_name)
			with open(pdf_path, "wb") as f:
				f.write(pdf_bytes)
			result["pdf_path"] = pdf_path
		else:
			result["pdf_path"] = None

	return result

