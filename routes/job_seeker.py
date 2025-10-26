import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from dotenv import load_dotenv

from ..models import Role
from bson import ObjectId
from .auth import get_current_user
from ..database import get_db
from ..services.job_parser import parse_job_from_url
from ..services.resume_parser import parse_resume
from ..services.candidate_analysis import generate_candidate_analysis
from ..services.resume_enhancer import generate_enhanced_resume
from ..services.interview_prep import (
    generate_interview_questions,
    generate_interview_answers,
)

load_dotenv()

router = APIRouter(prefix="/job-seeker", tags=["job-seeker"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _map_template_to_candidate_analysis(
    template: Dict[str, Any], resume_data: Dict[str, Any], job_data: Dict[str, Any]
) -> Dict[str, Any]:
    oa = template.get("overall_analysis", {})
    charts = template.get("charts", {})

    # Derive a CandidateAnalysis object expected by the frontend
    name = resume_data.get("candidate_name") or resume_data.get("contact_info", {}).get("name", "Candidate")
    current_role = resume_data.get("current_role", "")
    target_role = job_data.get("job_title", "Target Role")
    target_company = job_data.get("company", {}).get("name", "Target Company")

    overall = float(oa.get("overall_match_score", 0))
    ats = float(oa.get("ats_score", 0))
    # simple synthesized metrics in [0,1]
    metrics = {
        "jobMatchScore": round(overall / 100, 2),
        "atsScore": round(ats / 100, 2),
        "leadershipNarrative": round(min(1.0, (overall + charts.get("resume_effectiveness", {}).get("gauge_score", 0)) / 200), 2),
        "quantitativeEvidence": round(min(1.0, (oa.get("skills_match", 0) + oa.get("experience_match", 0)) / 200), 2),
    }

    # strengths from matches
    strengths = [
        {"label": "Skills alignment", "detail": f"Skills match at {int(oa.get('skills_match', 0))}% vs role requirements."},
        {"label": "Experience alignment", "detail": f"Experience match at {int(oa.get('experience_match', 0))}% relative to benchmark."},
        {"label": "ATS readiness", "detail": f"ATS score at {int(oa.get('ats_score', 0))}% suggests good keyword coverage."},
    ]

    # improvement areas from textual_feedback
    feedback = template.get("improvement_suggestions", {}).get("textual_feedback", [])
    improvement_areas = []
    if feedback:
        improvement_areas.append({
            "label": "Resume improvements",
            "actions": [str(x) for x in feedback][:6],
        })

    # keywords from word cloud
    words = charts.get("word_cloud_keywords", []) or []
    max_freq = max([w.get("frequency", 1) or 1 for w in words] or [1])
    recommended_keywords = [
        {"keyword": str(w.get("word", "")), "coverage": round((float(w.get("frequency", 0)) / float(max_freq or 1)), 2)}
        for w in words if w.get("word")
    ][:20]

    # next steps from resume_optimization_tips
    next_steps = [str(x) for x in template.get("improvement_suggestions", {}).get("resume_optimization_tips", [])][:8]

    # light interview topics from keywords
    topics = []
    if recommended_keywords:
        top_kw = [k["keyword"] for k in recommended_keywords[:3]]
        topics.append({
            "topic": "Role-specific keywords",
            "questions": [f"How have you demonstrated {kw} in recent projects?" for kw in top_kw],
            "coaching": "Tie answers to measurable outcomes and mention stakeholder impact.",
        })
    topics.extend([
        {
            "topic": "Experience depth",
            "questions": [
                "Walk through a flagship project aligned to this role.",
                "Describe a difficult trade-off you made and how you communicated it.",
                "How do you measure success and prevent regressions?",
            ],
            "coaching": "Use concise STAR framing and quantify results.",
        },
        {
            "topic": "Leadership & collaboration",
            "questions": [
                "Share a time you aligned conflicting senior stakeholders.",
                "How do you mentor and scale team practices?",
                "Tell us about a risk you managed in an ambiguous situation.",
            ],
            "coaching": "Emphasize cross-functional rituals and decision cadence.",
        },
    ])

    return {
        "candidate": {
            "name": name,
            "currentRole": current_role,
            "targetRole": target_role,
            "targetCompany": target_company,
        },
        "metrics": metrics,
        "summary": "Analysis generated from your resume and the target role.",
        "strengths": strengths,
        "improvementAreas": improvement_areas,
        "recommendedKeywords": recommended_keywords,
        "nextSteps": next_steps,
        "interviewTopics": topics,
        "resumeAngles": [],
    }


@router.post("/analyze")
async def analyze_resume(
    job_url: Annotated[str, Form(...)],
    file: UploadFile = File(...),
    current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None,
):
    """End-to-end: parse job+resume, run candidate analysis, store and return id + preview payload."""
    if not job_url:
        raise HTTPException(status_code=400, detail="job_url is required")

    # 1) Parse inputs
    job_data = await parse_job_from_url(job_url)
    resume_data = await parse_resume(file)

    # 2) Analysis template (charts + suggestions)
    try:
        template = await generate_candidate_analysis(job_data, resume_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    # 3) CandidateAnalysis mapping for UI
    analysis = _map_template_to_candidate_analysis(template, resume_data, job_data)

    # 4) Persist to DB
    db = await get_db()
    analyses = db["analyses"]
    doc = {
        "user_email": current_user.email,
        "job_url": job_url,
        "job_data": job_data,
        "resume_data": resume_data,
        "analysis_template": template,
        "candidate_analysis": analysis,
        "match_score": template.get("overall_analysis", {}).get("overall_match_score", 0),
        "role": job_data.get("job_title", ""),
        "company": job_data.get("company", {}).get("name", ""),
        "summary": analysis.get("summary", ""),
        "highlights": [h for h in analysis.get("nextSteps", [])][:2],
        "created_at": _now(),
        "updated_at": _now(),
    }
    result = await analyses.insert_one(doc)
    analysis_id = str(result.inserted_id)

    metadata = {
        "id": analysis_id,
        "role": doc["role"],
        "company": doc["company"],
        "summary": doc["summary"],
        "updatedAt": _now().isoformat(),
        "matchScore": int(doc["match_score"]),
    }

    return {"id": analysis_id, "metadata": metadata, "analysis": analysis, "template": template}


@router.get("/analyses")
async def list_analyses(current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None):
    """Return recent analyses metadata for the user (for dashboard snapshots)."""
    db = await get_db()
    analyses = db["analyses"]
    cursor = analyses.find({"user_email": current_user.email}).sort("updated_at", -1).limit(20)
    items: List[Dict[str, Any]] = []
    async for doc in cursor:
        items.append({
            "id": str(doc.get("_id")),
            "role": doc.get("role", ""),
            "company": doc.get("company", ""),
            "matchScore": int(doc.get("match_score", 0)),
            "updatedAt": doc.get("updated_at", _now()).isoformat(),
            "summary": doc.get("summary", ""),
            "highlights": doc.get("highlights", []),
        })
    return {"items": items}


@router.get("/analyses/latest")
async def get_latest_analysis(current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None):
    db = await get_db()
    analyses = db["analyses"]
    doc = await analyses.find_one({"user_email": current_user.email}, sort=[("updated_at", -1)])
    if not doc:
        return {"analysis": None, "template": None, "metadata": None}
    metadata = {
        "id": str(doc.get("_id")),
        "role": doc.get("role", ""),
        "company": doc.get("company", ""),
        "summary": doc.get("summary", ""),
        "updatedAt": doc.get("updated_at", _now()).isoformat(),
        "matchScore": int(doc.get("match_score", 0)),
    }
    return {
        "analysis": doc.get("candidate_analysis"),
        "template": doc.get("analysis_template"),
        "metadata": metadata,
    }


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None):
    db = await get_db()
    analyses = db["analyses"]
    doc = await analyses.find_one({"_id": ObjectId(analysis_id), "user_email": current_user.email})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    metadata = {
        "id": str(doc.get("_id")),
        "role": doc.get("role", ""),
        "company": doc.get("company", ""),
        "summary": doc.get("summary", ""),
        "updatedAt": doc.get("updated_at", _now()).isoformat(),
        "matchScore": int(doc.get("match_score", 0)),
    }
    return {
        "analysis": doc.get("candidate_analysis"),
        "template": doc.get("analysis_template"),
        "metadata": metadata,
    }


@router.get("/history")
async def history(current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None):
    """Return history entries for the user."""
    db = await get_db()
    analyses = db["analyses"]
    enhanced = db["enhanced_resumes"]
    interviews = db["interviews"]
    # Map analysis id to resume enhancement existence
    enhanced_ids = set()
    async for r in enhanced.find({"user_email": current_user.email}, {"analysis_id": 1}):
        if r.get("analysis_id"):
            enhanced_ids.add(str(r["analysis_id"]))
    # Map analysis id to interview existence
    interview_ids = set()
    async for r in interviews.find({"user_email": current_user.email}, {"analysis_id": 1}):
        if r.get("analysis_id"):
            interview_ids.add(str(r["analysis_id"]))

    items: List[Dict[str, Any]] = []
    async for doc in analyses.find({"user_email": current_user.email}).sort("created_at", -1):
        items.append({
            "id": str(doc.get("_id")),
            "role": doc.get("role", ""),
            "company": doc.get("company", ""),
            "uploadedAt": doc.get("created_at", _now()).isoformat(),
            "matchScore": int(doc.get("match_score", 0)),
            "hasAnalysis": True,
            "hasInterviewPack": str(doc.get("_id")) in interview_ids,
            "hasEnhancedResume": str(doc.get("_id")) in enhanced_ids,
            "job": doc.get("job_data", {}),
        })
    return {"items": items}


@router.post("/resume/enhance")
async def enhance_resume(
    analysis_id: Annotated[str, Form(...)],
    template_id: str = Form("1"),
    current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None,
):
    db = await get_db()
    analyses = db["analyses"]
    doc = await analyses.find_one({"_id": ObjectId(analysis_id), "user_email": current_user.email})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")

    resume_data = doc.get("resume_data", {})
    job_data = doc.get("job_data", {})
    tips = doc.get("analysis_template", {}).get("improvement_suggestions", {}).get("resume_optimization_tips", [])

    try:
        result = await generate_enhanced_resume(resume_data, job_data, tips, template_id=template_id, return_pdf=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhancer failed: {str(e)}")

    # persist
    enhanced = db["enhanced_resumes"]
    save_doc = {
        "user_email": current_user.email,
        "analysis_id": str(doc.get("_id")),
        "template_id": template_id,
        "html": result.get("html"),
        "pdf_path": result.get("pdf_path"),
        "created_at": _now(),
    }
    await enhanced.insert_one(save_doc)
    # derive a public URL if pdf_path exists
    pdf_url = None
    pdf_path = result.get("pdf_path")
    if pdf_path:
        fname = os.path.basename(str(pdf_path))
        pdf_url = f"/files/{fname}"
    out = {"html": result.get("html"), "pdf_path": pdf_path, "pdf_url": pdf_url}
    return out


@router.get("/resume/templates")
async def list_resume_templates(
    current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None,
):
    """List available numeric HTML resume templates from Backend/templates/*.html"""
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    items: List[Dict[str, str]] = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name.lower().endswith(".html"):
                tid = name.rsplit(".", 1)[0]
                if tid.isdigit():
                    items.append({"id": tid, "label": f"Template {tid}"})
    return {"items": items}


@router.post("/interview/generate")
async def generate_interview(
    analysis_id: Annotated[str, Form(...)],
    interview_type: Annotated[str, Form("mixed")],
    count: Annotated[int, Form(6)],
    current_user: Annotated[Dict[str, Any], Depends(get_current_user)] = None,
):
    """Generate interview questions and answers using saved analysis context and persist a session."""
    db = await get_db()
    analyses = db["analyses"]
    doc = await analyses.find_one({"_id": ObjectId(analysis_id), "user_email": current_user.email})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")

    job_data = doc.get("job_data", {})
    resume_data = doc.get("resume_data", {})

    # Generate questions then answers
    try:
        questions = await generate_interview_questions(job_data, resume_data, interview_type, int(count))
        answers = await generate_interview_answers(job_data, resume_data, interview_type, questions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interview generation failed: {str(e)}")

    items = []
    for i, q in enumerate(questions):
        items.append({"question": q, "answer": answers[i] if i < len(answers) else ""})

    # persist session
    interviews = db["interviews"]
    await interviews.insert_one({
        "user_email": current_user.email,
        "analysis_id": analysis_id,
        "interview_type": interview_type,
        "count": int(count),
        "items": items,
        "created_at": _now(),
    })

    return {"items": items}
