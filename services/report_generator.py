"""
Service: Report Generator (PDF)

Purpose:
- Create clean PDF reports for interview prep, either Questions-only or Questions & Answers, including minimal candidate info.

Key functions:
- create_pdf_report(job_id, questions, report_type, resume_data, match_score=None, answers=None, output_file_path=None) -> str
    - If answers is provided, includes Q&A; otherwise questions only.
    - Returns the file path of the generated PDF.
- create_pdf_report_with_answers(...)
- create_pdf_report_questions_only(...)

Inputs:
- job_id: Optional[str]
- questions: List[str]
- report_type: str (e.g., "Technical", "Behavioral")
- resume_data: Dict[str, Any] (expects new resume_parser shape)
- match_score: Optional summary (e.g., {overall_match, skill_match, experience_match})
- answers: Optional[List[str]] (same order as questions)
- output_file_path: Optional[str] (if None, uses timestamped name)

Outputs:
- File path string pointing to the generated PDF on disk.

Example usage:
        path = create_pdf_report(job_id, questions, "Technical", resume_data, answers=answers)
        # path -> "report_with_answers_YYYYMMDD_hhmmss.pdf"
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch
from datetime import datetime
from typing import Any, Dict, List, Optional


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = letter

    # Header brand
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(inch, height - 0.75 * inch, "Builder")
    canvas.setFont("Helvetica", 12)
    canvas.setFillColor(colors.gray)
    canvas.drawString(inch + 65, height - 0.75 * inch, ".io")

    # Separator line
    canvas.setLineWidth(1)
    canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
    canvas.line(inch, height - inch, width - inch, height - inch)

    # Footer page number
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(width / 2, 0.75 * inch, f"Page {doc.page}")

    canvas.restoreState()


def extract_candidate_info(resume_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract only the required candidate details from resume_data (new parser shape).
    Required fields: candidate_name, contact_info.email, contact_info.phone,
    experience_years, skills.
    """
    contact = resume_data.get("contact_info", {}) or {}
    return {
        "candidate_name": resume_data.get("candidate_name", "N/A"),
        "contact_info": {
            "email": contact.get("email", "N/A"),
            "phone": contact.get("phone", "N/A"),
        },
        "experience_years": resume_data.get("experience_years", "N/A"),
        "skills": list(resume_data.get("skills", []) or []),
    }


def build_common_elements(
    job_id: Optional[str],
    questions: List[str],
    report_type: str,
    candidate_info: Dict[str, Any],
    match_score: Optional[Dict[str, Any]],
    styles,
):
    elements: List[Any] = []

    # Title and Generated Date
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=30,
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=12,
        textColor=colors.HexColor("#4B5563"),
        spaceBefore=4,
        leftIndent=20,
        leading=14,
        alignment=TA_LEFT,
    )

    title_text = f"{report_type} Interview Assessment"
    if job_id:
        title_text += f" — {job_id}"
    elements.append(Paragraph(title_text, title_style))
    elements.append(
        Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y')}", body_style)
    )
    elements.append(Spacer(1, 20))

    # Match Score Section (optional)
    if match_score:
        heading_style = ParagraphStyle(
            "HeadingStyle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=colors.black,
            spaceBefore=20,
            spaceAfter=10,
        )
        elements.append(Paragraph("Match Analysis", heading_style))
        elements.append(Spacer(1, 10))

        ms_overall = match_score.get("overall_match", "N/A")
        ms_skill = match_score.get("skill_match", "N/A")
        ms_exp = match_score.get("experience_match", "N/A")

        match_table_data = [
            [
                Paragraph(f"<b>{ms_overall}%</b><br/>Overall Match", body_style),
                Paragraph(f"<b>{ms_skill}%</b><br/>Skills Match", body_style),
                Paragraph(f"<b>{ms_exp}%</b><br/>Experience Match", body_style),
            ]
        ]
        match_table = Table(match_table_data, colWidths=[2 * inch] * 3, hAlign="CENTER")
        match_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ]
            )
        )
        elements.append(match_table)
        elements.append(Spacer(1, 20))

    # Candidate Information Section (required fields only)
    if candidate_info:
        heading_style = ParagraphStyle(
            "HeadingStyle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=colors.black,
            spaceBefore=20,
            spaceAfter=10,
        )
        elements.append(Paragraph("Candidate Information", heading_style))
        elements.append(Spacer(1, 10))

        details_lines = [
            f"Name: {candidate_info.get('candidate_name', 'N/A')}",
            f"Email: {candidate_info.get('contact_info', {}).get('email', 'N/A')}",
            f"Phone: {candidate_info.get('contact_info', {}).get('phone', 'N/A')}",
            f"Experience: {candidate_info.get('experience_years', 'N/A')} years",
            f"Skills: {', '.join(candidate_info.get('skills', [])[:10])}",
        ]
        elements.append(Paragraph("<br/>".join(details_lines), body_style))
        elements.append(Spacer(1, 20))

    return elements


