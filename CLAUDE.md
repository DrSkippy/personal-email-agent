# CLAUDE.md

## Project Overview

**personal-email-agent** is a Gmail classification and organization agent. It polls the inbox every 10 minutes, uses a local LLM (LM Studio) to classify emails into one of four categories, applies Gmail labels, and sends an hourly `notify-send` desktop digest of items requiring attention.

## Project Layout

```
personal-email-agent/
├── bin/
│   ├── classify_emails.py    # 10-min cron: fetch → classify → label
│   ├── hourly_digest.py      # Hourly cron: notify-send attention summary
│   └── setup_labels.py       # One-time: create Gmail labels
├── email_agent/
│   ├── __init__.py
│   ├── gmail_client.py       # Gmail API wrapper (fetch, label, mark importance)
│   ├── classifier.py         # PydanticAI classification against LM Studio
│   ├── db.py                 # PostgreSQL storage (processed emails, history)
│   └── notifier.py           # notify-send digest builder
├── test/
├── config.yaml               # Model name, label names, LM Studio URL, prompts
├── .envrc                    # Secrets: Gmail OAuth path, DB credentials
├── .envrc.example
├── pyproject.toml
├── poetry.lock
├── Dockerfile
├── docker-compose.yml
└── CLAUDE.md
```

## Email Categories

| Label | Description | Urgency | Action |
|---|---|---|---|
| `Advertising` | Vendor subscriptions, marketing | Non-urgent | Leave unread |
| `Bills-Finance` | Credit card/bank statements, investments, bills | Urgent if action needed | Include in digest |
| `Friends-Family` | Personal emails from known contacts | Not urgent | Leave unread, include in digest |
| `Ideas-Tech` | AI, programming, data science, ML, coffee, fountain pens — informational only | Not urgent | Leave unread |
| `News` | News digests, newsletters, current events from news outlets and journalists (e.g. Axios, Substack) | Non-urgent | Leave unread |

Emails that do not clearly match any category are left **unchanged and unread**.

## Gmail Labels Applied

- `Advertising`
- `Bills-Finance`
- `Friends-Family`
- `Ideas-Tech`
- `News`

Gmail importance is set to `important` for `Bills-Finance` emails requiring immediate attention.

## Running the Agent

**One-time setup** (create Gmail labels):
```bash
poetry run python bin/setup_labels.py
```

**Manual classification run:**
```bash
poetry run python bin/classify_emails.py
```

**Manual digest:**
```bash
poetry run python bin/hourly_digest.py
```

**Cron configuration** (add via `crontab -e`):
```
*/10 * * * * /home/scott/Working/personal-email-agent/bin/cron_classify.sh >> /var/log/email-agent.log 2>&1
0 * * * *    /home/scott/Working/personal-email-agent/bin/cron_digest.sh >> /var/log/email-agent-digest.log 2>&1
```

The wrapper scripts source `.envrc` for secrets and add `~/.local/bin` to PATH for poetry. `DISPLAY` and `DBUS_SESSION_BUS_ADDRESS` are set inside `cron_digest.sh`.

## Configuration

### config.yaml
```yaml
lm_studio:
  base_url: "http://192.168.1.90:1234/v1"
  model: "your-model-name-here"   # Set to the loaded LM Studio model
  temperature: 0.1                 # Low temp for consistent classification

gmail:
  token_path: "~/.config/email-agent/token.json"
  credentials_path: "~/.config/email-agent/credentials.json"
  max_results: 50                  # Emails to fetch per run

labels:
  advertising: "email-agent/Advertising"
  bills_finance: "email-agent/Bills-Finance"
  friends_family: "email-agent/Friends-Family"
  ideas_tech: "email-agent/Ideas-Tech"

digest:
  lookback_hours: 1
  notify_timeout_ms: 10000
```

### .envrc
```bash
export PGHOST=192.168.1.91
export PGPORT=5434
export PGUSER=<db_user>
export PGPASSWORD=<db_password>
export PGDATABASE=email_agent
```

## Database

- **Host:** `192.168.1.91:5434`
- **Database:** `email-agent`
- **Driver:** `psycopg2`

### Table: `processed_emails`

| Column | Type | Notes |
|---|---|---|
| `message_id` | VARCHAR(255) PRIMARY KEY | Gmail message ID |
| `classified_at` | TIMESTAMPTZ | When classification ran |
| `category` | VARCHAR(50) | One of the 4 categories, or NULL |
| `urgent` | BOOLEAN | Whether marked important |
| `subject` | TEXT | Email subject |
| `sender` | TEXT | From address |
| `snippet` | TEXT | Gmail snippet used for classification |
| `llm_reason` | TEXT | LLM's classification rationale |

## LLM Integration

- **Server:** LM Studio at `http://192.168.1.90:1234/v1` (OpenAI-compatible API)
- **Framework:** PydanticAI with OpenAI-compatible provider
- **Model:** Configured in `config.yaml` — choose the smallest model that reliably produces structured JSON output
- Classification input: sender address + subject + Gmail snippet (first ~200 chars of body)
- Classification output: Pydantic model with `category`, `urgent`, `reason` fields
- Low temperature (0.1) for deterministic classification

## Key Classes

| Class | File | Purpose |
|---|---|---|
| `GmailClient` | `email_agent/gmail_client.py` | Fetch unread messages, apply labels, set importance |
| `EmailClassifier` | `email_agent/classifier.py` | PydanticAI agent wrapping LM Studio classification |
| `EmailDatabase` | `email_agent/db.py` | PostgreSQL read/write for processed emails |
| `DigestNotifier` | `email_agent/notifier.py` | Query attention items, build and send notify-send |

## Pydantic Classification Schema

```python
from typing import Literal
from pydantic import BaseModel

class EmailClassification(BaseModel):
    category: Literal["Advertising", "Bills-Finance", "Friends-Family", "Ideas-Tech"] | None
    urgent: bool
    reason: str  # LLM rationale (stored for debugging)
```

`category=None` means the email did not clearly match any category — leave it untouched.

## Dependencies

```toml
python = ">=3.11"
pydantic-ai
openai            # Used by PydanticAI for OpenAI-compatible endpoints
google-api-python-client
google-auth-oauthlib
psycopg2-binary
pyyaml
```

All managed via Poetry. Run `poetry install` to set up the environment.

## Gmail OAuth Setup

1. In your Google Cloud project, enable the Gmail API.
2. Create an OAuth 2.0 Client ID (Desktop app type).
3. Download `credentials.json` → place at path configured in `config.yaml`.
4. Run the auth flow once interactively — token saved to `token_path`.
5. Token auto-refreshes on subsequent runs.
