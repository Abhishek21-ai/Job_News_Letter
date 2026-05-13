# 🎯 AI Job Newsletter Agent — Phase 2.1

An AI-powered personal career intelligence system that scrapes LinkedIn jobs, semantically ranks them against your resume, scores them with an LLM, and delivers a ranked HTML digest to your inbox — complete with ATS diagnosis, recruiter analysis, and a tailored resume rewrite per job.

Designed for backend, Python, data engineering, and platform engineering roles.

---

## 🚀 Features

- ✅ Scrapes fresh LinkedIn jobs posted in the last **12 hours**
- ✅ Supports multiple locations: Pune · Bangalore · Hyderabad · Remote India
- ✅ **Semantic similarity ranking** using local `all-MiniLM-L6-v2` embeddings (zero API cost)
- ✅ **Resume parsed from PDF** — no hardcoded summaries
- ✅ **AI scoring** using Groq (`llama-3.1-8b-instant`) on top-N semantically ranked jobs only
- ✅ **Three-actor intelligence layer** per qualifying job:
  - 🔬 **Diagnoser** — ATS score, missing keywords, weak/strong areas
  - 👔 **Recruiter** — role fit score, commonly required gaps, quick wins
  - ✍️ **Rewriter** — tailored resume rewrite using Google XYZ formula
- ✅ Smart filtering removes senior roles, wrong tech stacks, irrelevant domains
- ✅ **Resume profile cached** — only regenerates when `REGENERATE_RESUME=true`
- ✅ Experience level and seniority stored in secrets — immune to freelance/consulting inflation
- ✅ Beautiful HTML email newsletter with intelligence sections inline
- ✅ Fully serverless via GitHub Actions · Runs twice daily · ~₹0/month

---

## 🏗️ Architecture

```text
GitHub Actions Scheduler
        │
        ▼
Resume Profile Check
(skip if cached, regenerate if REGENERATE_RESUME=true)
        │
        ▼
LinkedIn Search URLs
        │
        ▼
Apify LinkedIn Scraper
        │
        ▼
Raw Jobs Dataset
        │
        ▼
Deduplication Engine
        │
        ▼
Keyword + Tech Stack Filtering
(title-based seniority check — stricter than description-level)
        │
        ▼
Local Embedding Generation
(all-MiniLM-L6-v2 · query expansion from resume_profile.json)
        │
        ▼
Cosine Similarity Ranking → Top 10 Jobs
        │
        ▼
Groq LLM Scoring (top 10 only)
        │
        ▼
Score Filter (≥ MIN_SCORE)
        │
        ▼
Intelligence Layer (per qualifying job)
  ├── 🔬 Diagnoser (ATS analysis)
  ├── 👔 Recruiter (gap analysis)
  └── ✍️  Rewriter (XYZ resume rewrite)
        │
        ▼
HTML Newsletter Generator
        │
        ▼
Resend / SendGrid Email Delivery
```

---

## 📂 Project Structure

```text
.
├── job_agent.py              # Main pipeline
├── email_sender.py           # HTML newsletter builder + email delivery
├── embedder.py               # Local semantic similarity engine
├── resume_parser.py          # PDF text extraction utility
├── resume_profile.py         # Resume → structured JSON profile (Groq)
├── resume_profile.json       # Cached profile (committed to repo)
├── requirements.txt
├── resumes/
│   └── latest_resume.pdf     # Upload your latest resume here
└── .github/
    └── workflows/
        └── job_newsletter.yml
```

---

## ⚙️ How It Works

1. GitHub Actions triggers the workflow twice daily
2. `resume_profile.py` checks if regeneration is needed — skips if cached
3. Apify scrapes LinkedIn jobs from configured search URLs
4. Jobs are deduplicated and prefiltered locally (title-based seniority check)
5. `embedder.py` generates a query-expanded resume embedding and ranks all filtered jobs by cosine similarity
6. Top 10 semantically similar jobs are sent to Groq for scoring
7. Jobs meeting `MIN_SCORE` go through the three-actor intelligence layer
8. A polished HTML newsletter is built with all intelligence sections inline
9. Resend or SendGrid delivers the email

---

## 🛠️ Setup

