# personal-email-agent

A Gmail classification, organization, and reply-drafting agent. Polls your inbox every 10 minutes, uses a local LLM to classify each email into one of five categories, applies Gmail labels, drafts replies for emails you flag, and sends an hourly desktop notification summarizing anything that needs attention.

## What it does

- Fetches unread inbox messages via the Gmail API
- Classifies each one using a local LLM (LM Studio, OpenAI-compatible)
- Applies a Gmail label to categorized emails
- Records every classification in PostgreSQL (avoids reprocessing)
- Drafts replies for emails you label `REPLY-REQUIRED` and saves them to Gmail Drafts
- Sends a `notify-send` desktop digest once per hour for urgent items

## Categories

| Label | What it catches | Urgency |
|---|---|---|
| `Advertising` | Marketing, promotions, vendor newsletters, loyalty programs | Non-urgent |
| `Bills-Finance` | Statements, bills, investment notices | Urgent if action/due date mentioned |
| `Friends-Family` | Personal email from individual humans you know | Not urgent |
| `Ideas-Tech` | Informational AI, programming, data science, coffee, fountain pens | Not urgent |
| `News` | News digests, editorial newsletters (Axios, Substack, etc.) | Non-urgent |

Emails that don't clearly fit any category are left **unchanged and unread**.

The hourly digest surfaces two things: urgent `Bills-Finance` and any `Friends-Family` email from the past hour.

## Draft replies

Label any unread email `REPLY-REQUIRED` in Gmail. Within 10 minutes the agent will:

1. Fetch the full email body
2. Ask the LLM to draft a reply that recaps the request and proposes a response with a timeline
3. For complex requests, draft two labeled options (`--- Option A ---` / `--- Option B ---`) so you can delete whichever you don't want before sending
4. Save the draft to Gmail Drafts, signed off as "Scott"
5. Swap the label to `REPLY-DRAFTED` (email stays unread)

The draft tone matches the incoming email — formal replies to formal email, casual to casual.

## Requirements

- Python 3.11+
- Poetry
- PostgreSQL (remote or local)
- LM Studio running an OpenAI-compatible model
- A Google Cloud project with the Gmail API enabled and OAuth credentials
- `notify-send` / `libnotify-bin` for desktop notifications

## Setup

### 1. Configure Poetry to use an in-project virtualenv

```bash
poetry config virtualenvs.in-project true
```

This places the virtualenv at `.venv/` inside the project directory. The cron wrapper scripts rely on this path — run this once before `poetry install`.

### 2. Install dependencies

```bash
poetry install
```

The virtualenv is created at `.venv/`. Verify with:

```bash
.venv/bin/python -c "import yaml; print('OK')"
```

### 3. Configure secrets

```bash
cp .envrc.example .envrc
```

Edit `.envrc` and fill in your values:

```bash
export LM_STUDIO_API_KEY=<your-lm-studio-api-key>
export POSTGRES_PASSWORD=<your-db-password>
```

Then allow direnv (or source the file manually for the current shell):

```bash
direnv allow
# or: source .envrc
```

### 4. Edit config.yaml

```yaml
lm_studio:
  base_url: "http://<lm-studio-host>:1234/v1"
  model: "openai/gpt-oss-20b"   # any loaded model

drafter:
  model: "openai/gpt-oss-20b"   # can override to a larger model for drafting
  temperature: 0.4
  max_tokens: 800

gmail:
  token_path: "~/.config/email-agent/token.json"
  credentials_path: "~/.config/email-agent/credentials.json"

database:
  host: "<postgres-host>"
  port: 5432
  user: "<db-user>"
  dbname: "email-agent"
```

### 5. Gmail OAuth

