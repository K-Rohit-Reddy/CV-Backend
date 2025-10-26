"""
Service: Candidate Analysis

Purpose:
- Produce a dashboard-ready analysis JSON comparing job requirements to a candidate resume, including compulsory course recommendations.

Environment variables:
- GROQ_API_KEY: API key for Groq
- GROQ_MODEL: Model name
- TAVILY_API_KEY: Required for fetching certification/course links (Tavily search)

Key function:
- generate_candidate_analysis(job_data, resume_data) -> Dict[str, Any]
    - Returns a Dict strictly matching ANALYSIS_TEMPLATE.
    - Internally: extracts missing skills (Groq) -> expands related skills (Groq) -> fetches links (Tavily) -> ranks/normalizes courses (Groq) -> final analysis (Groq).

Outputs (ANALYSIS_TEMPLATE, summarized):
- overall_analysis: scores (0–100) and counts
- charts: skill distribution, experience comparison, word cloud, career timeline, effectiveness gauge
- profile_highlights: publications, volunteer_work
- improvement_suggestions: textual_feedback, recommended_courses[{name,platform,url}], skill_gap_closure_plan, resume_optimization_tips

Example usage (async):
        analysis = await generate_candidate_analysis(job_data, resume_data)
        # analysis matches ANALYSIS_TEMPLATE
"""
from groq import Groq
from dotenv import load_dotenv
from typing import Any, Dict, List
import os
import json
from tavily import TavilyClient


load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

def _groq_client() -> Groq:
    api = os.getenv("GROQ_API_KEY")
    if not api:
        raise RuntimeError("GROQ_API_KEY is required. Set it in your .env.")
    return Groq(api_key=api)

def _tavily() -> TavilyClient:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is required for course recommendations. Set it in your .env.")
    return TavilyClient(key)


# Target JSON structure template to enforce model output
ANALYSIS_TEMPLATE: Dict[str, Any] = {
    "overall_analysis": {
        "overall_match_score": 0,
        "skills_match": 0,
        "experience_match": 0,
        "education_match": 0,
        "certifications_match": 0,
        "missing_skills_count": 0,
        "ats_score": 0,
    },
    "charts": {
        "skill_match_distribution": {
            "matched": 0,
            "missing": 0,
            "partially_matched": 0,
        },
        "experience_comparison": {
            "required_experience_years": 0,
            "candidate_experience_years": 0,
        },
        "word_cloud_keywords": [
            {"word": "", "frequency": 0}
        ],
        "career_timeline": [
            {"year": "", "role": "", "organization": ""}
        ],
        "resume_effectiveness": {"gauge_score": 0},
    },
    "profile_highlights": {
        "publications": [],
        "volunteer_work": [],
    },
    "improvement_suggestions": {
        "textual_feedback": [],
        "recommended_courses": [
            {"name": "", "platform": "", "url": ""}
        ],
        "skill_gap_closure_plan": [
            {"missing_skill": "", "recommended_action": "", "priority_level": ""}
        ],
        "resume_optimization_tips": [],
    },
}


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


