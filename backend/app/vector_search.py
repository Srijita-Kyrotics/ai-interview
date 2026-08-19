"""
Vector-Based Resume Search
===========================
Generates embeddings for resume chunks and enables semantic search
across the candidate pool. Uses sentence-transformers for embeddings
and stores vectors as JSON arrays in PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import numpy as np
import psycopg2.extras

from app.config import settings
from app.db import get_connection, release_connection

logger = logging.getLogger("ai_interview.vector_search")

# Global embedding model (lazy loaded)
_embedding_model = None


def get_embedding_model():
    """Get or create the sentence transformer model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = getattr(settings, "embedding_model", "all-MiniLM-L6-v2")
            _embedding_model = SentenceTransformer(model_name)
            logger.info("Loaded embedding model: %s", model_name)
        except Exception as e:
            logger.warning("Failed to load embedding model: %s", e)
            _embedding_model = False  # Mark as unavailable
    return _embedding_model if _embedding_model is not False else None


def init_vector_tables() -> None:
    """Initialize database tables for vector storage."""
    conn = get_connection()
    try:
        c = conn.cursor()
        # Resume embeddings table
        c.execute("""
            CREATE TABLE IF NOT EXISTS resume_embeddings (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                candidate_email TEXT NOT NULL,
                chunk_text TEXT NOT NULL,
                chunk_type TEXT NOT NULL,  -- 'skills', 'experience', 'projects', 'education', 'summary'
                embedding JSONB NOT NULL,  -- Vector as JSON array
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_resume_embeddings_email ON resume_embeddings(candidate_email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_resume_embeddings_session ON resume_embeddings(session_id)")

        # Job description embeddings table (for skill gap analysis)
        c.execute("""
            CREATE TABLE IF NOT EXISTS job_embeddings (
                id SERIAL PRIMARY KEY,
                job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT,
                description TEXT NOT NULL,
                embedding JSONB NOT NULL,
                required_skills JSONB DEFAULT '[]'::jsonb,
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_job_embeddings_job_id ON job_embeddings(job_id)")

        conn.commit()
        logger.info("Vector search tables initialized")
    finally:
        release_connection(conn)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a)
    b_np = np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))


