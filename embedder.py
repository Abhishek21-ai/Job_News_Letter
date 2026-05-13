"""
embedder.py
Semantic similarity engine using local sentence-transformers.
Zero API cost. No network calls. Runs entirely in-process.

Model: all-MiniLM-L6-v2
- 22MB download (cached after first run)
- ~384-dim embeddings
- Excellent for short-to-medium text semantic similarity

Key design: Query Expansion
  Instead of embedding a flat list of skills, we construct a
  natural-language "ideal job description" from the profile.
  This puts the resume in the same semantic space as JDs,
  so even sparse or vaguely-written job descriptions match correctly.
"""

from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

_MODEL: SentenceTransformer | None = None
PROFILE_PATH = Path("resume_profile.json")


# ──────────────────────────────────────────────────────────────────────────────
# MODEL
# ──────────────────────────────────────────────────────────────────────────────

def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        print("📦 Loading sentence-transformer model...")
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        print("  ✅ Model loaded.")
    return _MODEL


def embed(texts: list[str]) -> np.ndarray:
    return _get_model().encode(texts, convert_to_numpy=True, show_progress_bar=False)


# ──────────────────────────────────────────────────────────────────────────────
# QUERY EXPANSION — fixes semantic mismatch with sparse JDs
# ──────────────────────────────────────────────────────────────────────────────

def build_resume_embedding_text() -> str:
    """
    Constructs a natural-language "ideal job description" from the
    resume profile JSON.

    WHY: Embedding a flat list of skills ("Python FastAPI Kafka Azure...")
    produces a vector in skills-space. Job descriptions live in
    role-description-space. These spaces don't align well, so similarity
    scores are artificially low for relevant jobs.

    By rephrasing as "Looking for a role as X with experience in Y...",
    the resume vector lands in the same semantic neighbourhood as JDs.
    Even a sparse JD saying "Python backend engineer, 1-2 years" will
    score correctly.
    """
    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    roles     = ", ".join(profile.get("primary_roles", []))
    skills    = ", ".join(profile.get("skills", []))
    domains   = ", ".join(profile.get("preferred_domains", []))
    strengths = ", ".join(profile.get("core_strengths", []))
    exp_level = profile.get("experience_level", "1-2 years")
    seniority = profile.get("seniority", "junior")
    locations = ", ".join(profile.get("target_locations", ["India"]))
    certs     = ", ".join(profile.get("certifications", []))

    # Natural-language query expansion — reads like a job seeker's summary,
    # not a keyword list. Lands in the same embedding space as job descriptions.
    text = (
        f"Looking for a {seniority}-level position as {roles}. "
        f"I have {exp_level} of industry experience in {domains}. "
        f"My core technical skills include {skills}. "
        f"Key strengths: {strengths}. "
        f"Open to roles in {locations}. "
        f"Certifications: {certs}. "
        f"Prefer entry-level to mid-level backend engineering, "
        f"data engineering, or platform engineering roles requiring "
        f"Python, FastAPI, Databricks, PySpark, Kafka, or Azure."
    )

    return text


def build_resume_embedding(resume_text: str) -> np.ndarray:
    print("🧠 Generating resume embedding...")
    vec = embed([resume_text])[0]
    print("  ✅ Resume embedding ready.")
    return vec


# ──────────────────────────────────────────────────────────────────────────────
# JOB TEXT CONSTRUCTION
# ──────────────────────────────────────────────────────────────────────────────

def build_job_texts(jobs: list[dict]) -> list[str]:
    """
    Builds rich text per job for embedding.
    Uses 600 chars of description (more signal for sparse JDs).
    Omits company name — noise, not signal.
    Omits seniorityLevel — LinkedIn's value is unreliable for
    contract/freelance-posted roles. Title + JD body is cleaner.
    """
    texts = []
    for job in jobs:
        title       = job.get("title", "")
        description = (job.get("descriptionText") or "")[:600]
        text = f"Job title: {title}. {description}"
        texts.append(text)
    return texts


# ──────────────────────────────────────────────────────────────────────────────
# SIMILARITY RANKING
# ──────────────────────────────────────────────────────────────────────────────

def rank_jobs_by_similarity(
    resume_embedding: np.ndarray,
    jobs: list[dict],
    top_n: int = 10,
) -> list[dict]:
    """
    Cosine similarity between resume embedding and each job embedding.
    Returns top_n jobs with 'similarity_score' attached.
    """
    if not jobs:
        return []

    print(f"🔎 Embedding {len(jobs)} job descriptions...")

    job_texts      = build_job_texts(jobs)
    job_embeddings = embed(job_texts)

    resume_norm = resume_embedding / (np.linalg.norm(resume_embedding) + 1e-9)
    jobs_norm   = job_embeddings   / (np.linalg.norm(job_embeddings, axis=1, keepdims=True) + 1e-9)
    similarities = jobs_norm @ resume_norm

    for job, sim in zip(jobs, similarities):
        job["similarity_score"] = round(float(sim), 4)

    ranked = sorted(jobs, key=lambda j: j["similarity_score"], reverse=True)
    top    = ranked[:top_n]

    print(f"  ✅ Top {len(top)} jobs by semantic similarity.")
    print(f"     Range: {top[-1]['similarity_score']:.3f} → {top[0]['similarity_score']:.3f}")

    return top
