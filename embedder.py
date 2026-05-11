"""
embedder.py
Semantic similarity engine using local sentence-transformers.
Zero API cost. No network calls. Runs entirely in-process.

Model: all-MiniLM-L6-v2
- 22MB download (cached after first run)
- ~384-dim embeddings
- Excellent for short-to-medium text semantic similarity
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer
import json
from pathlib import Path

# Loaded once per process — GitHub Actions caches the model between runs
# via the actions/cache step (see README for cache config)
_MODEL: SentenceTransformer | None = None

PROFILE_PATH = Path("resume_profile.json")


def build_resume_embedding_text() -> str:
    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    text = []

    text.extend(profile.get("primary_roles", []))
    text.extend(profile.get("skills", []))
    text.extend(profile.get("preferred_domains", []))

    text.append(profile.get("experience_level", ""))

    return " ".join(text)


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        print("📦 Loading sentence-transformer model (first run may take ~10s)...")
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        print("  ✅ Model loaded.")
    return _MODEL


def embed(texts: list[str]) -> np.ndarray:
    """
    Embed a list of strings.
    Returns shape (N, 384) float32 array.
    """
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def build_resume_embedding(resume_summary: str) -> np.ndarray:
    """
    Generate a single embedding vector for the resume profile.
    Returns shape (384,) float32 array.
    """
    print("🧠 Generating resume embedding...")
    vec = embed([resume_summary])[0]
    print("  ✅ Resume embedding ready.")
    return vec


def build_job_texts(jobs: list[dict]) -> list[str]:
    """
    Construct a rich text representation of each job for embedding.
    Combines title + seniority + description for best semantic coverage.
    Truncates description to 512 chars — enough signal, keeps it fast.
    """
    texts = []
    for job in jobs:
        title       = job.get("title", "")
        company     = job.get("companyName", "")
        seniority   = job.get("seniorityLevel", "")
        description = (job.get("descriptionText") or "")[:512]

        text = f"{title} at {company}. {seniority}. {description}"
        texts.append(text)
    return texts


def rank_jobs_by_similarity(
    resume_embedding: np.ndarray,
    jobs: list[dict],
    top_n: int = 10,
) -> list[dict]:
    """
    Computes cosine similarity between resume embedding and each job embedding.
    Returns top_n jobs sorted by similarity score (descending),
    with 'similarity_score' added to each job dict.

    Cosine similarity:
        sim(A, B) = (A · B) / (||A|| * ||B||)
    Range: [-1, 1] — in practice for these embeddings: [0.0, 1.0]
    """
    if not jobs:
        return []

    print(f"🔎 Embedding {len(jobs)} job descriptions...")

    job_texts      = build_job_texts(jobs)
    job_embeddings = embed(job_texts)          # shape: (N, 384)

    # Normalise both sides for clean cosine similarity via dot product
    resume_norm = resume_embedding / (np.linalg.norm(resume_embedding) + 1e-9)
    jobs_norm   = job_embeddings   / (np.linalg.norm(job_embeddings, axis=1, keepdims=True) + 1e-9)

    similarities = jobs_norm @ resume_norm     # shape: (N,)

    # Attach similarity score to each job
    for job, sim in zip(jobs, similarities):
        job["similarity_score"] = round(float(sim), 4)

    # Sort descending and return top_n
    ranked = sorted(jobs, key=lambda j: j["similarity_score"], reverse=True)
    top    = ranked[:top_n]

    print(f"  ✅ Top {len(top)} jobs selected by semantic similarity.")
    print(f"     Score range: {top[-1]['similarity_score']:.3f} → {top[0]['similarity_score']:.3f}")

    return top