### Step 1 — Create GitHub Repository

Create a new **private** GitHub repository and add all project files.

---

### Step 2 — Upload Your Resume

Commit your latest resume PDF to:

```text
resumes/latest_resume.pdf
```

---

### Step 3 — Get API Keys

All services used have generous free tiers.

| Service | Usage | Free Tier |
|---|---|---|
| Apify | LinkedIn scraping | 100 runs/month |
| Groq | LLM scoring + intelligence layer | Free developer tier |
| Resend | Email delivery | 100 emails/day |
| SendGrid | Alternative email provider | 100 emails/day |

- Apify → https://apify.com
- Groq Console → https://console.groq.com
- Resend → https://resend.com
- SendGrid → https://sendgrid.com

---

### Step 4 — Add GitHub Secrets

Go to: `GitHub Repo → Settings → Secrets and variables → Actions → New repository secret`

| Secret | Description | Example |
|---|---|---|
| `APIFY_TOKEN` | Apify API token | `apify_api_...` |
| `GROQ_API_KEY` | Groq API key | `gsk_...` |
| `RECIPIENT_EMAIL` | Your inbox | `you@gmail.com` |
| `SENDER_EMAIL` | Verified sender email | `agent@yourdomain.com` |
| `EMAIL_API_KEY` | Resend or SendGrid key | `re_...` |
| `EMAIL_PROVIDER` | Provider name | `resend` or `sendgrid` |
| `MIN_SCORE` | Minimum score threshold | `75` |
| `TOP_N` | Max jobs in newsletter | `5` |
| `REGENERATE_RESUME` | Controls profile regeneration | `false` |
| `CANDIDATE_EXPERIENCE` | Your actual experience (overrides LLM inference) | `1.5 years` |
| `CANDIDATE_SENIORITY` | Your seniority level (overrides LLM inference) | `junior` |

> **Why `CANDIDATE_EXPERIENCE` and `CANDIDATE_SENIORITY` as secrets?**
> The LLM infers experience from resume timelines — but freelance and consulting work inflates the count. Storing these as secrets gives you direct control and prevents the scorer and intelligence layer from making incorrect assumptions about your level.

---

### Step 5 — Generate Resume Profile (First Time Only)

Set `REGENERATE_RESUME` to `true`, trigger the workflow once manually, then set it back to `false`.

```text
GitHub → Actions → Run Workflow
```

This generates `resume_profile.json` and commits it back to the repo. All future runs skip this step.

**To update after uploading a new resume:**
1. Commit the new PDF to `resumes/latest_resume.pdf`
2. Set `REGENERATE_RESUME` secret to `true`
3. Trigger the workflow once
4. Set `REGENERATE_RESUME` back to `false`

---

### Step 6 — Customize Job Searches

Edit `LINKEDIN_SEARCH_URLS` in `job_agent.py`. Current setup searches:

- Data Engineer
- Backend Engineer (Python / FastAPI)
- Associate Data Engineer
- Remote backend roles

Across: Pune · Bangalore · Hyderabad · Remote India

---

## ⏰ Schedule

Runs automatically at:
- **8:00 AM IST** (2:30 UTC)
- **8:00 PM IST** (14:30 UTC)

```yaml
on:
  schedule:
    - cron: "30 2 * * *"
    - cron: "30 14 * * *"
  workflow_dispatch:
```

Manual trigger available via `GitHub → Actions → Run Workflow`.

---

## 📬 Newsletter Output

Each job card in the email contains:

**Core scoring:**
- Compatibility score + visual score bar
- Match verdict (Strong / Moderate / Weak / Skip)
- Match reasons + skill gap
- Experience requirement
- Remote badge · Employment type · Posted date
- Apply Now + View on LinkedIn buttons

**Intelligence layer** (qualifying jobs only, score ≥ MIN_SCORE):
- 🔬 **ATS Diagnosis** — ATS score, missing JD keywords (pill badges), weak areas, strong areas
- 👔 **Recruiter Analysis** — role fit score, commonly required missing skills, candidate differentiators, quick-win skills
- ✍️ **Tailored Resume** — experience bullets rewritten using Google XYZ formula, ATS keywords naturally incorporated, rendered inline in the email

