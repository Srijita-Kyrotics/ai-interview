import re
import fitz  # PyMuPDF
from typing import Any, Dict, List, Optional


def extract_text_from_pdf_content(content: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF."""
    doc = fitz.open(stream=content, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def normalize_skill_text(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r'[\u2010-\u2015]', '-', value)
    value = re.sub(r'[^a-z0-9+.#/\-\s]', ' ', value)
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


SKILL_BLOCKLIST = {
    "languages", "programming languages", "web technologies", "developer tools",
    "frameworks", "libraries", "databases", "database", "others", "operating systems",
    "tools", "technologies", "methodologies", "concepts", "expertise", "skills",
    "technical", "core", "primary", "secondary", "software", "applications",
    "platforms", "environments", "various", "frontend", "backend", "fullstack",
    "development", "design", "management", "systems", "services", "utilities"
}


SKILL_ALIASES = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "java script": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "type script": "TypeScript",
    "reactjs": "React",
    "react.js": "React",
    "react js": "React",
    "react": "React",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "node.js": "Node.js",
    "node": "Node.js",
    "expressjs": "Express",
    "express.js": "Express",
    "express js": "Express",
    "express": "Express",
    "py": "Python",
    "python": "Python",
    "c sharp": "C#",
    "csharp": "C#",
    "c#": "C#",
    "c plus plus": "C++",
    "cpp": "C++",
    "c++": "C++",
    "sql": "SQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mongo db": "MongoDB",
    "mongodb": "MongoDB",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "fast api": "FastAPI",
    "fastapi": "FastAPI",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "data science": "Data Science",
    "ds": "Data Science",
    "nlp": "NLP",
    "computer vision": "Computer Vision",
    "cv": "Computer Vision",
    "ai": "AI",
    "git": "Git",
    "github": "Git",
    "gitlab": "Git",
    "linux": "Linux",
    "html": "HTML",
    "css": "CSS",
    "tailwind": "Tailwind",
    "tailwind css": "Tailwind",
    "bootstrap": "Bootstrap",
    "rest": "REST",
    "rest api": "REST",
    "restful api": "REST",
    "graphql": "GraphQL",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "scikit-learn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "excel": "Excel"
}


COMMON_SKILL_PATTERNS = sorted(
    {
        "Python", "Java", "C++", "C#", "JavaScript", "TypeScript", "React", "Angular", "Vue", "Node.js", "Express", "Django",
        "FastAPI", "Spring", "SQL", "PostgreSQL", "MySQL", "MongoDB", "AWS", "Azure", "GCP", "Docker",
        "Kubernetes", "Git", "Linux", "HTML", "CSS", "Tailwind", "REST", "GraphQL", "Machine Learning",
        "TensorFlow", "PyTorch", "scikit-learn", "AI", "NLP", "Computer Vision", "Data Science", "DevOps", "Redux",
        "Next.js", "Flask", "Bootstrap", "Power BI", "Tableau", "Excel", "Pandas", "NumPy", "Seaborn", "Matplotlib"
    },
    key=len,
    reverse=True,
)


def clean_line(line: str) -> str:
    line = re.sub(r'^[?•\-\*\s]+', '', line).strip()
    return re.sub(r'\s{2,}', ' ', line)


def split_values(line: str) -> list[str]:
    items = re.split(r'[?•\*;,/|]', line)
    return [item.strip() for item in items if item.strip()]


def canonicalize_skill(raw_skill: str) -> str:
    normalized = normalize_skill_text(raw_skill)
    if not normalized or normalized in SKILL_BLOCKLIST:
        return ""
    if normalized in SKILL_ALIASES:
        return SKILL_ALIASES[normalized]
    if '.' in normalized and normalized.replace('.', '') in SKILL_ALIASES:
        return SKILL_ALIASES[normalized.replace('.', '')]
    return raw_skill.strip().title()


def unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        canonical = canonicalize_skill(item)
        if canonical:
            normalized = normalize_skill_text(canonical)
            if normalized not in seen:
                seen.add(normalized)
                result.append(canonical)
    return result


SECTION_KEYWORDS = {
    "summary": ["summary", "profile", "about me", "professional summary", "career objective", "overview", "professional profile"],
    "education": ["education", "qualification", "academic", "academics", "education & training", "educational background", "education & certifications"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "experience summary", "career history", "work history"],
    "projects": ["projects", "project experience", "portfolio", "selected projects", "key projects", "academic projects", "project highlights"],
    "skills": ["skills", "technical skills", "skillset", "core skills", "programming skills", "expertise", "technical expertise"],
    "certifications": ["certification", "certifications", "certificate", "licenses", "achievements", "awards"]
}


def parse_section_header(line: str) -> tuple[Optional[str], str]:
    normalized_line = re.sub(r'[^a-zA-Z0-9\s&]', ' ', line).strip().lower()
    normalized_line = re.sub(r'\s+', ' ', normalized_line)

    for section, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf'\b{re.escape(keyword)}\b', normalized_line):
                if len(line.strip()) < 50 or ':' in line or '-' in line:
                    parts = re.split(r'[:\-]', line, 1)
                    if len(parts) > 1 and parts[1].strip():
                        return section, parts[1].strip()
                    return section, ""
    return None, ""


EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_PATTERN = re.compile(r'(?:\+?\d[\d\s\-()]{7,}\d)')


def is_contact_line(line: str) -> bool:
    return bool(
        EMAIL_PATTERN.search(line)
        or PHONE_PATTERN.search(line)
        or re.search(r'\b(linkedin|github|portfolio|www\.|http|tel|phone|mobile|whatsapp)\b', line, re.I)
    )


def extract_email(lines: list[str]) -> str:
    for line in lines:
        match = EMAIL_PATTERN.search(line)
        if match:
            return match.group(0).strip()
    return ""


def extract_phone(lines: list[str]) -> str:
    for line in lines:
        for candidate in PHONE_PATTERN.findall(line):
            digits = re.sub(r'\D', '', candidate)
            if 9 <= len(digits) <= 15:
                return candidate.strip()
    return ""


def extract_skills(lines: list[str]) -> list[str]:
    skills = []
    for line in lines:
        if re.search(r'\b(skills?|technical skills|skillset|expertise)\b', line, re.I):
            if ':' in line or '-' in line:
                parts = re.split(r'[:\-]', line, 1)
                if len(parts) > 1:
                    skills.extend(split_values(parts[1]))
            else:
                skills.extend(split_values(line))
    return [canonicalize_skill(skill) for skill in skills if skill]


def extract_name(lines: list[str]) -> str:
    for line in lines:
        match = re.match(r'^(?:name|candidate name|applicant name)\s*[:\-]\s*(.+)$', line, re.I)
        if match:
            return match.group(1).strip()

    candidates = []
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        if is_contact_line(line_clean):
            continue
        if re.match(r'^(resume|curriculum vitae|cv|contact|contact details|contact info|linkedin|github|portfolio|summary|objective|about me|profile)$', line_clean, re.I):
            continue
        if re.search(r'\b(skills?|education|experience|projects?|certifications?|summary|objective|profile|phone|email|gmail|linkedin|github)\b', line_clean, re.I):
            continue
        candidates.append(line_clean)

    if candidates:
        first_cand = candidates[0]
        if re.match(r'^(resume|curriculum vitae|cv)$', first_cand, re.I) and len(candidates) > 1:
            first_cand = candidates[1]

        if '|' in first_cand:
            first_cand = first_cand.split('|')[0].strip()
        elif ',' in first_cand and not re.search(r'\b(university|college|school|inc\.|llc|corp)\b', first_cand, re.I):
            first_cand = first_cand.split(',')[0].strip()

        words = first_cand.split()
        if 1 <= len(words) <= 4:
            return first_cand
        return candidates[0]
    return "Candidate"


def extract_summary(lines: list[str], name: str) -> str:
    summary_lines = []
    for line in lines:
        if line == name or is_contact_line(line):
            continue
        if re.match(r'^(skills?|education|experience|projects?|certifications?|certificates?|profile|summary|objective|about me)\s*[:\-]?$', line, re.I):
            continue
        summary_lines.append(line)
        if len(summary_lines) >= 2:
            break
    if summary_lines:
        return " ".join(summary_lines).strip()
    return "A motivated candidate with practical experience in building scalable interview-ready applications."


def parse_education_line(entry: str) -> Dict[str, str]:
    raw = entry
    duration_match = re.search(r'\b(20\d{2}|19\d{2})(?:\s*[-–—]\s*(20\d{2}|19\d{2}|present|ongoing|current))?\b', entry, re.I)
    duration = duration_match.group(0) if duration_match else ""
    parts = [part.strip() for part in re.split(r'\s*[|]\s*|\s+[-–—]\s+', entry) if part.strip()]
    degree = ""
    institution = ""
    description = ""
    for part in parts:
        if part == duration or re.fullmatch(r'\d{4}', part):
            continue
        if re.search(r'\b(bachelor|master|b\.tech|btech|m\.tech|mtech|msc|phd|diploma|degree|certificate|mba|mca|b\.sc|bsc|m\.sc|msc|ph\.d)\b', part, re.I):
            degree = part
        elif re.search(r'\b(university|institute|college|school|academy|centre|center|faculty)\b', part, re.I):
            institution = part
        elif not institution:
            institution = part
        else:
            description = f"{description} {part}".strip()
    if not degree and parts:
        degree = parts[0]
    if not institution and len(parts) > 1:
        institution = parts[1]
    if duration:
        institution = re.sub(rf'\s*{re.escape(duration)}\s*,?\s*', '', institution, flags=re.I).strip(' ,')
        degree = re.sub(rf'\s*{re.escape(duration)}\s*,?\s*', '', degree, flags=re.I).strip(' ,')
    return {
        "degree": degree or entry,
        "institution": institution,
        "duration": duration,
        "description": description,
        "raw": raw,
    }


def parse_experience_line(entry: str) -> Dict[str, str]:
    raw = entry
    duration_match = re.search(r'\b(20\d{2}|19\d{2})(?:\s*[-–—]\s*(20\d{2}|19\d{2}|present|ongoing|current))?\b', entry, re.I)
    duration = duration_match.group(0) if duration_match else ""
    description = ""
    if ' at ' in entry.lower():
        role_part, company_part = re.split(r'\s+at\s+', entry, flags=re.I, maxsplit=1)
        company = re.split(r'[,|–—]', company_part)[0].strip() if company_part else ''
        if duration and duration in entry:
            parts = entry.split(duration, 1)
            if len(parts) > 1:
                description = parts[1].strip(' -–—|')
        return {
            "role": role_part.strip(),
            "company": company,
            "duration": duration,
            "description": description,
            "raw": raw,
        }
    parts = [part.strip() for part in re.split(r'\s*[|]\s*|\s+[-–—]\s+', entry) if part.strip()]
    role = parts[0] if parts else ''
    company = parts[1] if len(parts) > 1 else ''
    if not company and ',' in entry:
        comma_parts = [p.strip() for p in entry.split(',') if p.strip()]
        if len(comma_parts) > 1:
            role = comma_parts[0]
            company = re.sub(rf'\b{re.escape(duration)}\b', '', comma_parts[1], flags=re.I).strip(' ()-–—')
    if duration:
        company = re.sub(rf'\s*{re.escape(duration)}\s*', '', company, flags=re.I).strip(' ,-–—')
    if duration and duration in entry:
        parts_after = entry.split(duration, 1)
        if len(parts_after) > 1:
            description = parts_after[1].strip(' -–—|')
    return {
        "role": role,
        "company": company,
        "duration": duration,
        "description": description,
        "raw": raw,
    }


def parse_project_line(entry: str) -> Dict[str, str]:
    raw = entry
    parts = [part.strip() for part in re.split(r'\s*[:]\s*|\s+[-–—]\s+', entry, maxsplit=2) if part.strip()]
    if len(parts) >= 2:
        return {"name": parts[0], "description": parts[1], "raw": raw}
    return {"name": entry, "description": "", "raw": raw}


def parse_certification_line(entry: str) -> Dict[str, str]:
    raw = entry
    parts = [part.strip() for part in re.split(r'[\|–—-]', entry) if part.strip()]
    name = parts[0] if parts else entry
    issuer = ""
    year = ""
    if len(parts) > 1:
        issuer = parts[1]
    year_match = re.search(r'\b(20\d{2}|19\d{2})\b', entry)
    if year_match:
        year = year_match.group(0)
    return {"name": name, "issuer": issuer, "year": year, "raw": raw}


def extract_qualification(education_entries: list[dict], full_text: str) -> str:
    degree_keywords = r'(?i)\b(Bachelor(?:\'s)?|Master(?:\'s)?|MBA|MCA|M\.Tech|MTech|M\.Sc|MSc|B\.Tech|BTech|B\.Sc|BSc|Ph\.D|PhD|Diploma|Certificate)\b'
    for entry in education_entries:
        degree = entry.get("degree", "").strip()
        if degree and degree.lower() != entry.get("raw", "").strip().lower():
            return degree
    match = re.search(degree_keywords + r'.*', full_text)
    if match:
        return match.group(0).strip()
    if education_entries:
        return education_entries[0].get("degree") or education_entries[0].get("raw", "Bachelor's Degree")
    return "Bachelor's Degree"


def parse_section_entries(entries: list[str], parser) -> list[dict]:
    parsed = []
    for entry in entries:
        item = parser(entry)
        if item:
            parsed.append(item)
    return parsed


def parse_resume_text(text: str, filename: str = "") -> Dict[str, Any]:
    text_camel_separated = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    cleaned_lines = []
    seen = set()

    for line in lines:
        normalized = re.sub(r'[^a-z0-9]', '', line.lower())

        if normalized not in seen:
            seen.add(normalized)
            cleaned_lines.append(line)

    lines = cleaned_lines
    header_lines = []
    sections = {"summary": [], "education": [], "experience": [], "projects": [], "skills": [], "certifications": []}
    current_section = None

    for line in lines:
        heading_section, heading_value = parse_section_header(line)
        if heading_section:
            current_section = heading_section
            if heading_value:
                if current_section == "skills":
                    sections[current_section].extend(split_values(heading_value))
                else:
                    sections[current_section].append(heading_value)
            continue

        if current_section:
            if current_section == "skills":
                sections[current_section].extend(split_values(line))
            else:
                if current_section == "experience" and sections["experience"]:
                    if not re.search(r'\bat\b|\b(20\d{2}|19\d{2})\b|\bpresent\b|\bcurrent\b', line, re.I):
                        sections["experience"][-1] = f"{sections['experience'][-1]} {line}".strip()
                    else:
                        sections[current_section].append(line)
                else:
                    sections[current_section].append(line)
        else:
            header_lines.append(line)
            if re.search(r'\b(skills?|technical skills|skillset|expertise)\b', line, re.I):
                values = re.split(r'[:\-]', line, 1)[1] if re.search(r'[:\-]', line) else line
                sections["skills"].extend(split_values(values))

    sections["skills"].extend(extract_skills(header_lines))
    sections["skills"] = [skill for skill in sections["skills"] if skill]

    email = extract_email(header_lines) or extract_email(lines)
    phone = extract_phone(header_lines) or extract_phone(lines)

    name = extract_name(header_lines)
    summary = " ".join(sections["summary"]).strip() or extract_summary(header_lines, name)

    skill_candidates = unique([skill for skill in sections["skills"] if skill])
    for skill in COMMON_SKILL_PATTERNS:
        escaped = re.escape(skill)
        prefix = r'\b' if re.match(r'^\w', skill) else r'(?<!\w)'
        suffix = r'\b' if re.match(r'.*\w$', skill) else r'(?!\w)'
        pattern = prefix + escaped + suffix
        if re.search(pattern, text, re.I) or re.search(pattern, text_camel_separated, re.I):
            canonical = canonicalize_skill(skill)
            if canonical:
                normalized_cand = [normalize_skill_text(s) for s in skill_candidates]
                if normalize_skill_text(canonical) not in normalized_cand:
                    skill_candidates.append(canonical)

    education_entries = parse_section_entries(sections["education"], parse_education_line)
    experience_entries = parse_section_entries(sections["experience"], parse_experience_line)
    project_entries = parse_section_entries(sections["projects"], parse_project_line)
    certification_entries = parse_section_entries(sections["certifications"], parse_certification_line)

    education = education_entries
    experience = experience_entries
    projects = project_entries
    certifications = certification_entries
    qualification = (
        education[0].get("degree")
        if education
        else ""
    )

    resume = {
        "name": name,
        "email": email,
        "phone": phone,
        "summary": summary,
        "qualification": qualification,
        "education": education,
        "experience": experience,
        "skills": skill_candidates if skill_candidates else ["Python", "React", "FastAPI"],
        "projects": projects,
        "certifications": certifications,
        "rawText": text[:2000],
        "filename": filename,
    }

    return resume
