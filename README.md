# cost-digest-bot

> A daily Slack bot that pulls your AWS cloud spend, diffs it against last week, and posts a clean human-readable cost summary with anomaly alerts — no cloud console login needed.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Slack](https://img.shields.io/badge/slack-block%20kit-4A154B)
![AWS](https://img.shields.io/badge/aws-cost%20explorer-FF9900)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Why this exists

Cloud costs drift silently. By the time your monthly bill arrives, the damage is done. `cost-digest-bot` posts a daily digest to Slack so your team catches anomalies the same day they happen — not at end of month.

---

## What it posts

```
📊 Daily Cost Digest — Apr 3, 2026

Total spend today:  $1,240   (+8% vs last week)

Top movers:
  🔴 EC2          $640   +$92   (+17%)
  🟡 RDS          $210   +$18   (+9%)
  🟢 S3           $48    -$3    (-6%)
  ⚪ Lambda        $38    +$26  (+218%)

⚠️  Anomaly detected: Lambda spend tripled since yesterday ($12 → $38)
    Possible runaway function — check region: us-east-1

📅 Month-to-date: $18,420  (on track — projected $24,800 vs $25,000 budget)
```

---

## Features

| Feature | Details |
|---|---|
| **Daily digest** | Scheduled post every morning at a time you configure |
| **Week-over-week diff** | Shows spend change vs same day last week per service |
| **Anomaly detection** | Flags any service that spikes beyond a configurable threshold |
| **Month-to-date tracker** | Shows MTD spend and projects end-of-month vs your budget |
| **Top movers** | Ranks services by absolute dollar change, not just percentage |
| **Multi-account support** | Aggregates across AWS accounts via AWS Organizations |
| **SQLite history** | Stores daily snapshots locally for trend comparisons |

---

## Requirements

- Python 3.10+
- AWS account with Cost Explorer enabled (has a small API cost — ~$0.01 per request)
- IAM user or role with `ce:GetCostAndUsage` permission
- Slack app with `chat:write` permission and a bot token

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/NotHarshhaa/cost-digest-bot.git
cd cost-digest-bot
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your credentials
```

`.env` file:

```env
# AWS
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=us-east-1

# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_CHANNEL=#infra-costs

# Budget (optional)
MONTHLY_BUDGET_USD=25000

# Anomaly threshold — alert if a service grows more than this % day-over-day
ANOMALY_THRESHOLD_PCT=100
```

### 3. Run manually

```bash
python bot/digest.py
```

### 4. Schedule it

**GitHub Actions (recommended — free, no server needed):**

```yaml
# .github/workflows/daily-digest.yml
on:
  schedule:
    - cron: '0 8 * * *'   # 8am UTC daily
```

**Or cron on a server:**

```bash
0 8 * * * cd /path/to/cost-digest-bot && python bot/digest.py
```

---

## AWS IAM Policy

Attach this minimal policy to your IAM user or role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. Under **OAuth & Permissions** → add `chat:write` scope
3. Install app to your workspace
4. Copy the **Bot User OAuth Token** (`xoxb-...`) into your `.env` 
5. Invite the bot to your channel: `/invite @cost-digest-bot` 

---

## Repo structure

```
cost-digest-bot/
├── bot/
│   ├── digest.py             # Entry point — orchestrates fetch, diff, post
│   ├── aws_costs.py          # AWS Cost Explorer API client
│   ├── diff.py               # Week-over-week and day-over-day calculations
│   ├── anomaly.py            # Spike detection logic
│   ├── slack_post.py         # Slack Block Kit message builder and poster
│   └── store.py              # SQLite read/write for daily snapshots
├── .github/
│   └── workflows/
│       └── daily-digest.yml  # GitHub Actions cron schedule
├── tests/
│   ├── test_diff.py
│   ├── test_anomaly.py
│   └── fixtures/
│       └── sample_costs.json
├── .env.example
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Configuration reference

All config is via environment variables or `.env`:

| Variable | Default | Description |
|---|---|---|
| `SLACK_CHANNEL` | `#infra-costs` | Channel to post to |
| `MONTHLY_BUDGET_USD` | _(none)_ | Enables MTD budget tracker |
| `ANOMALY_THRESHOLD_PCT` | `100` | Alert if service grows > this % day-over-day |
| `TOP_MOVERS_COUNT` | `5` | Number of services shown in digest |
| `LOOKBACK_DAYS` | `7` | Days to compare against for week-over-week |
| `AWS_DEFAULT_REGION` | `us-east-1` | Region for Cost Explorer API calls |

---

## Docker

```bash
docker build -t cost-digest-bot .
docker run --env-file .env cost-digest-bot
```

---

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Lint
ruff check bot/
```

---

## Roadmap

- [ ] GCP Billing API support
- [ ] Azure Cost Management support
- [ ] Per-team cost breakdown using resource tags
- [ ] Weekly summary report (not just daily)
- [ ] Slack slash command `/cost today` for on-demand query
- [ ] Cost forecast for next 7 days using AWS Cost Forecast API

---

## License

MIT © 2026 NotHarshhaa
