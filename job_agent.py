"""
Job Newsletter Agent — Phase 2.1
Pipeline:
  Scrape → Dedup → Prefilter → Embed → Similarity Rank
  → Groq Score → [Diagnoser → Recruiter → Rewriter] → Newsletter

Three-actor intelligence layer triggers only when score >= MIN_SCORE:
  Diagnoser : ATS weak-area analysis
  Recruiter : gap analysis vs popular JDs in target role
  Rewriter  : tailored resume rewrite (XYZ formula, preserves structure)
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

from email_sender import send_newsletter
from embedder import build_resume_embedding, rank_jobs_by_similarity, build_resume_embedding_text

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG — all values from GitHub Secrets
# ──────────────────────────────────────────────────────────────────────────────

APIFY_TOKEN     = os.environ["APIFY_TOKEN"]
GROQ_API_KEY    = os.environ["GROQ_API_KEY"]
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]
SENDER_EMAIL    = os.environ["SENDER_EMAIL"]
EMAIL_API_KEY   = os.environ["EMAIL_API_KEY"]
EMAIL_PROVIDER  = os.environ.get("EMAIL_PROVIDER", "resend")
MIN_SCORE       = int(os.environ.get("MIN_SCORE", "75"))
TOP_N           = int(os.environ.get("TOP_N", "5"))
EMBEDDING_TOP_N = int(os.environ.get("EMBEDDING_TOP_N", "10"))

# Stored in secrets to override LLM inference — prevents freelance/consulting
# history from inflating experience level incorrectly.
CANDIDATE_EXPERIENCE = os.environ.get("CANDIDATE_EXPERIENCE", "1.5 years").strip()
# entry | junior | mid — overrides LinkedIn seniorityLevel which is unreliable
CANDIDATE_SENIORITY  = os.environ.get("CANDIDATE_SENIORITY", "junior").strip()

PROFILE_PATH = Path("resume_profile.json")

# ──────────────────────────────────────────────────────────────────────────────
# LOAD RESUME PROFILE
# ──────────────────────────────────────────────────────────────────────────────

def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            "resume_profile.json not found. "
            "Set REGENERATE_RESUME=true and run once to generate it."
        )
    with open(PROFILE_PATH) as f:
        return json.load(f)


def build_candidate_context(profile: dict) -> str:
    """
    Builds a rich candidate context string for all Groq prompts.
    Uses CANDIDATE_EXPERIENCE and CANDIDATE_SENIORITY from secrets
    instead of profile-inferred values (which can be wrong for freelancers).
    """
    return f"""