def create_pdf_report_with_answers(
    job_id: Optional[str],
    questions: List[str],
    report_type: str,
    resume_data: Dict[str, Any],
    match_score: Optional[Dict[str, Any]],
    answers: List[str],
    output_file_path: Optional[str] = None,
) -> str:
    """Generates a PDF report including both questions and their answers."""
    if output_file_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file_path = f"report_with_answers_{ts}.pdf"

    doc = SimpleDocTemplate(
        output_file_path,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()
    candidate_info = extract_candidate_info(resume_data)
    elements = build_common_elements(job_id, questions, report_type, candidate_info, match_score, styles)

    # Heading for Questions & Answers
    heading_style = ParagraphStyle(
        "QnAHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=colors.black,
        spaceBefore=20,
        spaceAfter=10,
        alignment=TA_LEFT,
    )
    elements.append(Paragraph("Interview Questions & Answers", heading_style))
    elements.append(Spacer(1, 10))

    # Question & Answer blocks
    question_style = ParagraphStyle(
        "QuestionStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    answer_style = ParagraphStyle(
        "AnswerStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=12,
        textColor=colors.HexColor("#4B5563"),
        spaceBefore=4,
        leftIndent=20,
        leading=14,
        alignment=TA_LEFT,
    )

    answers = answers or []
    for i, question in enumerate(questions or [], 1):
        block = []
        block.append(Paragraph(f"{i}. {question}", question_style))
        if i - 1 < len(answers):
            block.append(Paragraph(f"<font color='#3B82F6'>Answer:</font> {answers[i-1]}", answer_style))
        block.append(Spacer(1, 15))
        elements.append(KeepTogether(block))

    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)
    return output_file_path


def create_pdf_report_questions_only(
    job_id: Optional[str],
    questions: List[str],
    report_type: str,
    resume_data: Dict[str, Any],
    match_score: Optional[Dict[str, Any]],
    output_file_path: Optional[str] = None,
) -> str:
    """Generates a PDF report including only the interview questions."""
    if output_file_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file_path = f"report_questions_only_{ts}.pdf"

    doc = SimpleDocTemplate(
        output_file_path,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()
    candidate_info = extract_candidate_info(resume_data)
    elements = build_common_elements(job_id, questions, report_type, candidate_info, match_score, styles)

    # Heading for Questions only
    heading_style = ParagraphStyle(
        "QHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=colors.black,
        spaceBefore=20,
        spaceAfter=10,
        alignment=TA_LEFT,
    )
    elements.append(Paragraph("Interview Questions", heading_style))
    elements.append(Spacer(1, 10))

    # Question blocks only
    question_style = ParagraphStyle(
        "QuestionStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    for i, question in enumerate(questions or [], 1):
        block = []
        block.append(Paragraph(f"{i}. {question}", question_style))
        block.append(Spacer(1, 15))
        elements.append(KeepTogether(block))

    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)
    return output_file_path


def create_pdf_report(
    job_id: Optional[str],
    questions: List[str],
    report_type: str,
    resume_data: Dict[str, Any],
    match_score: Optional[Dict[str, Any]] = None,
    answers: Optional[List[str]] = None,
    output_file_path: Optional[str] = None,
) -> str:
    """
    Main entry to create the PDF report.
    - If 'answers' is provided, generates a report with both questions and answers.
    - Otherwise, generates a report with questions only.
    - If output_file_path is not provided, a timestamped default file name is used.
    """
    if answers is not None:
        return create_pdf_report_with_answers(
            job_id,
            questions,
            report_type,
            resume_data,
            match_score,
            answers,
            output_file_path,
        )
    else:
        return create_pdf_report_questions_only(
            job_id,
            questions,
            report_type,
            resume_data,
            match_score,
            output_file_path,
        )
