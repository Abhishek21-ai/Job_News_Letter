# resume_profile.py

import json
from pathlib import Path

import fitz
from groq import Groq


# ============================================================
# CONFIG
# ============================================================

RESUME_PATH = Path("resumes/latest_resume.pdf")

MODEL_NAME = "llama-3.1-8b-instant"

client = Groq()


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def extract_resume_text(pdf_path: str) -> str:
    """
    Extracts text from PDF resume using PyMuPDF.
    """

    doc = fitz.open(pdf_path)

    pages = []

    for page in doc:
        pages.append(page.get_text())

    doc.close()

    text = "\n".join(pages)

    # Basic cleanup
    text = " ".join(text.split())

    return text


# ============================================================
# PROMPT
# ============================================================

def build_prompt(resume_text: str) -> str:
    return f"""
You are an expert resume analyzer.

Analyze the following resume and generate a structured JSON profile.

Return ONLY valid JSON.

Rules:
- Do NOT add markdown
- Do NOT add explanation text
- Do NOT wrap in ```json
- Infer experience level from timelines if possible
- Infer engineering domains from projects and technologies
- Infer leadership signals if present

Required JSON schema:

{{
  "primary_roles": [],
  "skills": [],
  "experience_level": "",
  "seniority": "",
  "core_strengths": [],
  "preferred_domains": [],
  "leadership_signals": []
}}

Resume:

{resume_text}
"""


# ============================================================
# LLM PROFILE GENERATION
# ============================================================

def generate_resume_profile(resume_text: str) -> dict:
    prompt = build_prompt(resume_text)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate highly accurate structured "
                    "career profile JSON from resumes."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    content = response.choices[0].message.content

    return json.loads(content)


# ============================================================
# SAVE PROFILE
# ============================================================

def save_profile(profile: dict):
    with open("resume_profile.json", "w") as f:
        json.dump(profile, f, indent=2)


# ============================================================
# MAIN
# ============================================================

def main():
    print("Extracting resume text...")

    resume_text = extract_resume_text(str(RESUME_PATH))

    print("Generating structured profile with Groq...")

    profile = generate_resume_profile(resume_text)

    save_profile(profile)

    print("\nGenerated Resume Profile:\n")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