Candidate: {profile.get('name', 'Candidate')}
Experience: {CANDIDATE_EXPERIENCE} industry experience (excluding freelance/consulting)
Seniority: {CANDIDATE_SENIORITY}-level
Primary Roles: {', '.join(profile.get('primary_roles', []))}
Skills: {', '.join(profile.get('skills', []))}
Core Strengths: {', '.join(profile.get('core_strengths', []))}
Domains: {', '.join(profile.get('preferred_domains', []))}
Certifications: {', '.join(profile.get('certifications', []))}
Education: {profile.get('education', '')}
Target Locations: {', '.join(profile.get('target_locations', []))}
""".strip()

# ──────────────────────────────────────────────────────────────────────────────
# LINKEDIN SEARCH URLS
# f_TPR=r43200 = last 12 hours | f_WT=2 = Remote
#
# NOTE: f_E (seniority filter) intentionally removed from all URLs.
# In India, most companies don't set seniority level correctly when posting.
# A genuine 0-2yr Data Engineer role is often posted with no tag or tagged as
# "Associate" (f_E=3) instead of "Entry" (f_E=2), causing valid jobs to be
# silently dropped before Apify even scrapes them.
# Seniority is enforced downstream via SENIOR_TITLE_KEYWORDS + Groq scorer.
#
# Two URLs per location: exact role + broader Python keyword.
# Broader URLs catch roles posted as "Python Developer" or "Software Engineer"
# that are actually data/backend engineering positions.
# ──────────────────────────────────────────────────────────────────────────────

LINKEDIN_SEARCH_URLS = [
    # ── PUNE ─────────────────────────────────────────────────────────────────
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r43200",
    "https://www.linkedin.com/jobs/search/?keywords=Python%20Backend%20Engineer&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r43200",
    "https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r43200",

    # ── BANGALORE ────────────────────────────────────────────────────────────
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r43200",
    "https://www.linkedin.com/jobs/search/?keywords=Python%20Backend%20Engineer&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r43200",
    "https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r43200",

    # ── HYDERABAD ────────────────────────────────────────────────────────────
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r43200",
    "https://www.linkedin.com/jobs/search/?keywords=Python%20Backend%20Engineer&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r43200",

    # ── REMOTE INDIA ──────────────────────────────────────────────────────────
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer%20Python&location=India&f_TPR=r43200&f_WT=2",
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python&location=India&f_TPR=r43200&f_WT=2",
    "https://www.linkedin.com/jobs/search/?keywords=Associate%20Data%20Engineer&location=India&f_TPR=r43200",
]

# ──────────────────────────────────────────────────────────────────────────────
# FILTER RULES
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# FILTER RULES
# ──────────────────────────────────────────────────────────────────────────────

RELEVANT_KEYWORDS = [
    "python",
    "fastapi",
    "backend",
    "backend engineer",
    "backend developer",
    "data engineer",
    "associate data engineer",
    "databricks",
    "pyspark",
    "spark",
    "kafka",
    "postgresql",
    "etl",
    "azure",
]

# Title-level seniority words — these override LinkedIn's unreliable field.
# Checked ONLY against title.
SENIOR_TITLE_KEYWORDS = [
    "senior",
    "sr.",
    "lead",
    "principal",
    "staff",
    "architect",
    "manager",
    "director",
    "head of",
    "vp ",
    "vice president",
    "10+ years",
    "12+ years",
    "8+ years",
]

# Roles/domains we DO NOT want even if stack partially overlaps.
# This is extremely important because embeddings can incorrectly
# rank adjacent AI/analytics/networking jobs highly.
NEGATIVE_TITLE_KEYWORDS = [
    # AI / ML / DS
    "data scientist",
    "ai engineer",
    "ml engineer",
    "machine learning",
    "deep learning",
    "genai",
    "llm engineer",
    "prompt engineer",
    "computer vision",
    "nlp engineer",
    "research engineer",
    "research scientist",

    # Analytics / BI
    "visualization analyst",
    "bi analyst",
    "business analyst",
    "data analyst",
    "reporting analyst",
    "tableau",
    "power bi",
    "analytics consultant",

    # Infra / Networking
    "network engineer",
    "system engineer",
    "infrastructure engineer",
    "devops engineer",
    "site reliability engineer",
    "sre",
    "cloud support",

    # QA / Support
    "qa engineer",
    "test engineer",
    "automation tester",
    "support engineer",

    # Frontend / Mobile
    "frontend",
    "ui engineer",
    "ux engineer",
    "react native",
    "android",
    "ios",

    # Non-target backend ecosystems
    "java developer",
    ".net developer",
    "php developer",
    "golang developer",
]

NEGATIVE_STACK_KEYWORDS = [
    "java",
    "spring",
    "springboot",
    ".net",
    "dotnet",
    "php",
    "android",
    "ios",
    "react native",
    "golang",
    "ruby on rails",
]

# Title-level role exclusions — blocks adjacent roles whose descriptions
# mention Python/Databricks incidentally but are the wrong domain entirely.
NEGATIVE_TITLE_KEYWORDS = [
    "data scientist",
    "data science",
    "data analyst",
    "data coach",
    "machine learning",
    "ml engineer",
    "ai and ml",
    "network engineer",
    "visualization",
    "visualisation",
    "devops",
    "site reliability",
    "sre",
    "security engineer",
    "power bi",
    "tableau",
    "business analyst",
    "business intelligence",
    "bi developer",
    "bi analyst",
    "salesforce",
    "qa engineer",
    "test engineer",
    "scrum master",
    "product manager",
    "project manager",
]

# Strong positive title signals.
# At least ONE should exist in title to reduce embedding drift.
TARGET_TITLE_KEYWORDS = [
    "backend engineer",
    "backend developer",
    "python developer",
    "python engineer",
    "data engineer",
    "associate data engineer",
    "platform engineer",
    "software engineer",
    "backend",
    "python",
    "data engineer",
    "software engineer",
    "platform engineer",
    "api",
    "distributed systems",
]

# ──────────────────────────────────────────────────────────────────────────────
# SCRAPE
# ──────────────────────────────────────────────────────────────────────────────

def scrape_linkedin_jobs() -> list[dict]:
    print("🔍 Scraping LinkedIn jobs via Apify...")

    run_url = (
        "https://api.apify.com/v2/acts/"
        f"curious_coder~linkedin-jobs-scraper/runs?token={APIFY_TOKEN}"
    )
    resp = requests.post(
        run_url,
        json={"urls": LINKEDIN_SEARCH_URLS, "count": 50, "scrapeCompany": False},
        timeout=30,
    )
    resp.raise_for_status()
    run_id = resp.json()["data"]["id"]
    print(f"  Actor run started: {run_id}")

    status_resp = {}
    for _ in range(36):
        time.sleep(5)
        status_resp = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"
        ).json()
        status = status_resp["data"]["status"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify run failed: {status}")

    dataset_id = status_resp["data"]["defaultDatasetId"]
    jobs = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        f"?token={APIFY_TOKEN}&limit=100"
    ).json()

    print(f"  Retrieved {len(jobs)} raw jobs")
    return jobs

# ──────────────────────────────────────────────────────────────────────────────
# DEDUP
# ──────────────────────────────────────────────────────────────────────────────

def deduplicate(jobs: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for job in jobs:
        key = f"{job.get('title','').strip().lower()}|{job.get('companyName','').strip().lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    print(f"  After dedup: {len(unique)} jobs")
    return unique

# ──────────────────────────────────────────────────────────────────────────────
# PREFILTER
# Much stricter title filtering BEFORE embeddings.
# Prevents adjacent domains from reaching semantic ranking.
# ──────────────────────────────────────────────────────────────────────────────

def prefilter_jobs(jobs: list[dict]) -> list[dict]:
    filtered = []

    for job in jobs:
        title = (job.get("title") or "").lower().strip()
        desc  = (job.get("descriptionText") or "").lower()
        full  = f"{title} {desc}"

        # ── HARD REJECTION: seniority ─────────────────────────
        if any(k in title for k in SENIOR_TITLE_KEYWORDS):
            continue

        # ── HARD REJECTION: unwanted role/domain ──────────────
        if any(k in title for k in NEGATIVE_TITLE_KEYWORDS):
            continue

        # ── HARD REJECTION: wrong stack ───────────────────────
        if any(k in full for k in NEGATIVE_STACK_KEYWORDS):
            continue

        # ── TITLE MUST MATCH TARGET ROLE ──────────────────────
        # This is the biggest improvement.
        # Prevents semantic search from drifting into AI/ML/Analytics.
        if not any(k in title for k in TARGET_TITLE_KEYWORDS):
            continue

        # ── Must contain at least one relevant tech signal ────
        if not any(k in full for k in RELEVANT_KEYWORDS):
            continue

        filtered.append(job)

    print(f"🔍 Prefiltered to {len(filtered)} relevant jobs")
    return filtered

# ──────────────────────────────────────────────────────────────────────────────
# GROQ HELPER
# ──────────────────────────────────────────────────────────────────────────────

def groq_request(body: dict, retries: int = 5) -> dict:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(retries):
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30,
        )
        if r.status_code == 429:
            wait = 2 ** attempt
            print(f"    ⏳ Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise Exception("Groq rate limit exceeded after retries")


def groq_json(system: str, user: str, max_tokens: int = 400) -> dict:
    """Single helper for all JSON-returning Groq calls."""
    resp = groq_request({
        "model": "llama-3.1-8b-instant",
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    })
    raw   = resp["choices"][0]["message"]["content"].strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in Groq response: {raw[:200]}")
    return json.loads(match.group())


def groq_text(system: str, user: str, max_tokens: int = 800) -> str:
    """Single helper for all plain-text Groq calls (resume rewriter)."""
    resp = groq_request({
        "model": "llama-3.1-8b-instant",
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    })
    return resp["choices"][0]["message"]["content"].strip()

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 0 — SCORER
# ──────────────────────────────────────────────────────────────────────────────

def score_job(job: dict, candidate_context: str) -> dict:
    title       = job.get("title", "")
    company     = job.get("companyName", "")
    description = (job.get("descriptionText") or "")[:800]
    sim_score   = job.get("similarity_score", "N/A")

    prompt = f"""
