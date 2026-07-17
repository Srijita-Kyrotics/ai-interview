"""Tests for resume_parser.py."""
from app.resume_parser import extract_text_from_pdf_content, normalize_skill_text, parse_resume_text

SAMPLE_RESUME = """
John Doe
john.doe@email.com
+1-555-123-4567

Summary
Experienced software engineer with 5 years in full-stack development.

Education
B.Tech in Computer Science - Indian Institute of Technology - 2018-2022

Experience
Software Engineer at Google - 2022-Present
Built scalable microservices handling 1M+ requests per day

Junior Developer at Startup Inc - 2020-2022
Developed React frontend and Python backend APIs

Skills
Python, JavaScript, React, Node.js, Docker, AWS, SQL, Git

Projects
AI Chatbot - Built a conversational AI using NLP techniques
E-commerce Platform - Full-stack React/Django application

Certifications
AWS Certified Solutions Architect - Amazon - 2023
Google Cloud Professional - Google - 2022
"""


class TestNormalizeSkillText:
    def test_lowercase(self):
        assert normalize_skill_text("PYTHON") == "python"

    def test_strip_special_chars(self):
        assert normalize_skill_text("C++!") == "c++"

    def test_normalize_dashes(self):
        result = normalize_skill_text("machine-learning")
        assert "\u2010" not in result  # no en-dash

    def test_collapse_whitespace(self):
        assert normalize_skill_text("  hello   world  ") == "hello world"


class TestParseResumeText:
    def test_extracts_name(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert "John" in result["name"]

    def test_extracts_email(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert result["email"] == "john.doe@email.com"

    def test_extracts_phone(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert "555" in result["phone"]

    def test_extracts_skills(self):
        result = parse_resume_text(SAMPLE_RESUME)
        skills = [s.lower() for s in result["skills"]]
        assert "python" in skills
        assert "react" in skills
        assert "docker" in skills

    def test_extracts_education(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert len(result["education"]) >= 1
        assert any("B.Tech" in e.get("degree", "") or "b.tech" in e.get("degree", "").lower()
                    for e in result["education"])

    def test_extracts_experience(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert len(result["experience"]) >= 1

    def test_extracts_projects(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert len(result["projects"]) >= 1

    def test_extracts_certifications(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert len(result["certifications"]) >= 1

    def test_raw_text_truncated(self):
        result = parse_resume_text(SAMPLE_RESUME)
        assert len(result["rawText"]) <= 2000

    def test_filename_preserved(self):
        result = parse_resume_text(SAMPLE_RESUME, "my_resume.pdf")
        assert result["filename"] == "my_resume.pdf"

    def test_returns_all_keys(self):
        result = parse_resume_text(SAMPLE_RESUME)
        expected = {"name", "email", "phone", "summary", "qualification",
                     "education", "experience", "skills", "projects",
                     "certifications", "rawText", "filename"}
        assert expected.issubset(result.keys())


class TestMinimalResume:
    """Edge case: very minimal input."""
    def test_empty_text(self):
        result = parse_resume_text("")
        assert result["name"] == "Candidate"
        assert isinstance(result["skills"], list)

    def test_name_only(self):
        result = parse_resume_text("Jane Smith\njane@test.com")
        assert "Jane" in result["name"] or "jane" in result["email"]


class TestSkillCanonicalization:
    """Test that skills are properly canonicalized."""
    def test_aliases_resolved(self):
        text = "Skills: js, ts, py, reactjs, nodejs"
        result = parse_resume_text(text)
        skills = [s.lower() for s in result["skills"]]
        assert "javascript" in skills
        assert "typescript" in skills
        assert "python" in skills

    def test_blocklist_filtered(self):
        text = "Skills: languages, tools, Python"
        result = parse_resume_text(text)
        skills_lower = [s.lower() for s in result["skills"]]
        assert "languages" not in skills_lower
        assert "tools" not in skills_lower
        assert "python" in skills_lower


class TestExtractTextFromPdf:
    def test_invalid_pdf_raises(self):
        import pytest
        with pytest.raises(Exception):
            extract_text_from_pdf_content(b"not a pdf")
