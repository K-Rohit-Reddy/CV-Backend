"""
Service: Resume Parser

Purpose:
- Extract text from uploaded PDF/DOCX resumes and convert it into a strict, structured JSON that matches RESUME_TEMPLATE.

Environment variables:
- GROQ_API_KEY: API key for Groq
- GROQ_MODEL: Model name (e.g., gpt-oss-120b)

Key functions:
- parse_resume(file) -> Dict[str, Any]
    - Input: file (FastAPI UploadFile-like) ending with .pdf or .docx
    - Output: Dict in the exact shape of RESUME_TEMPLATE

- get_resume_summary(text) -> Dict[str, Any]
    - Input: raw text extracted from the resume
    - Output: Dict in the exact shape of RESUME_TEMPLATE

Output contract (RESUME_TEMPLATE keys):
- candidate_name: str
- contact_info: { email, phone, linkedin, portfolio, location }
- current_role: str
- experience_years: int
- core_competencies: List[str]
- skills: List[str]
- education: List[{ institution, degree, year:int }]
- work_experience: List[{ company, role, employment_type, start_date, end_date, is_current, description }]
- achievements: List[str]
 - projects: List[{
         title: str,
         tech_stack: List[str],           # main technologies used
    details: List[str],              # Detailed bullet lines combining description + highlights; include as many as present in the resume; do NOT shorten
         github_url: str,                 # repo link if any, else ""
         live_url: str                    # deployed app/site link if any, else ""
     }]

Example usage (async):
        from fastapi import UploadFile
        data = await parse_resume(upload_file)
        # data matches RESUME_TEMPLATE
"""
from groq import Groq
import json
from typing import Any, Dict
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from docx import Document
import io
import os

load_dotenv()

def _groq_client() -> Groq:
    api = os.getenv("GROQ_API_KEY")
    if not api:
        raise RuntimeError("GROQ_API_KEY is required. Set it in your .env.")
    return Groq(api_key=api)

MODEL_NAME = os.getenv("GROQ_MODEL", "llama3-70b-8192")

RESUME_TEMPLATE = {
    "candidate_name": "John Doe",
    "contact_info": {
        "email": "john@example.com",
        "phone": "123-456-7890",
        "linkedin": "https://linkedin.com/in/johndoe",
        "portfolio": "https://johndoe.com",
        "location": "San Francisco, CA"
    },
    "current_role": "Senior Software Engineer",
    "experience_years": 5,
    "core_competencies": [
        "Software Development",
        "Team Leadership",
        "Project Management"
    ],
    "skills": ["Python", "JavaScript", "React", "Node.js", "MongoDB"],
    "education": [
        {
            "institution": "MIT",
            "degree": "Master's in Software Engineering",
            "year": 2022
        },
        {
            "institution": "Stanford University",
            "degree": "Bachelor's in Computer Science",
            "year": 2020
        }
    ],
    "work_experience": [
        {
            "company": "Microsoft",
            "role": "Senior Software Engineer",
            "employment_type": "Full-time",
            "start_date": "2024-01",
            "end_date": "",
            "is_current": True,
            "description": "Leading frontend development team"
        },
        {
            "company": "Google",
            "role": "Software Engineer",
            "employment_type": "Full-time",
            "start_date": "2022-01",
            "end_date": "2024-12",
            "is_current": False,
            "description": "Developed web applications using React and Node.js"
        }
    ],
    "achievements": [
        "Increased efficiency by 20%",
        "Led team of 5 developers"
    ],
    "projects": [
        {
            "title": "Portfolio Website",
            "tech_stack": ["React", "Next.js", "Vercel"],
            "details": [
                "Personal portfolio showcasing projects and blog posts.",
                "Optimized lighthouse score to 98/100",
                "Implemented dynamic MDX blog system"
            ],
            "github_url": "https://github.com/johndoe/portfolio",
            "live_url": "https://johndoe.com"
        }
    ]
}


async def get_resume_summary(text: str) -> Dict[str, Any]:
    """
    Strictly formatted resume parser using Groq returning EXACTLY the RESUME_TEMPLATE shape.
    """

    prompt = f"""
You must return ONLY valid JSON that follows this exact structure and key order:
{json.dumps(RESUME_TEMPLATE, indent=2)}

No missing keys, no extra text. Follow the exact rules below.

──────────────────────────────
KEY RULES AND DEFINITIONS
──────────────────────────────
1. candidate_name (string): Full candidate name.
2. contact_info (object):
   - email (string, lowercase)
   - phone (string, "xxx-xxx-xxxx" or "")
   - linkedin (string, full URL)
   - portfolio (string or "")
   - location (string, city + state/country)
3. current_role (string): Current or most recent job title.
4. experience_years (integer): Total full years of professional experience.
5. core_competencies (array[str]): 3–10 key soft or domain skills.
6. skills (array[str]): 5–15 technical tools/languages.
7. education (array[object]): Each item has {{"institution","degree","year(int)"}} sorted by year DESC.
8. work_experience (array[object]):
   - company, role, employment_type, start_date(YYYY-MM), end_date(YYYY-MM or ""), is_current(bool), description.
9. achievements (array[str]): 2–5 notable achievements.
10. projects (array[object]): Each item has:
    - title (string)
    - tech_stack (array[str])
    - details (array[str]): Use ALL relevant lines present in the resume. Preserve original phrasing and length (do not abridge or summarize). Keep each bullet as a single string.
    - github_url (string URL or "")
    - live_url (string URL or "")

──────────────────────────────
ADDITIONAL RULES
──────────────────────────────
- Keep same key order as above.
- Use double quotes only.
- Empty fields → "" or [].
- Output must be pure JSON, no markdown, no comments.
 - Do NOT fabricate data: only include projects and links present in the resume text; if unsure, set github_url/live_url to "".
 - Do NOT truncate or shorten project details; include all relevant lines as-is from the resume.
──────────────────────────────

<RESUME_TEXT>
{text}
</RESUME_TEXT>
"""

    messages = [
        {
            "role": "system",
            "content": "You are a JSON schema extractor. Return ONLY valid JSON strictly matching the provided template and order.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        completion = _groq_client().chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        response_content = completion.choices[0].message.content.strip()
        return json.loads(response_content)
    except Exception as e:
        raise Exception(f"Failed to parse resume: {str(e)}")


async def parse_resume(file: Any) -> Dict[str, Any]:
    """Extract text from PDF/DOCX and return structured JSON using get_resume_summary."""
    file_content = await file.read()

    if file.filename.lower().endswith(".pdf"):
        text = "\n".join(
            p.extract_text()
            for p in PdfReader(io.BytesIO(file_content)).pages
            if p.extract_text()
        )
    elif file.filename.lower().endswith(".docx"):
        text = "\n".join(
            p.text for p in Document(io.BytesIO(file_content)).paragraphs if p.text
        )
    else:
        raise ValueError("Only PDF/DOCX supported")

    return await get_resume_summary(text)