You are a strict recruiter scoring candidate-job compatibility.

CANDIDATE:
{candidate_context}

JOB:
Title: {title}
Company: {company}
Semantic Similarity (pre-computed, 0-1): {sim_score}
Description:
{description}

SCORING RULES:
- Score 80-100: Strong stack match (Python/FastAPI/Databricks/Kafka/Azure) + correct seniority
- Score 65-79:  Partial match — relevant domain but some stack mismatch
- Score 50-64:  Weak match — adjacent role or too senior
- Score <50:    Skip — wrong stack or clearly too senior

IMPORTANT: The candidate has {CANDIDATE_EXPERIENCE} of industry experience.
Do NOT penalise for missing 3+ years if the job only requires 0-2 years.
Do NOT score high if the job clearly requires 5+ years.

Return ONLY valid JSON:
{{
  "score": 0-100,
  "verdict": "Strong Match | Moderate Match | Weak Match | Skip",
  "match_reasons": ["reason1", "reason2", "reason3"],
  "gap": "single biggest missing skill or requirement",
  "exp_required": "experience range from JD"
}}
"""
    try:
        scoring = groq_json(
            system="You are a strict JSON generator. Return ONLY valid JSON. No markdown.",
            user=prompt,
            max_tokens=350,
        )
    except Exception as e:
        print(f"    ⚠ Scorer failed for '{title}': {e}")
        scoring = {
            "score": 0, "verdict": "Skip",
            "match_reasons": [], "gap": "Scoring error",
            "exp_required": "?",
        }

    return {**job, **scoring}


def score_all_jobs(jobs: list[dict], candidate_context: str) -> list[dict]:
    print(f"🤖 Scoring {len(jobs)} jobs with Groq...")
    scored = []
    for i, job in enumerate(jobs):
        title   = job.get("title", "?")
        company = job.get("companyName", "?")
        sim     = job.get("similarity_score", "?")
        link    = job.get("applyUrl") or job.get("link", "no link")

        print(f"\n  [{i+1}/{len(jobs)}] {title} @ {company}")
        print(f"    sim: {sim} | 🔗 {link}")

        result = score_job(job, candidate_context)
        scored.append(result)

        groq_score = result.get("score", "?")
        verdict    = result.get("verdict", "?")
        gap        = result.get("gap", "?")
        exp_req    = result.get("exp_required", "?")
        reasons    = result.get("match_reasons", [])
        threshold  = "✅ QUALIFIES" if isinstance(groq_score, int) and groq_score >= MIN_SCORE else "❌ below threshold"

        print(f"    score: {groq_score}/100 ({verdict}) {threshold}")
        print(f"    exp required: {exp_req}")
        print(f"    gap: {gap}")
        for r in reasons:
            print(f"    + {r}")

        # 7s gap keeps TPM under Groq free tier (~600 tokens/call)
        if i < len(jobs) - 1:
            time.sleep(7)

    return scored

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 1 — DIAGNOSER
# Acts as an ATS system. Identifies weak areas in the candidate profile
# relative to this specific job. Triggers only for score >= MIN_SCORE.
# ──────────────────────────────────────────────────────────────────────────────

def run_diagnoser(job: dict, candidate_context: str) -> dict:
    """
    Reads the JD line by line and extracts every required skill, tool,
    and keyword. Then cross-checks each one against the candidate profile.
    Gap = what the JD explicitly requires that the candidate does NOT have.
    Never flags resume skills as gaps — only JD requirements.
    Also scores the CURRENT resume ATS match before rewriting.
    """
    title       = job.get("title", "")
    company     = job.get("companyName", "")
    description = (job.get("descriptionText") or "")[:1200]

    prompt = f"""
