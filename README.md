# AI Code Review Agent

![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-8B5CF6)
![Claude](https://img.shields.io/badge/Anthropic-Claude-FF6B35)
![MongoDB](https://img.shields.io/badge/MongoDB-motor-47A248?logo=mongodb&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-yellow)

> A LangGraph-powered autonomous code review agent that fetches GitHub PR diffs, generates structured AI analysis across five engineering dimensions, and posts formatted reviews as PR comments — with an optional human-in-the-loop approval gate.

---

## The Problem

Code review is a bottleneck at every engineering team:

- PRs wait hours or days for human review
- Junior engineers miss security vulnerabilities and performance issues
- Reviewers burn time on style and formatting instead of logic and architecture
- No consistent review depth across the team

---

## Solution

A production FastAPI service with a LangGraph StateGraph pipeline that automatically reviews any GitHub PR on trigger — via webhook or API call — and posts a structured, scored review directly as a PR comment.

---

## Architecture

```
GitHub PR (opened / updated)
         │
         ▼
POST /webhook/github   OR   POST /review
         │
         ▼
   FastAPI (async)
         │
         ▼
┌────────────────────────────────────────────────┐
│            LangGraph StateGraph                │
│                                                │
│  ┌─────────────┐                               │
│  │ fetch_diff  │  PyGithub → raw PR diff       │
│  └──────┬──────┘  (up to 80K chars)           │
│         │                                      │
│  ┌──────▼──────┐                               │
│  │ llm_review  │  Claude Sonnet (cached prompt)│
│  │             │  or GPT-4o (JSON mode)        │
│  └──────┬──────┘                               │
│         │                                      │
│  ┌──────▼──────┐                               │
│  │    parse    │  JSON → Pydantic models       │
│  └──────┬──────┘                               │
│         │                                      │
│  ┌──────▼──────┐                               │
│  │ build_review│  CodeReview + scores          │
│  └──────┬──────┘                               │
│         │                                      │
│  ┌──────▼──────┐                               │
│  │   persist   │  MongoDB (motor async)        │
│  └──────┬──────┘                               │
│         │                                      │
│    REQUIRE_HUMAN_APPROVAL?                     │
│       /          \                             │
│     yes           no                           │
│      │             │                           │
│  wait for      post_comment                    │
│  /approve      (PyGithub → PR comment)         │
└────────────────────────────────────────────────┘
```

---

## Key Features

| Feature | Detail |
|---------|--------|
| **5-dimension review** | Bugs · Security · Performance · Code Quality · Suggested Fixes |
| **Scoring** | 1–10 scores for quality, security, and performance |
| **Verdict** | `APPROVE` · `REQUEST_CHANGES` · `COMMENT` |
| **Multi-LLM** | Anthropic Claude (default, prompt caching) or OpenAI GPT-4o |
| **Human gate** | Optional approval hold before posting to GitHub |
| **Review history** | Full MongoDB persistence with repo, PR, timestamp, verdict |
| **Webhook** | Drop-in GitHub webhook — fully autonomous after one-time setup |
| **Extensible** | LangGraph nodes make it easy to add static analysis, test generation, etc. |

---

## How It Works

**Step 1 — Trigger**
GitHub fires a webhook to `POST /webhook/github` when a PR is opened or updated. Alternatively, call `POST /review` directly with `repo_name` and `pr_number`.

**Step 2 — Fetch Diff**
`fetch_diff` authenticates with `GITHUB_TOKEN`, retrieves the raw PR diff via PyGithub. Diffs are truncated at 80K characters to prevent token overflow.

**Step 3 — LLM Review**
`llm_review` sends the diff and a structured review prompt to Claude (with ephemeral prompt caching on the system prompt) or GPT-4o in JSON mode. Output is a structured object with findings per category and 1–10 scores.

**Step 4 — Parse and Build**
`parse_response` strips markdown fences and decodes JSON. `build_review` assembles the validated `CodeReview` Pydantic model with per-finding `FindingItem` objects.

**Step 5 — Persist**
`persist_review` stores the full review in MongoDB with motor (async). Enables review history queries and audit trail.

**Step 6 — Gate or Post**
- `REQUIRE_HUMAN_APPROVAL=false` → `post_comment` formats and posts immediately
- `REQUIRE_HUMAN_APPROVAL=true` → review waits; call `POST /review/approve` to release

---

## Sample PR Comment Output

```
## 🤖 AI Code Review — Add JWT authentication

> Verdict: 🚨 REQUEST_CHANGES

Adds JWT auth but token expiry is not validated server-side, and /login has
no rate limiting — creating an exploitable auth bypass and brute-force surface.

### Scores
| Dimension    | Score |
|--------------|-------|
| Code Quality | 7/10  |
| Security     | 4/10  |
| Performance  | 8/10  |

### 🐛 Bugs (2)
- `verify_token()`: expired tokens accepted — add `options={"verify_exp": True}`
- `get_user()`: SQL query uses string concatenation in one edge case — parameterize

### 🔐 Security (1)
- No rate limiting on POST /login → brute-force attack surface

### ⚡ Performance (1)
- N+1 query in user list endpoint — add select_related or batch fetch

### 🧹 Code Quality (2)
- Token TTL hardcoded as magic number — extract to config constant
- `validate_user()` is 120 lines — split into focused functions

### Suggested Fixes
...
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Orchestration | LangGraph StateGraph |
| AI | Claude `claude-sonnet-4-6` (Anthropic) / OpenAI GPT-4o |
| Prompt Optimization | Anthropic ephemeral prompt caching |
| GitHub Integration | PyGithub |
| API | FastAPI (async) |
| Database | MongoDB via motor (async) |
| Validation | Pydantic v2 |
| Runtime | Python 3.11+ |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Sudharsan2816/Code_review_agent
cd Code_review_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Required: GITHUB_TOKEN, ANTHROPIC_API_KEY, MONGODB_URI
```

### 3. Start MongoDB

```bash
docker run -d -p 27017:27017 mongo:7
```

### 4. Run

```bash
mkdir -p logs
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### 5. Add GitHub Webhook

In your target repo → Settings → Webhooks → Add webhook:
- **Payload URL:** `https://your-server/webhook/github`
- **Content type:** `application/json`
- **Events:** Pull requests
- **Secret:** your `GITHUB_WEBHOOK_SECRET`

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/review` | Trigger review by repo + PR number |
| `GET` | `/review/{id}` | Fetch a stored review |
| `GET` | `/review?repo=owner/repo` | List review history |
| `POST` | `/review/approve` | Post a held review to GitHub |
| `POST` | `/webhook/github` | GitHub webhook receiver |

---

## LLM Configuration

```bash
# Claude (default) — prompt caching enabled
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...

# GPT-4o — JSON mode
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

---

## Project Structure

```
Code_review_agent/
├── app/
│   ├── main.py                   # FastAPI entry point
│   ├── config.py                 # Pydantic settings (env vars)
│   ├── agents/
│   │   └── review_agent.py       # LangGraph StateGraph definition
│   ├── api/routes/
│   │   ├── review.py             # POST /review, GET /review, POST /approve
│   │   └── webhook.py            # POST /webhook/github
│   ├── models/
│   │   ├── review.py             # CodeReview, Scores, FindingItem
│   │   └── webhook.py            # GitHub webhook payload models
│   ├── services/
│   │   ├── github_service.py     # PyGithub: fetch diff, post comment
│   │   ├── db_service.py         # MongoDB persistence
│   │   ├── review_service.py     # Orchestration logic
│   │   └── llm/
│   │       ├── base.py           # Abstract LLM interface
│   │       ├── claude_client.py  # Anthropic with prompt caching
│   │       └── openai_client.py  # OpenAI GPT-4o with JSON mode
│   └── utils/
│       └── markdown.py           # CodeReview → GitHub comment formatter
├── requirements.txt
├── .env.example
└── README.md
```
