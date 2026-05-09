# 🎯 Daily Job Newsletter Agent

Automatically scrapes LinkedIn for jobs matching your resume every 24 hours,
scores each one with Claude AI, and sends a ranked HTML digest to your inbox.

---

## How it works

1. **GitHub Actions** triggers the script daily at 8 AM IST (free, no server needed)
2. **Apify** scrapes LinkedIn for jobs posted in the last 48 hours
3. **Claude API** scores each job 0–100 against your resume
4. Jobs scoring ≥ 70 are ranked and formatted into a newsletter
5. **Resend or SendGrid** sends the HTML email to your inbox

---

## Setup (10 minutes)

### Step 1 — Fork/create the repo

Create a new private GitHub repo and add these files:
```
job_agent.py
email_sender.py
.github/workflows/job_newsletter.yml
```

### Step 2 — Get your API keys (all have free tiers)

| Service | Free Tier | Sign Up |
|---------|-----------|---------|
| **Apify** | 100 actor runs/mo | https://apify.com |
| **Anthropic** | Pay-per-use (~$0.01/run) | https://console.anthropic.com |
| **Resend** *(recommended)* | 100 emails/day free | https://resend.com |
| **SendGrid** *(alternative)* | 100 emails/day free | https://sendgrid.com |

For Resend: you need a verified domain or use their sandbox with your own email.
For SendGrid: verify your sender email address in their dashboard.

### Step 3 — Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these secrets:

| Secret name | Value |
|-------------|-------|
| `APIFY_TOKEN` | Your Apify API token |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `RECIPIENT_EMAIL` | abhishek230102@gmail.com |
| `SENDER_EMAIL` | your verified sender email |
| `EMAIL_API_KEY` | Your Resend or SendGrid API key |
| `EMAIL_PROVIDER` | `resend` or `sendgrid` |

### Step 4 — Customize your searches

In `job_agent.py`, edit `LINKEDIN_SEARCH_URLS` to add/change locations or roles.
Edit `RESUME_SUMMARY` if your skills change.

### Step 5 — Test it

Go to **Actions** tab in GitHub → **Daily Job Newsletter** → **Run workflow** (manual trigger).

Check your inbox in ~3–5 minutes.

---

## Customization

| What | Where | How |
|------|-------|-----|
| Score threshold | `MIN_SCORE` env var or workflow YAML | Default: 70 |
| Locations/roles | `LINKEDIN_SEARCH_URLS` in `job_agent.py` | Add/remove LinkedIn search URLs |
| Schedule | `.github/workflows/job_newsletter.yml` | Edit the cron expression |
| Resume skills | `RESUME_SUMMARY` in `job_agent.py` | Paste your updated skills |

### Changing the schedule

The default is 8:00 AM IST daily. To change it, edit the cron line in the workflow:

```yaml
# Examples (all times in UTC):
- cron: "30 2 * * *"    # 8:00 AM IST (default)
- cron: "30 2 * * 1-5"  # Weekdays only
- cron: "30 2 * * 1"    # Mondays only
```

---

## Estimated monthly cost

| Service | Usage | Cost |
|---------|-------|------|
| GitHub Actions | ~30 runs × ~5 min | Free (2000 min/mo included) |
| Apify | ~30 runs × ~50 jobs | Free (100 runs/mo free tier) |
| Anthropic API | ~30 × 50 jobs × ~300 tokens | ~$0.30–0.50/month |
| Resend / SendGrid | 30 emails/month | Free |
| **Total** | | **~$0.50/month** |

---

## Troubleshooting

**No email received?**
- Check GitHub Actions logs for errors
- Verify your sender email is confirmed with Resend/SendGrid
- Check spam folder

**Apify run times out?**
- Reduce `count` in `scrape_linkedin_jobs()` (default: 50)
- Reduce number of search URLs

**Claude API errors?**
- Check your Anthropic account has credits
- The script will skip failed scorings rather than crash

---

Built with: Python · Apify · Claude API · Resend · GitHub Actions