You are a senior ATS system doing a strict JD-vs-resume match analysis.

YOUR ONLY JOB: Compare the JD requirements against the candidate profile.
A gap = something the JD REQUIRES that the candidate does NOT have.
A gap is NEVER a skill the candidate has that the JD doesn't mention.

STEP 1 — Extract from the JD every required skill, tool, technology, and keyword.
STEP 2 — For each extracted requirement, check if the candidate has it.
STEP 3 — Missing = required by JD but absent from candidate. Present = candidate has it.
STEP 4 — Score the current resume ATS match based on coverage of JD requirements.

CANDIDATE PROFILE:
{candidate_context}

JOB TITLE: {title} at {company}
FULL JOB DESCRIPTION:
{description}

RULES:
- missing_keywords: ONLY keywords that appear in the JD AND are absent from the candidate
- weak_areas: ONLY genuine gaps between JD requirements and candidate profile
- Do NOT flag FastAPI as missing if the JD does not mention FastAPI
- Do NOT flag any candidate skill as a gap — gaps come from the JD only
- strong_areas: candidate skills that the JD explicitly requires or strongly prefers
- ats_score: percentage of JD requirements the current resume covers (0-100)
- ats_verdict: one specific sentence citing the biggest actual gap from the JD

Return ONLY valid JSON:
{{
  "ats_score": 0-100,
  "jd_required_skills": ["every skill/tool explicitly required in the JD"],
  "missing_keywords": ["JD-required skills absent from candidate — JD source only"],
  "present_keywords": ["JD-required skills the candidate already has"],
  "weak_areas": ["specific JD requirement the candidate does not meet"],
  "strong_areas": ["candidate strengths that directly match JD requirements"],
  "ats_verdict": "one specific sentence about the biggest real gap from this JD"
}}
"""
    try:
        result = groq_json(
            system=(
                "You are a strict ATS evaluator. "
                "Gaps come ONLY from JD requirements, never from candidate skills. "
                "Return ONLY valid JSON."
            ),
            user=prompt,
            max_tokens=600,
        )
    except Exception as e:
        print(f"    ⚠ Diagnoser failed: {e}")
        result = {
            "ats_score": 0, "jd_required_skills": [], "missing_keywords": [],
            "present_keywords": [], "weak_areas": [],
            "strong_areas": [], "ats_verdict": "Analysis unavailable",
        }

    time.sleep(1)
    return result

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 2 — RECRUITER
# Analyses the resume against what's typically required for this role
# based on the JD. Surfaces what's missing vs what popular JDs expect.
# ──────────────────────────────────────────────────────────────────────────────

def run_recruiter(job: dict, candidate_context: str) -> dict:
    """
    Reads THIS JD specifically — not generic role expectations.
    Scores fit based on what this company explicitly wants.
    Quick wins are tied to THIS JD's requirements, not industry averages.
    PySpark === Apache Spark — never flags synonyms as missing.
    """
    title       = job.get("title", "")
    company     = job.get("companyName", "")
    description = (job.get("descriptionText") or "")[:1200]

    prompt = f"""
