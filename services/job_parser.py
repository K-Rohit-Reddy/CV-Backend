"""
Service: Job Parser

Purpose:
- Fetch a job posting page, extract meaningful text, and produce a strict structured JSON (JOB_TEMPLATE) via Groq.

Environment variables:
- GROQ_API_KEY: API key for Groq
- GROQ_MODEL: Model name used for extraction

Key functions:
- parse_job_from_url(url: str) -> Dict[str, Any]
    - Input: public job URL (http/https)
    - Output: Dict in the exact JOB_TEMPLATE shape

- get_job_details(text: str, url: str) -> Dict[str, Any]
    - Input: cleaned job posting text and original URL
    - Output: Dict in the exact JOB_TEMPLATE shape

Output contract (JOB_TEMPLATE keys):
- job_title: str
- company: { name, location, industry }
- job_details: { employment_type, work_mode, experience_required, salary_range, posted_date }
- requirements: { must_have_skills:[], nice_to_have_skills:[], education:[], experience_years:int, certifications:[] }
- responsibilities: List[str]
- core_competencies_needed: List[str]
- job_description_raw: str (<= 2000 chars)
- application_url: str

Example usage (async):
        job = await parse_job_from_url("https://example.com/jobs/123")
        # job matches JOB_TEMPLATE
"""
from groq import Groq
import json
from typing import Any, Dict
from dotenv import load_dotenv
import os
import requests
from bs4 import BeautifulSoup
import re
from tiktoken import encoding_for_model

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = os.getenv("GROQ_MODEL")

JOB_TEMPLATE = {
    "job_title": "",
    "company": {
        "name": "",
        "location": "",
        "industry": ""
    },
    "job_details": {
        "employment_type": "",
        "work_mode": "",
        "experience_required": "",
        "salary_range": "",
        "posted_date": ""
    },
    "requirements": {
        "must_have_skills": [],
        "nice_to_have_skills": [],
        "education": [],
        "experience_years": 0,
        "certifications": []
    },
    "responsibilities": [],
    "core_competencies_needed": [],
    "job_description_raw": "",
    "application_url": ""
}


# --------------------- Utility Functions ---------------------

def fetch_webpage(url: str) -> str:
    """Fetch the HTML content of a webpage."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.text
        raise Exception(f"Failed to fetch webpage. Status code: {response.status_code}")
    except Exception as e:
        raise Exception(f"Error fetching webpage: {str(e)}")


def clean_text(text: str) -> str:
    """Clean extracted text by removing unnecessary whitespace."""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\t+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def extract_text_content(html: str) -> str:
    """Extract main job description content using BeautifulSoup."""
    soup = BeautifulSoup(html, 'html.parser')

    # Remove noise
    for element in soup.select(
        'script, style, svg, iframe, nav, footer, header, aside, '
        '.cookie-banner, .advertisement, .sidebar, .comments, '
        '.related-jobs, .similar-jobs'
    ):
        element.decompose()

    # Priority selectors for job content
    selectors_priority = [
        ".job-description",
        ".job-details",
        "[itemprop='description']",
        ".description",
        "#job-description",
        ".posting-requirements",
        ".job-posting-section",
        ".job-content",
        "[data-automation='jobDescription']",
        ".jobsearch-JobComponent-description"
    ]

    for selector in selectors_priority:
        elements = soup.select(selector)
        if elements:
            content = elements[0].get_text().strip()
            if content and len(content) > 300:
                return clean_text(content)

    # Fallbacks
    generic_selectors = ["main", "article", "[role='main']", "#main", "#content", ".content"]
    for selector in generic_selectors:
        elements = soup.select(selector)
        if elements:
            content = elements[0].get_text().strip()
            if content and len(content) > 500:
                return clean_text(content)

    # Last fallback: whole body
    body = soup.find("body")
    if body:
        return clean_text(body.get_text())

    return clean_text(soup.get_text())


def estimate_tokens(text: str, model: str) -> int:
    """Estimate token count for Groq model safely."""
    try:
        enc = encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        # fallback heuristic (~4 chars/token)
        return len(text) // 4


# --------------------- Groq Extraction ---------------------

async def get_job_details(text: str, url: str) -> Dict[str, Any]:
    """Structured JSON job parser using Groq JSON mode."""
    prompt = f"""
You must return ONLY valid JSON that follows this exact structure and key order:
{json.dumps(JOB_TEMPLATE, indent=2)}

Rules:
- No missing keys, no extra fields.
- Use double quotes only.
- experience_years must be integer.
- Dates: YYYY-MM or empty string.
- job_description_raw: keep full description (max 2000 chars).
- Keep education sorted DESC by relevance if multiple.
- Output only JSON, no markdown.

<JOB_URL>
{url}
</JOB_URL>

<JOB_POSTING_TEXT>
{text}
</JOB_POSTING_TEXT>
"""

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
            {"role": "system", "content": "You are a strict JSON schema extractor for job postings."},
            {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        response_content = completion.choices[0].message.content.strip()
        return json.loads(response_content)

    except Exception as e:
        raise Exception(f"Failed to parse job posting: {str(e)}")


# --------------------- Main Entry ---------------------

async def parse_job_from_url(url: str) -> Dict[str, Any]:
    """Extract and parse a job posting URL into structured JSON."""
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("Invalid URL format. Must start with http:// or https://")

    html_content = fetch_webpage(url)
    text_content = extract_text_content(html_content)

    # Token-aware safe cap 
    token_count = estimate_tokens(text_content, MODEL_NAME)
    print(f"Estimated token count: {token_count}")

    if token_count > 120_000:
        print("⚠️ Large page detected, truncating safely.")
        text_content = text_content[:400_000]  # roughly ~120k tokens

    job_data = await get_job_details(text_content, url)
    return job_data
