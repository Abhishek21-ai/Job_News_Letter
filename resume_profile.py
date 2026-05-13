# resume_profile.py
#
# Generates resume_profile.json from the latest PDF resume.
# Controlled by REGENERATE_RESUME env var — skips generation
# if the profile already exists and the flag is not "true".
#
# Usage:
#   REGENERATE_RESUME=true  → always regenerate (use after uploading new resume)
#   REGENERATE_RESUME=false → skip if resume_profile.json already exists

import json
import os
import sys
from pathlib import Path

import fitz
from groq import Groq

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

RESUME_PATH   = Path("resumes/latest_resume.pdf")
PROFILE_PATH  = Path("resume_profile.json")
MODEL_NAME    = "llama-3.1-8b-instant"

client = Groq()

# ──────────────────────────────────────────────────────────────────────────────
# CACHE CHECK
# ──────────────────────────────────────────────────────────────────────────────

def should_regenerate() -> bool:
    """
    Returns True only when REGENERATE_RESUME=true is explicitly set.
    If profile already exists and flag is false/missing, skip generation.
    """
    flag = os.environ.get("REGENERATE_RESUME", "false").strip().lower()

    if flag == "true":
        print("🔄 REGENERATE_RESUME=true — regenerating profile...")
        return True

    if PROFILE_PATH.exists():
        print(f"✅ resume_profile.json exists and REGENERATE_RESUME={flag} — skipping generation.")
        return False

    # Profile doesn't exist at all — must generate regardless of flag
    print("⚠️  resume_profile.json not found — generating for the first time...")
    return True

# ──────────────────────────────────────────────────────────────────────────────
# PDF EXTRACTION
# ──────────────────────────────────────────────────────────────────────────────

def extract_resume_text(pdf_path: str) -> str:
    doc   = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return " ".join(" ".join(pages).split())

# ──────────────────────────────────────────────────────────────────────────────
# PROMPT
# ──────────────────────────────────────────────────────────────────────────────

def build_prompt(resume_text: str) -> str:
    # CANDIDATE_EXPERIENCE is stored in GitHub Secrets to override
    # any LLM inference — prevents freelance/consulting work from
    # inflating the experience level incorrectly.
    candidate_experience = os.environ.get("CANDIDATE_EXPERIENCE", "").strip()

    experience_instruction = (
        f'IMPORTANT: Set "experience_level" to exactly "{candidate_experience}". '
        f'Do NOT infer this from the resume. Use this value verbatim.'
        if candidate_experience
        else 'Infer experience_level from employment timelines only (exclude freelance/consulting).'
    )

    return f"""
You are an expert resume analyzer for software engineering roles.

Analyze the following resume and generate a structured JSON profile.

Return ONLY valid JSON. No markdown. No explanation. No ```json wrapper.

{experience_instruction}

For "seniority": derive ONLY from industry employment start date,
ignoring freelance, consulting, or contract work. Use one of:
"entry", "junior", "mid", "senior".

For "preferred_domains": list engineering domains the candidate
has direct project experience in (not just mentioned as buzzwords).

Required JSON schema:
{{
  "name": "",
  "primary_roles": [],
  "skills": [],
  "experience_level": "",
  "seniority": "",
  "core_strengths": [],
  "preferred_domains": [],
  "certifications": [],
  "education": "",
  "leadership_signals": [],
  "target_locations": ["Pune", "Bangalore", "Hyderabad", "Remote India"]
}}

Resume:
{resume_text}
"""

# ──────────────────────────────────────────────────────────────────────────────
# PROFILE GENERATION
# ──────────────────────────────────────────────────────────────────────────────

def generate_resume_profile(resume_text: str) -> dict:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate highly accurate structured career profile "
                    "JSON from resumes. You follow all instructions precisely."
                ),
            },
            {
                "role": "user",
                "content": build_prompt(resume_text),
            },
        ],
    )
    return json.loads(response.choices[0].message.content)

# ──────────────────────────────────────────────────────────────────────────────
# SAVE
# ──────────────────────────────────────────────────────────────────────────────

def save_profile(profile: dict):
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"💾 Profile saved to {PROFILE_PATH}")

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    if not should_regenerate():
        # Print existing profile for visibility in Actions log
        with open(PROFILE_PATH) as f:
            print("\nCurrent profile:\n", json.dumps(json.load(f), indent=2))
        sys.exit(0)

    if not RESUME_PATH.exists():
        print(f"❌ Resume not found at {RESUME_PATH}")
        sys.exit(1)

    print("📄 Extracting resume text...")
    resume_text = extract_resume_text(str(RESUME_PATH))

    print("🤖 Generating structured profile with Groq...")
    profile = generate_resume_profile(resume_text)

    save_profile(profile)

    print("\n✅ Generated Resume Profile:\n")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