You are a senior technical recruiter evaluating a candidate for THIS specific job.
You are NOT giving generic career advice. You are assessing fit for this one JD.

CANDIDATE PROFILE:
{candidate_context}

THIS SPECIFIC JOB: {title} at {company}
FULL JOB DESCRIPTION:
{description}

STRICT RULES:
1. Base ALL analysis on what THIS JD says — not industry generalizations
2. Treat synonyms as equivalent: PySpark = Apache Spark, Postgres = PostgreSQL,
   Kafka = Apache Kafka, ADF = Azure Data Factory, ADLS = Azure Data Lake Storage
3. commonly_required_missing: only skills THIS JD explicitly mentions that the candidate lacks
4. candidate_differentiators: candidate strengths that THIS JD would value
5. quick_wins: specific skills from THIS JD the candidate could add quickly
6. role_fit_score: how well this candidate fits THIS specific JD (0-100)
7. recruiter_verdict: one honest sentence about fit for THIS role specifically

Return ONLY valid JSON:
{{
  "role_fit_score": 0-100,
  "this_jd_requires": ["explicit requirements from this JD"],
  "commonly_required_missing": ["from THIS JD only — skills candidate lacks"],
  "candidate_differentiators": ["candidate strengths THIS JD explicitly values"],
  "quick_wins": ["specific skills from THIS JD the candidate could learn in 1-2 weeks"],
  "recruiter_verdict": "one specific honest sentence about fit for this exact role"
}}
"""
    try:
        result = groq_json(
            system=(
                "You are a strict technical recruiter. "
                "Base ALL analysis on the provided JD only. "
                "Treat PySpark and Apache Spark as identical. "
                "Return ONLY valid JSON."
            ),
            user=prompt,
            max_tokens=500,
        )
    except Exception as e:
        print(f"    ⚠ Recruiter failed: {e}")
        result = {
            "role_fit_score": 0, "this_jd_requires": [],
            "commonly_required_missing": [], "candidate_differentiators": [],
            "quick_wins": [], "recruiter_verdict": "Analysis unavailable",
        }

    time.sleep(1)
    return result

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 3 — REWRITER
# Rewrites resume bullet points using the Google XYZ formula:
# "Accomplished [X] as measured by [Y] by doing [Z]"
# Returns the rewritten content as a string — rendered inline in the email.
# (Saving to disk is not used: GitHub Actions runner is ephemeral and files
# are lost after the workflow ends unless committed back to the repo.)
# ──────────────────────────────────────────────────────────────────────────────

def run_rewriter(
    job: dict,
    candidate_context: str,
    diagnoser_output: dict,
    recruiter_output: dict,
) -> dict:
    """
    Rewrites resume bullets specifically for THIS JD.
    Returns a dict with:
      - rewritten_bullets: the tailored experience section
      - ats_score_before: current resume ATS score (from diagnoser)
      - ats_score_after:  estimated ATS score after rewrite
    Human-sounding, not AI-sounding. XYZ formula applied naturally.
    """
    title            = job.get("title", "")
    company          = job.get("companyName", "Unknown")
    description      = (job.get("descriptionText") or "")[:1200]
    missing_keywords = diagnoser_output.get("missing_keywords", [])
    present_keywords = diagnoser_output.get("present_keywords", [])
    jd_required      = diagnoser_output.get("jd_required_skills", [])
    ats_before       = diagnoser_output.get("ats_score", 0)

    prompt = f"""