def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding for a text string."""
    model = get_embedding_model()
    if model is None:
        return None
    try:
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    except Exception as e:
        logger.error("Failed to generate embedding: %s", e)
        return None


def chunk_resume_for_embedding(resume_parsed: dict) -> list[dict]:
    """
    Split a parsed resume into semantic chunks for embedding.

    Returns list of dicts with keys: chunk_text, chunk_type, metadata
    """
    chunks = []

    # Skills chunk
    skills = resume_parsed.get("skills", [])
    if skills:
        skills_text = "Skills: " + ", ".join(str(s) for s in skills)
        chunks.append({
            "chunk_text": skills_text,
            "chunk_type": "skills",
            "metadata": {"skill_count": len(skills)}
        })

    # Experience chunks (one per role)
    experience = resume_parsed.get("experience_entries", [])
    for i, exp in enumerate(experience):
        exp_text = f"Role: {exp.get('role', '')} at {exp.get('company', '')}. "
        exp_text += f"Duration: {exp.get('duration', '')}. "
        exp_text += "Key claims: " + "; ".join(exp.get("key_claims", []))
        chunks.append({
            "chunk_text": exp_text,
            "chunk_type": "experience",
            "metadata": {
                "role": exp.get("role", ""),
                "company": exp.get("company", ""),
                "index": i
            }
        })

    # Projects chunks
    projects = resume_parsed.get("projects", [])
    for i, proj in enumerate(projects):
        proj_text = f"Project: {proj.get('name', '')}. "
        proj_text += "Technologies: " + ", ".join(proj.get("technologies", [])) + ". "
        proj_text += "Impact: " + proj.get("claimed_impact", "")
        chunks.append({
            "chunk_text": proj_text,
            "chunk_type": "projects",
            "metadata": {
                "project_name": proj.get("name", ""),
                "technologies": proj.get("technologies", []),
                "index": i
            }
        })

    # Education chunk
    education = resume_parsed.get("education", [])
    if education:
        edu_text = "Education: " + "; ".join(
            f"{e.get('degree', '')} from {e.get('institution', '')} ({e.get('year', '')})"
            for e in education
        )
        chunks.append({
            "chunk_text": edu_text,
            "chunk_type": "education",
            "metadata": {"degree_count": len(education)}
        })

    # Summary chunk
    summary = resume_parsed.get("summary", "")
    if summary:
        chunks.append({
            "chunk_text": f"Summary: {summary}",
            "chunk_type": "summary",
            "metadata": {}
        })

    return chunks


def store_resume_embeddings(
    session_id: str,
    candidate_email: str,
    resume_parsed: dict
) -> int:
    """
    Generate and store embeddings for all resume chunks.

    Returns number of chunks stored.
    """
    model = get_embedding_model()
    if model is None:
        logger.warning("Embedding model not available, skipping vector storage")
        return 0

    chunks = chunk_resume_for_embedding(resume_parsed)
    if not chunks:
        return 0

    conn = get_connection()
    stored = 0
    try:
        c = conn.cursor()
        now = time.time()

        for chunk in chunks:
            embedding = generate_embedding(chunk["chunk_text"])
            if embedding is None:
                continue

            c.execute("""
                INSERT INTO resume_embeddings
                (session_id, candidate_email, chunk_text, chunk_type, embedding, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            """, (
                session_id,
                candidate_email,
                chunk["chunk_text"],
                chunk["chunk_type"],
                json.dumps(embedding),
                json.dumps(chunk["metadata"]),
                now,
            ))
            stored += 1

        conn.commit()
        logger.info("Stored %d resume embeddings for %s", stored, candidate_email)
    finally:
        release_connection(conn)

    return stored


def search_similar_resumes(
    query_text: str,
    candidate_email: str | None = None,
    top_k: int = 10,
    chunk_types: list[str] | None = None,
    min_similarity: float = 0.3
) -> list[dict]:
    """
    Search for resume chunks similar to the query text.

    Returns list of dicts with: session_id, candidate_email, chunk_text, chunk_type, similarity, metadata
    """
    model = get_embedding_model()
    if model is None:
        logger.warning("Embedding model not available, returning empty results")
        return []

    query_embedding = generate_embedding(query_text)
    if query_embedding is None:
        return []

    conn = get_connection()
    try:
        c = conn.cursor()

        # Build query
        where_clauses = []
        params = []

        if candidate_email:
            where_clauses.append("candidate_email = %s")
            params.append(candidate_email)

        if chunk_types:
            placeholders = ", ".join(["%s"] * len(chunk_types))
            where_clauses.append(f"chunk_type IN ({placeholders})")
            params.extend(chunk_types)

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        c.execute(f"""
            SELECT session_id, candidate_email, chunk_text, chunk_type, embedding, metadata
            FROM resume_embeddings
            {where_sql}
        """, params)

        results = []
        for row in c.fetchall():
            session_id, cand_email, chunk_text, chunk_type, embedding_json, metadata = row
            embedding = embedding_json if isinstance(embedding_json, list) else json.loads(embedding_json)
            similarity = _cosine_similarity(query_embedding, embedding)

            if similarity >= min_similarity:
                results.append({
                    "session_id": session_id,
                    "candidate_email": cand_email,
                    "chunk_text": chunk_text,
                    "chunk_type": chunk_type,
                    "similarity": similarity,
                    "metadata": metadata if isinstance(metadata, dict) else json.loads(metadata),
                })

        # Sort by similarity descending and return top_k
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    finally:
        release_connection(conn)


def find_candidates_for_role(
    role_description: str,
    required_skills: list[str] | None = None,
    top_k: int = 20,
    min_similarity: float = 0.4
) -> list[dict]:
    """
    Find candidates matching a role description and required skills.

    Returns aggregated results per candidate with average similarity and skill match info.
    """
    # Search for relevant chunks
    chunk_types = ["skills", "experience", "projects"] if required_skills else None
    chunk_results = search_similar_resumes(
        role_description,
        top_k=top_k * 3,  # Get more chunks to aggregate
        chunk_types=chunk_types,
        min_similarity=min_similarity
    )

    if not chunk_results:
        return []

    # Aggregate by candidate
    candidate_scores: dict[str, dict] = {}
    for r in chunk_results:
        email = r["candidate_email"]
        if email not in candidate_scores:
            candidate_scores[email] = {
                "candidate_email": email,
                "session_ids": set(),
                "chunk_matches": [],
                "total_similarity": 0.0,
                "match_count": 0,
            }
        cs = candidate_scores[email]
        cs["session_ids"].add(r["session_id"])
        cs["chunk_matches"].append({
            "chunk_type": r["chunk_type"],
            "similarity": r["similarity"],
            "text": r["chunk_text"][:200],
        })
        cs["total_similarity"] += r["similarity"]
        cs["match_count"] += 1

    # Calculate averages and skill matches
    final_results = []
    for email, data in candidate_scores.items():
        avg_sim = data["total_similarity"] / data["match_count"] if data["match_count"] > 0 else 0

        # Skill matching
        skill_matches = []
        skill_gaps = []
        if required_skills:
            # Get all skill chunks for this candidate
            skill_chunks = [m for m in data["chunk_matches"] if m["chunk_type"] == "skills"]
            skill_text = " ".join(c["text"] for c in skill_chunks).lower()
            for skill in required_skills:
                if skill.lower() in skill_text:
                    skill_matches.append(skill)
                else:
                    skill_gaps.append(skill)

        final_results.append({
            "candidate_email": email,
            "session_ids": list(data["session_ids"]),
            "avg_similarity": round(avg_sim, 3),
            "match_count": data["match_count"],
            "top_matches": data["chunk_matches"][:5],
            "skill_matches": skill_matches,
            "skill_gaps": skill_gaps,
            "skill_match_ratio": round(len(skill_matches) / len(required_skills), 2) if required_skills else 1.0,
        })

    # Sort by combined score: similarity * skill_match_ratio
    final_results.sort(
        key=lambda x: x["avg_similarity"] * x["skill_match_ratio"],
        reverse=True
    )

    return final_results[:top_k]


def store_job_embedding(
    job_id: str,
    title: str,
    company: str | None,
    description: str,
    required_skills: list[str] | None = None
) -> bool:
    """Store a job description embedding for skill gap analysis."""
    model = get_embedding_model()
    if model is None:
        return False

    embedding = generate_embedding(description)
    if embedding is None:
        return False

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO job_embeddings
            (job_id, title, company, description, embedding, required_skills, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (job_id) DO UPDATE SET
                title=EXCLUDED.title,
                company=EXCLUDED.company,
                description=EXCLUDED.description,
                embedding=EXCLUDED.embedding,
                required_skills=EXCLUDED.required_skills
        """, (
            job_id,
            title,
            company,
            description,
            json.dumps(embedding),
            json.dumps(required_skills or []),
            time.time(),
        ))
        conn.commit()
        return True
    finally:
        release_connection(conn)


