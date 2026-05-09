# 🎯 AI Job Newsletter Agent

Automatically scrapes LinkedIn for highly relevant jobs, filters and scores them using Groq LLMs, and sends a ranked HTML newsletter directly to your inbox twice a day.

Designed for backend, Python, data engineering, and platform engineering roles.

---

# 🚀 Features

- ✅ Scrapes fresh LinkedIn jobs posted in the last **12 hours**
- ✅ Supports multiple locations:
  - Pune
  - Bangalore
  - Hyderabad
  - Remote (India)
- ✅ AI-powered scoring using Groq (`llama-3.1-8b-instant`)
- ✅ Smart filtering removes:
  - Senior roles
  - Java/.NET/PHP/mobile roles
  - Irrelevant tech stacks
- ✅ Sends only the **Top N highest-scoring jobs**
- ✅ Beautiful HTML email newsletter
- ✅ Fully serverless using GitHub Actions
- ✅ Runs automatically twice daily
- ✅ Extremely low-cost / free-tier friendly

---

# 🏗️ Architecture

```text
GitHub Actions Scheduler
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
        │
        ▼
Freshness + Seniority Filtering
        │
        ▼
Top Relevant Jobs
        │
        ▼
Groq LLM Scoring
        │
        ▼
Ranked Jobs (Score ≥ MIN_SCORE)
        │
        ▼
HTML Newsletter Generator
        │
        ▼
Resend / SendGrid Email Delivery
```

---

# ⚙️ How It Works

1. GitHub Actions triggers the workflow twice daily
2. Apify scrapes LinkedIn jobs from configured searches
3. Jobs are deduplicated and prefiltered locally
4. Groq LLM scores compatibility against your resume
5. Top-ranked jobs are selected
6. A polished HTML newsletter is generated
7. Resend or SendGrid sends the email

---

# 📂 Project Structure

```text
.
├── job_agent.py
├── email_sender.py
├── requirements.txt
└── .github
    └── workflows
        └── job_newsletter.yml
```

---

# 🛠️ Setup (10 Minutes)

## Step 1 — Create GitHub Repository

Create a new private GitHub repository and add:

```text
job_agent.py
email_sender.py
.github/workflows/job_newsletter.yml
requirements.txt
```

---

# 🔑 Step 2 — Get API Keys

All services used have generous free tiers.

| Service | Usage | Free Tier |
|---|---|---|
| Apify | LinkedIn scraping | 100 runs/month |
| Groq | LLM scoring | Free developer tier |
| Resend | Email delivery | 100 emails/day |
| SendGrid | Alternative email provider | 100 emails/day |

## Official Websites

- Apify → https://apify.com
- Groq Console → https://console.groq.com
- Resend → https://resend.com
- SendGrid → https://sendgrid.com

---

# 🔐 Step 3 — Add GitHub Secrets

Go to:

```text
GitHub Repo
→ Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

Add these secrets:

| Secret Name | Description |
|---|---|
| `APIFY_TOKEN` | Your Apify API token |
| `GROQ_API_KEY` | Your Groq API key |
| `RECIPIENT_EMAIL` | Your inbox email |
| `SENDER_EMAIL` | Verified sender email |
| `EMAIL_API_KEY` | Resend or SendGrid API key |
| `EMAIL_PROVIDER` | `resend` or `sendgrid` |
| `MIN_SCORE` | Recommended: `80` |
| `TOP_N` | Recommended: `5` |

---

# 🔎 Step 4 — Customize Job Searches

Edit `LINKEDIN_SEARCH_URLS` in `job_agent.py`.

Current setup searches:

- Data Engineer
- Backend Engineer (Python/FastAPI)
- Associate Data Engineer
- Remote backend roles

Across:
- Pune
- Bangalore
- Hyderabad
- Remote India

---

# 🧠 Step 5 — Customize Resume Profile

Update `RESUME_SUMMARY` in `job_agent.py`.

This directly impacts:
- AI scoring
- Match quality
- Ranking accuracy

---

# ⏰ Step 6 — GitHub Actions Schedule

Current schedule:
- 8:00 AM IST
- 8:00 PM IST

```yaml
on:
  schedule:
    # 8 AM IST
    - cron: "30 2 * * *"

    # 8 PM IST
    - cron: "30 14 * * *"
```

You can also manually trigger from:

```text
GitHub → Actions → Run Workflow
```

---

# 📬 Newsletter Output

The generated email contains:

- Compatibility score
- Match verdict
- Match reasons
- Missing skill gaps
- Apply links
- LinkedIn links
- Remote badges
- Experience requirements

Only the **top-ranked jobs** are included.

---

# 🧪 Smart Filtering Logic

Before sending jobs to the LLM, the system removes:

## ❌ Excluded Roles

- Manager
- Director
- Lead
- Principal
- Architect

## ❌ Excluded Tech Stacks

- Java
- Spring Boot
- .NET
- PHP
- Android
- iOS
- React Native

## ✅ Preferred Skills

- Python
- FastAPI
- Databricks
- PySpark
- Kafka
- PostgreSQL
- Azure
- ETL
- Backend Engineering
- Data Platform Engineering

---

# 💰 Estimated Monthly Cost

| Service | Estimated Usage | Cost |
|---|---|---|
| GitHub Actions | ~60 runs/month | Free |
| Apify | ~60 runs/month | Free |
| Groq | ~10 scored jobs/run | Free |
| Resend / SendGrid | ~60 emails/month | Free |
| **Total** | | **~$0/month** |

---

# 📈 Performance Strategy

The system intentionally:
- Scrapes many jobs
- Filters aggressively
- Scores only top relevant jobs
- Sends only highest-quality matches

This minimizes:
- API costs
- LLM usage
- Noise
- Irrelevant applications

---

# 🛡️ Rate Limit Protection

Built-in protections include:

- Exponential retry backoff
- Local keyword filtering
- Hard cap before LLM scoring
- Token-reduced prompts
- Deduplication

---

# 🧯 Troubleshooting

## No email received

- Check GitHub Actions logs
- Verify sender email/domain
- Check spam folder

---

## Groq rate limits (429)

Reduce:

```python
filtered_jobs = filtered_jobs[:10]
```

to:

```python
filtered_jobs = filtered_jobs[:5]
```

---

## Too many irrelevant jobs

Adjust:

```python
RELEVANT_KEYWORDS
NEGATIVE_KEYWORDS
EXCLUDED_KEYWORDS
```

---

## Apify scraping too many jobs

Reduce:

```python
"count": 25
```

to:

```python
"count": 12
```

---

# 🎯 Recommended Production Settings

```python
MIN_SCORE = 80
TOP_N = 5
```

And:

```python
"count": 12
```

These give the best balance of:
- freshness
- quality
- low cost
- free-tier sustainability

---

# 🔮 Future Improvements

Potential upgrades:

- Resume-tailored scoring
- Auto-generated cover letters
- ATS keyword optimization
- Telegram/Slack notifications
- Vector search memory
- Multi-LLM ensemble scoring
- Automatic application tracking dashboard

---

# 🧱 Tech Stack

- Python
- GitHub Actions
- Groq LLM API
- Apify
- Resend / SendGrid
- LinkedIn Job Search
- HTML Email Templates

---

# 📄 License

MIT License

---

Built with ❤️ using AI + automation for smarter job hunting.