You are a professional resume writer helping a candidate tailor their resume
for a specific job. Your rewrites sound like a real person wrote them —
confident, direct, human. Not AI-generated filler.

CANDIDATE PROFILE:
{candidate_context}

TARGET JOB: {title} at {company}
FULL JOB DESCRIPTION:
{description}

JD REQUIRED SKILLS (use these exact terms where truthful):
{", ".join(jd_required)}

CANDIDATE ALREADY HAS THESE JD SKILLS (highlight prominently):
{", ".join(present_keywords)}

THESE ARE MISSING FROM CANDIDATE (only incorporate if genuinely applicable):
{", ".join(missing_keywords)}

REWRITING RULES:
1. Write in first person implied (no "I" — just the action): "Built...", "Designed...", "Led..."
2. Use the XYZ formula naturally: "Built [X] that achieved [Y] by doing [Z]"
   Bad:  "Accomplished ETL pipeline development as measured by data processing efficiency"
   Good: "Built a metadata-driven ETL pipeline on Databricks that cut ingestion time by 40%"
3. Use JD's exact terminology where the candidate has that skill
   (e.g. if JD says "data pipeline orchestration" and candidate uses ADF, say "orchestrated pipelines using Azure Data Factory")
4. Quantify with realistic estimates — don't invent, but don't be vague either
5. Max 4 bullets per role, each 1-2 lines
6. End with "Key Skills" listing only skills from BOTH the candidate AND the JD
7. Do NOT mention skills the candidate does not have
8. Sound like a senior engineer wrote this, not a career coach