async def generate_candidate_analysis(job_data: Dict[str, Any], resume_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Default analysis pipeline (certifications compulsory):
    - Infer missing skills with Groq
    - Expand skills with Groq
    - Fetch certifications via Tavily
    - Rank & normalize recommended courses with Groq
    - Generate final analysis JSON with Groq using job_data, resume_data and recommended_courses
    """

    tavily_client = _tavily()

    # 1) Missing skills via Groq
    missing_skills = await _extract_missing_skills_via_groq(job_data, resume_data)
    # 2) Expand with Groq to get related technologies in same ecosystem
    expanded_skills = await _expand_skills_via_groq(missing_skills)
    # 3) Tavily search
    search_results = _fetch_certifications_with_tavily(expanded_skills)
    # 4) Rank & normalize using Groq
    recommended_courses = await _rank_certifications_with_groq(missing_skills, search_results)

    # 5) Final analysis generation
    prompt = f"""
You must return ONLY valid JSON that follows this exact structure and key order:
{_json(ANALYSIS_TEMPLATE)}

Important output rules:
- Output only JSON (no markdown). Use double quotes only. No extraneous keys.
- Ensure numeric fields are numbers (not strings). Keep all keys present, even if values are 0 or empty arrays.
- Integrate the provided recommended_courses under improvement_suggestions.recommended_courses as-is (deduplicate by name+url).
- Base all judgments on BOTH job_data and resume_data.

Attribute guide (interpretation hints):
- overall_analysis:
    - overall_match_score: 0-100 weighted blend of skills_match (50%), experience_match (25%), education_match (15%), certifications_match (10%).
    - skills_match, experience_match, education_match, certifications_match: each 0-100 describing alignment with job needs.
    - missing_skills_count: number of skills from MISSING_SKILLS that the candidate lacks.
    - ats_score: 0-100 indicating keyword alignment and clarity for ATS parsing.
- charts:
    - skill_match_distribution: counts of matched, missing, partially_matched skills; these should be consistent with your comparison.
    - experience_comparison: required_experience_years vs candidate_experience_years (numbers in years).
    - word_cloud_keywords: 10-20 key terms with frequency from combined job/resume context.
    - career_timeline: chronological entries from resume work experience (year, role, organization).
    - resume_effectiveness.gauge_score: 0-100 based on clarity, keywords, structure.
- profile_highlights: pull publications or volunteer_work if present; otherwise leave empty arrays.
- improvement_suggestions:
    - textual_feedback: 5-8 short, actionable bullets.
    - recommended_courses: use provided items (name, platform, url); keep best 5.
    - skill_gap_closure_plan: for each top missing skill, give a recommended_action and priority_level (High/Medium/Low).
    - resume_optimization_tips: 4-6 concrete resume edits (e.g., quantify achievements, reorder sections, add keywords).

<JOB_DATA>
{_json(job_data)}
</JOB_DATA>

<RESUME_DATA>
{_json(resume_data)}
</RESUME_DATA>

<MISSING_SKILLS>
{_json(missing_skills)}
</MISSING_SKILLS>

<RECOMMENDED_COURSES>
{_json(recommended_courses)}
</RECOMMENDED_COURSES>
"""

    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict JSON analysis engine for job-resume matching. "
                "Return ONLY the JSON object exactly in the provided shape."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    completion = _groq_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    response_content = completion.choices[0].message.content.strip()
    return json.loads(response_content)


async def _expand_skills_via_groq(missing_skills: List[str]) -> List[str]:
    """Use Groq to expand missing skills into related tools and frameworks. Returns list of names."""
    schema = {"items": [""]}
    prompt = f"""
Return ONLY valid JSON with this exact shape:
{_json(schema)}

You are a technical career mentor. The user is missing: {', '.join(missing_skills)}.
Suggest 5–10 related tools, libraries, or frameworks in the same ecosystem.
Place the names in items[] (strings only). No explanations.
"""
    completion = _groq_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": "Return ONLY a JSON object {\"items\": [...]}."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        items = data.get("items", [])
        return [str(x) for x in items if isinstance(x, (str, int, float))]
    except Exception:
        return missing_skills


def _fetch_certifications_with_tavily(expanded_skills: List[str]) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    try:
        tavily_client = _tavily()
    except Exception:
        return results
    for skill in expanded_skills:
        query = f"best certifications for {skill} developers"
        try:
            resp = tavily_client.search(query=query, max_results=5)
        except Exception:
            continue
        for r in (resp.get("results", []) if isinstance(resp, dict) else []):
            results.append(
                {
                    "skill": skill,
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": (r.get("content", "") or "")[:300],
                }
            )
    return results


async def _rank_certifications_with_groq(
    missing_skills: List[str], search_results: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    snippet = "\n".join(
        [f"- {r.get('title','')} ({r.get('url','')})" for r in search_results[:12]]
    )
    schema = {"items": [{"name": "", "platform": "", "url": ""}]}
    prompt = f"""
Return ONLY valid JSON with this exact shape:
{_json(schema)}

The user wants certifications to fill skill gaps in: {', '.join(missing_skills)}.

Here are search results (title and link):
{snippet}

Select the 5 most relevant certifications that directly teach the needed skills.
Return them in items[] with fields name, platform, url. No extra fields.
"""
    completion = _groq_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": "Return ONLY a JSON object {\"items\": [...]} with name/platform/url."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        items = data.get("items", [])
        out: List[Dict[str, str]] = []
        for it in items:
            out.append({
                "name": str(it.get("name", "")),
                "platform": str(it.get("platform", "")),
                "url": str(it.get("url", "")),
            })
        return [x for x in out if x["name"] and x["url"]]
    except Exception:
        return []


async def _extract_missing_skills_via_groq(
    job_data: Dict[str, Any], resume_data: Dict[str, Any]
) -> List[str]:
    schema = {"missing_skills": [""]}
    prompt = f"""
Return ONLY valid JSON with this exact shape:
{_json(schema)}

Rules:
- Compare the job requirements (skills, competencies) with the candidate resume skills.
- Provide a concise list of truly missing or significantly weak skills for the candidate to learn next.
- Use double quotes only and no markdown.

<JOB_DATA>
{_json(job_data)}
</JOB_DATA>

<RESUME_DATA>
{_json(resume_data)}
</RESUME_DATA>
"""
    completion = _groq_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": "Return ONLY a JSON object with missing_skills: [...]."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        items = data.get("missing_skills", [])
        if isinstance(items, list):
            return [str(x) for x in items if isinstance(x, (str, int, float))]
    except Exception:
        pass
    return []


    
