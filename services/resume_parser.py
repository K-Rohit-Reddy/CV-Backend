from groq import Groq
import json
from typing import Any, Dict
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from docx import Document
import io
import os

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = os.getenv("GROQ_MODEL")

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

──────────────────────────────
ADDITIONAL RULES
──────────────────────────────
- Keep same key order as above.
- Use double quotes only.
- Empty fields → "" or [].
- Output must be pure JSON, no markdown, no comments.
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
        completion = client.chat.completions.create(
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