---

## 🧠 Embedding Pipeline

The semantic layer uses `sentence-transformers/all-MiniLM-L6-v2` — a 22MB model that runs locally in GitHub Actions with zero API cost.

**Query Expansion:** Instead of embedding a flat skill list, the resume is converted into a natural-language paragraph that reads like a job seeker's summary. This puts the resume vector in the same semantic space as job descriptions, so even sparse or vaguely-written JDs match correctly.

**Flow:**
```text
resume_profile.json
        │
        ▼
Natural-language expansion
("Looking for a junior-level position as Backend Engineer...")
        │
        ▼
all-MiniLM-L6-v2 → resume embedding (384-dim)

All filtered jobs → job embeddings (384-dim each)
        │
        ▼
Cosine similarity → top 10 jobs → Groq scoring
```

The model is cached between GitHub Actions runs via `actions/cache` — loads in under 1 second after the first run.

---

## 🔍 Filtering Logic

### Seniority Filter (title-based, strict)

Checks job **title only** — not description — to avoid false positives from JDs that mention "working alongside senior engineers".

Excluded title keywords:
`senior` · `sr.` · `lead` · `principal` · `staff` · `architect` · `manager` · `director` · `head of` · `vp` · `10+ years` · `12+ years` · `8+ years`

### Tech Stack Exclusions (full text)

`java` · `spring` · `springboot` · `.net` · `dotnet` · `php` · `android` · `ios` · `react native` · `golang` · `ruby on rails`

### Relevance Keywords (at least one required)

`python` · `fastapi` · `backend` · `data engineer` · `databricks` · `pyspark` · `kafka` · `postgresql` · `etl` · `azure`

---

## 💰 Estimated Monthly Cost

| Service | Estimated Usage | Cost |
|---|---|---|
| GitHub Actions | ~60 runs/month | Free |
| Apify | ~60 runs/month | Free |
| Groq | ~10 scored + ~15 intelligence calls/run | Free |
| Resend / SendGrid | ~60 emails/month | Free |
| sentence-transformers | Local · no API | Free |
| **Total** | | **~₹0/month** |

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Scraping | Apify · LinkedIn Jobs Scraper |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` · numpy |
| LLM | Groq · `llama-3.1-8b-instant` |
| PDF Parsing | PyMuPDF (`fitz`) |
| Email | Resend / SendGrid |
| Automation | GitHub Actions |
| Language | Python 3.11 |

---

## 🧯 Troubleshooting

### No email received
- Check GitHub Actions run logs
- Verify sender domain is verified in Resend/SendGrid
- Check spam folder

### Groq rate limits (429)
Reduce `EMBEDDING_TOP_N` in the workflow from `10` to `5`:
```yaml
EMBEDDING_TOP_N: "5"
```

### Similarity scores too low / wrong jobs selected
- Set `REGENERATE_RESUME=true` and re-run to rebuild the profile
- Check that `CANDIDATE_EXPERIENCE` and `CANDIDATE_SENIORITY` secrets are set correctly
- Ensure `resumes/latest_resume.pdf` is your most recent resume

### Seniority detected incorrectly in profile
- `CANDIDATE_SENIORITY` secret overrides all LLM inference — set it to `junior`, `entry`, or `mid` as appropriate
- Trigger a profile regeneration after updating the secret

### Too many irrelevant jobs passing the filter
Tighten `RELEVANT_KEYWORDS` or add terms to `NEGATIVE_STACK_KEYWORDS` in `job_agent.py`.

### resume_profile.json not found
Set `REGENERATE_RESUME=true` and run the workflow once manually. The profile will be generated and committed back to the repo automatically.

---

## 🔮 Planned Improvements

- Cover letter generation per job
- Telegram / Slack notification channel
- Seen job ID deduplication across runs (persistent JSON in repo)
- Feedback loop — mark jobs as applied / not relevant
- Multi-location resume variants (backend-focused vs data-focused)
- ATS score trend tracking over time

---

## 📄 License

MIT License

---

Built with ❤️ using local embeddings + Groq LLM + GitHub Actions for smarter, nearly free job hunting.