1. In [Google Cloud Console](https://console.cloud.google.com/), enable the **Gmail API** for your project.
2. Create an **OAuth 2.0 Client ID** (Desktop app type) and download `credentials.json`.
3. Place it at the path set in `config.yaml` (`credentials_path`).
4. Run the one-time auth flow:

```bash
poetry run python bin/auth_gmail.py
```

A browser window opens for the OAuth consent. The token is saved to `token_path` and auto-refreshes on subsequent runs.

### 6. Create the database table

The table is created automatically on first run, but you can trigger it explicitly:

```bash
poetry run python bin/classify_emails.py
```

## Running manually

```bash
# Classify unread inbox messages now
poetry run python bin/classify_emails.py

# Draft replies to REPLY-REQUIRED emails now
poetry run python bin/draft_replies.py

# Send the attention digest now
DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
  poetry run python bin/hourly_digest.py
```

## Cron setup

Cron runs with a minimal `PATH` and no shell hooks, so `.envrc` secrets are not available by default. The wrapper scripts in `bin/cron_*.sh` source `.envrc` and invoke `.venv/bin/python` directly, bypassing any dependency on `poetry` being on the cron `PATH`.

Add all three jobs via `crontab -e`:

```
# Classify every 10 minutes
*/10 * * * * /home/scott/Working/personal-email-agent/bin/cron_classify.sh >> /var/log/email-agent.log 2>&1

# Draft replies to REPLY-REQUIRED emails every 10 minutes
*/10 * * * * /home/scott/Working/personal-email-agent/bin/cron_draft.sh >> /var/log/email-agent-draft.log 2>&1

# Hourly attention digest
0 * * * * /home/scott/Working/personal-email-agent/bin/cron_digest.sh >> /var/log/email-agent-digest.log 2>&1
```

Test a wrapper script manually before adding to cron:

```bash
bash /home/scott/Working/personal-email-agent/bin/cron_classify.sh
```

## Project layout

```
personal-email-agent/
├── bin/
│   ├── auth_gmail.py         # One-time OAuth flow
│   ├── classify_emails.py    # Classifier (every 10 min)
│   ├── draft_replies.py      # Reply drafter (every 10 min)
│   ├── hourly_digest.py      # Attention digest (every hour)
│   ├── setup_labels.py       # Pre-create Gmail labels (optional)
│   ├── cron_classify.sh      # Cron wrapper for classifier
│   ├── cron_draft.sh         # Cron wrapper for reply drafter
│   └── cron_digest.sh        # Cron wrapper for digest
├── email_agent/
│   ├── classifier.py         # LLM classification via LM Studio
│   ├── drafter.py            # LLM reply drafting via LM Studio
│   ├── db.py                 # PostgreSQL read/write
│   ├── gmail_client.py       # Gmail API wrapper
│   ├── models.py             # Pydantic schemas
│   └── notifier.py           # notify-send digest builder
├── .venv/                    # In-project virtualenv (not committed)
├── test/
├── config.yaml
├── .envrc                    # Secrets (not committed)
├── .envrc.example
└── pyproject.toml
```

## Choosing a model

The classifier works best with a compact, instruction-following model. Non-thinking models are strongly preferred — thinking models (Qwen3, DeepSeek-R1, etc.) burn hundreds of reasoning tokens on a task that needs fewer than 100, causing context exhaustion on some emails.

A 7–20B general-purpose instruct model is the sweet spot for both classification and reply drafting. You can configure a separate (larger) model for drafting in the `drafter` section of `config.yaml` if the default produces weak drafts.

## Logs

All scripts write to stdout/stderr using Python's `logging` module (format: `YYYY-MM-DD HH:MM:SS LEVEL name — message`). The cron entries redirect that output to files in `/var/log/`.

### Create log files

The files must exist and be writable by your user before cron runs:

```bash
sudo touch /var/log/email-agent.log /var/log/email-agent-draft.log /var/log/email-agent-digest.log
sudo chown $USER:$USER /var/log/email-agent.log /var/log/email-agent-draft.log /var/log/email-agent-digest.log
```

### View logs

```bash
tail -f /var/log/email-agent.log          # classifier (every 10 min)
tail -f /var/log/email-agent-draft.log    # reply drafter (every 10 min)
tail -f /var/log/email-agent-digest.log   # digest (every hour)
```

### Log rotation (optional)

Create `/etc/logrotate.d/email-agent` to keep logs from growing unbounded:

```
/var/log/email-agent.log /var/log/email-agent-draft.log /var/log/email-agent-digest.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

This keeps 4 weeks of compressed history and silently skips missing files.