def analyze_skill_gap(candidate_email: str, job_id: str) -> dict | None:
    """
    Analyze skill gap between a candidate and a job description.
    """
    conn = get_connection()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get job data
        c.execute("SELECT * FROM job_embeddings WHERE job_id = %s", (job_id,))
        job = c.fetchone()
        if not job:
            return None

        required_skills = job["required_skills"] if isinstance(job["required_skills"], list) else json.loads(job["required_skills"])

        # Get candidate's skill chunks
        c.execute("""
            SELECT chunk_text, embedding FROM resume_embeddings
            WHERE candidate_email = %s AND chunk_type = 'skills'
        """, (candidate_email,))

        skill_chunks = c.fetchall()
        if not skill_chunks:
            return {
                "candidate_email": candidate_email,
                "job_id": job_id,
                "required_skills": required_skills,
                "matched_skills": [],
                "missing_skills": required_skills,
                "match_percentage": 0.0,
            }

        # Check each required skill against candidate's skill embeddings
        matched = []
        missing = []
        job_embedding = job["embedding"] if isinstance(job["embedding"], list) else json.loads(job["embedding"])

        for skill in required_skills:
            skill_embedding = generate_embedding(skill)
            if not skill_embedding:
                continue

            # Find max similarity with candidate's skill chunks
            max_sim = 0.0
            for chunk in skill_chunks:
                chunk_emb = chunk["embedding"] if isinstance(chunk["embedding"], list) else json.loads(chunk["embedding"])
                sim = _cosine_similarity(skill_embedding, chunk_emb)
                max_sim = max(max_sim, sim)

            if max_sim >= 0.5:  # Threshold for considering a skill matched
                matched.append({"skill": skill, "confidence": round(max_sim, 2)})
            else:
                missing.append({"skill": skill, "best_match_score": round(max_sim, 2)})

        match_pct = len(matched) / len(required_skills) * 100 if required_skills else 100

        return {
            "candidate_email": candidate_email,
            "job_id": job_id,
            "job_title": job["title"],
            "company": job["company"],
            "required_skills": required_skills,
            "matched_skills": matched,
            "missing_skills": missing,
            "match_percentage": round(match_pct, 1),
            "total_required": len(required_skills),
            "total_matched": len(matched),
        }
    finally:
        release_connection(conn)


def get_candidate_profile_vector(candidate_email: str) -> list[float] | None:
    """Get an aggregated profile vector for a candidate (average of all their embeddings)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT embedding FROM resume_embeddings WHERE candidate_email = %s", (candidate_email,))
        rows = c.fetchall()
        if not rows:
            return None

        embeddings = []
        for row in rows:
            emb = row[0] if isinstance(row[0], list) else json.loads(row[0])
            embeddings.append(emb)

        if not embeddings:
            return None

        # Average the embeddings
        avg_emb = np.mean(np.array(embeddings), axis=0)
        return avg_emb.tolist()
    finally:
        release_connection(conn)


def find_similar_candidates(candidate_email: str, top_k: int = 10) -> list[dict]:
    """Find candidates with similar profiles to the given candidate."""
    profile_vec = get_candidate_profile_vector(candidate_email)
    if not profile_vec:
        return []

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT candidate_email FROM resume_embeddings
            WHERE candidate_email != %s
        """, (candidate_email,))

        results = []
        for row in c.fetchall():
            other_email = row[0]
            other_vec = get_candidate_profile_vector(other_email)
            if not other_vec:
                continue
            sim = _cosine_similarity(profile_vec, other_vec)
            if sim > 0.5:
                results.append({
                    "candidate_email": other_email,
                    "similarity": round(sim, 3),
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
    finally:
        release_connection(conn)