OUTPUT FORMAT (plain text, no markdown):
Experience
[Company Name] — [Role Title]
- [bullet 1]
- [bullet 2]
- [bullet 3]
- [bullet 4]

Key Skills for {title}:
[comma-separated list]
"""
    try:
        rewritten = groq_text(
            system=(
                "You are a professional resume writer. "
                "Write like a human, not an AI. "
                "Be specific to the JD. "
                "Output plain text only, no markdown."
            ),
            user=prompt,
            max_tokens=900,
        )
    except Exception as e:
        print(f"    ⚠ Rewriter failed: {e}")
        rewritten = "Resume rewrite unavailable for this job."

    # Estimate post-rewrite ATS score: before + credit for each missing keyword
    # now naturally incorporated. Cap at 95 — never claim 100.
    incorporated = len([k for k in missing_keywords if k.lower() in rewritten.lower()])
    ats_after = min(95, ats_before + (incorporated * 5))

    print(f"    ✅ Rewriter complete — ATS {ats_before} → {ats_after} ({len(rewritten)} chars)")
    time.sleep(1)

    return {
        "rewritten_bullets": rewritten,
        "ats_score_before":  ats_before,
        "ats_score_after":   ats_after,
    }

# ──────────────────────────────────────────────────────────────────────────────
# INTELLIGENCE LAYER — orchestrates all three actors
# ──────────────────────────────────────────────────────────────────────────────

def run_intelligence_layer(
    job: dict,
    candidate_context: str,
    date_str: str,
) -> dict:
    """
    Runs Diagnoser → Recruiter → Rewriter for a single qualifying job.
    Returns a dict with all intelligence outputs attached.
    tailored_resume_content is a plain-text string rendered inline in the email.
    """
    title   = job.get("title", "?")
    company = job.get("companyName", "?")

    print(f"\n  🧠 Intelligence layer: {title} @ {company}")

    print(f"    🔬 Diagnoser running...")
    diagnoser = run_diagnoser(job, candidate_context)

    print(f"    👔 Recruiter running...")
    recruiter = run_recruiter(job, candidate_context)

    print(f"    ✍️  Rewriter running...")
    rewriter_output = run_rewriter(job, candidate_context, diagnoser, recruiter)

    return {
        **job,
        "diagnoser":               diagnoser,
        "recruiter":               recruiter,
        "tailored_resume_content": rewriter_output.get("rewritten_bullets", ""),
        "ats_score_before":        rewriter_output.get("ats_score_before", 0),
        "ats_score_after":         rewriter_output.get("ats_score_after", 0),
    }

# ──────────────────────────────────────────────────────────────────────────────
# FILTER + RANK
# ──────────────────────────────────────────────────────────────────────────────

def filter_and_rank(scored_jobs: list[dict]) -> list[dict]:
    # Print a final summary table so the Actions log clearly shows
    # every job's score and why it was accepted or rejected
    print(f"\n{'─'*60}")
    print(f"  SCORING SUMMARY (threshold: {MIN_SCORE})")
    print(f"{'─'*60}")
    for job in sorted(scored_jobs, key=lambda x: x.get("score", 0), reverse=True):
        s       = job.get("score", 0)
        title   = job.get("title", "?")[:40]
        company = job.get("companyName", "?")[:25]
        verdict = job.get("verdict", "?")
        status  = "✅" if s >= MIN_SCORE else "❌"
        print(f"  {status} {s:>3}/100  {title} @ {company}  ({verdict})")
    print(f"{'─'*60}\n")

    filtered = [j for j in scored_jobs if j.get("score", 0) >= MIN_SCORE]
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = filtered[:TOP_N]
    print(f"✅ {len(top)} jobs qualify (score ≥{MIN_SCORE}), {len(scored_jobs) - len(top)} rejected")
    return top

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    print(f"\n{'='*60}")
    print(f"  Job Newsletter Agent — Phase 2.1 — {today}")
    print(f"  Experience: {CANDIDATE_EXPERIENCE} | Seniority: {CANDIDATE_SENIORITY}")
    print(f"{'='*60}\n")

    # ── Load profile ──────────────────────────────────────────
    profile          = load_profile()
    candidate_ctx    = build_candidate_context(profile)

    # ── Step 1: Scrape ────────────────────────────────────────
    raw_jobs = scrape_linkedin_jobs()

    # ── Step 2: Dedup ─────────────────────────────────────────
    unique_jobs = deduplicate(raw_jobs)

    # ── Step 3: Prefilter ─────────────────────────────────────
    filtered_jobs = prefilter_jobs(unique_jobs)
    if not filtered_jobs:
        print("📭 No jobs passed prefilter today.")
        return

    # ── Step 4: Resume embedding (local) ─────────────────────
    resume_text      = build_resume_embedding_text()
    resume_embedding = build_resume_embedding(resume_text)

    # ── Step 5: Semantic similarity ranking ───────────────────
    top_similar_jobs = rank_jobs_by_similarity(
        resume_embedding, filtered_jobs, top_n=EMBEDDING_TOP_N
    )

    # ── Step 6: Groq scoring ──────────────────────────────────
    scored_jobs = score_all_jobs(top_similar_jobs, candidate_ctx)

    # ── Step 7: Filter by score ───────────────────────────────
    top_jobs = filter_and_rank(scored_jobs)

    # Rejected jobs = scored but below threshold — passed to newsletter
    # as a separate feedback section so you can see why they were skipped.
    rejected_jobs = [
        j for j in scored_jobs
        if j.get("score", 0) < MIN_SCORE
    ]
    rejected_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)

    if not top_jobs:
        print("📭 No jobs met the score threshold today.")
        # Still send email if there are rejected jobs worth reviewing
        if not rejected_jobs:
            return

    # ── Step 8: Intelligence layer (Diagnoser+Recruiter+Rewriter)
    # Runs only on qualifying jobs to minimise Groq usage.
    if top_jobs:
        print(f"\n🧠 Running intelligence layer on {len(top_jobs)} qualifying jobs...")
        enriched_jobs = []
        for job in top_jobs:
            enriched = run_intelligence_layer(job, candidate_ctx, today)
            enriched_jobs.append(enriched)
    else:
        enriched_jobs = []

    # ── Step 9: Send newsletter ───────────────────────────────
    send_newsletter(
        jobs=enriched_jobs,
        rejected_jobs=rejected_jobs,
        recipient=RECIPIENT_EMAIL,
        sender=SENDER_EMAIL,
        api_key=EMAIL_API_KEY,
        provider=EMAIL_PROVIDER,
        date_str=today,
        min_score=MIN_SCORE,
    )

    print(f"\n🎉 Newsletter sent → {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    main()
