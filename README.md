# AI Code Review Agent

![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-pipeline-8B5CF6)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude-FF6B35)
![MongoDB](https://img.shields.io/badge/MongoDB-motor-47A248?logo=mongodb&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-yellow)

A production-ready AI-powered code review service that analyses GitHub pull requests and posts structured reviews as PR comments.

## Features

- Fetches PR diffs via PyGithub
- Modular LLM support: **Anthropic Claude** (default) or **OpenAI GPT-4**
- Structured review output: Bugs · Security · Performance · Code Quality · Suggested Fixes
- Scoring system (1–10) for quality, security, and performance
- Optional human approval gate before posting to GitHub
- Review history stored in MongoDB
- FastAPI backend with `/review` and `/webhook/github` endpoints
- LangGraph-compatible pipeline — ready for multi-agent composition
- Prompt caching for Claude (cost reduction)

---

## Architecture

```
GitHub PR
    │
    ▼
FastAPI  (/review  or  /webhook/github)
    │
    ▼
LangGraph StateGraph Pipeline
    │
    ├── fetch_diff        (PyGithub → raw PR diff)
    ├── llm_review        (Claude / GPT-4 structured analysis)
    ├── parse_response    (JSON → Pydantic models)
    ├── build_review      (CodeReview with scores)
    ├── persist_review    (MongoDB via motor)
    └── post_comment      (GitHub PR comment)
```

---

## Project Structure

```
Code_review_agent/
├── app/
│   ├── main.py                  # FastAPI application entry point
│   ├── config.py                # Pydantic settings (env vars)
│   ├── models/
│   │   ├── review.py            # CodeReview, Scores, FindingItem, …
│   │   └── webhook.py           # GitHub webhook payload models
│   ├── services/
│   │   ├── github_service.py    # PyGithub: fetch diff, post comment
│   │   ├── db_service.py        # MongoDB (motor) persistence
│   │   ├── review_service.py    # Orchestration: GitHub → LLM → DB → GitHub
│   │   └── llm/
│   │       ├── base.py          # Abstract LLM interface
│   │       ├── claude_client.py # Anthropic Claude with prompt caching
│   │       └── openai_client.py # OpenAI GPT-4 with JSON mode
│   ├── agents/
│   │   └── review_agent.py      # LangGraph StateGraph pipeline
│   ├── api/
│   │   └── routes/
│   │       ├── review.py        # POST /review, GET /review/{id}
│   │       └── webhook.py       # POST /webhook/github
│   └── utils/
│       └── markdown.py          # CodeReview → GitHub markdown renderer
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/Sudharsan2816/Code_review_agent
cd Code_review_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Required variables:

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub Personal Access Token (repo scope) |
| `ANTHROPIC_API_KEY` | Anthropic API key (if using Claude) |
| `OPENAI_API_KEY` | OpenAI API key (if using GPT-4) |
| `LLM_PROVIDER` | `claude` (default) or `openai` |
| `MONGODB_URI` | MongoDB connection string |

### 3. Start MongoDB

```bash
docker run -d -p 27017:27017 --name mongo mongo:7
```

### 4. Run the server

```bash
mkdir -p logs
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at `http://localhost:8000/docs`

---

## API Reference

### `POST /review`

Trigger a code review for a pull request.

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{
    "repo_name": "owner/repo",
    "pr_number": 42,
    "post_comment": true
  }'
```

**Response:**
```json
{
  "review_id": "664f1a2b3c4d5e6f7a8b9c0d",
  "review": {
    "repo": "owner/repo",
    "pr_number": 42,
    "pr_title": "Add user authentication",
    "final_verdict": "REQUEST_CHANGES",
    "scores": { "quality": 7, "security": 4, "performance": 8 },
    "bugs": [],
    "security": [],
    "performance": [],
    "code_quality": [],
    "suggested_fixes": [],
    "summary": "..."
  }
}
```

### `GET /review/{review_id}`

Retrieve a stored review.

```bash
curl http://localhost:8000/review/664f1a2b3c4d5e6f7a8b9c0d
```

### `GET /review?repo=owner/repo&limit=20&skip=0`

List review history with optional filtering.

```bash
curl "http://localhost:8000/review?repo=owner/repo&limit=10"
```

### `POST /review/approve`

Approve a pending review (when `REQUIRE_HUMAN_APPROVAL=true`).

```bash
curl -X POST http://localhost:8000/review/approve \
  -H "Content-Type: application/json" \
  -d '{"review_id": "664f1a2b3c4d5e6f7a8b9c0d", "approved_by": "alice"}'
```

### `POST /webhook/github`

GitHub webhook endpoint. Configure in your repo:

- **Payload URL:** `https://your-server/webhook/github`
- **Content type:** `application/json`
- **Events:** Pull requests
- **Secret:** value of `GITHUB_WEBHOOK_SECRET`

---

## Human Approval Flow

Set `REQUIRE_HUMAN_APPROVAL=true` in `.env`.

Reviews are analysed and saved to MongoDB but **not** posted to GitHub automatically. Use `POST /review/approve` to post after review.

---

## Switching LLM Providers

```bash
# Use Claude (default)
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...

# Use OpenAI GPT-4
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

---

## LangGraph Agent

The `app/agents/review_agent.py` module exposes a compiled `StateGraph`:

```python
from app.agents.review_agent import review_graph

result = await review_graph.ainvoke({
    "repo": "owner/repo",
    "pr_number": 42,
    "post_comment": True,
    "pr_diff": None,
    "raw_llm_response": "",
    "parsed_data": {},
    "review": None,
    "review_id": "",
    "error": "",
    "logs": [],
})
print(result["review"].final_verdict)
```

The linear pipeline (`fetch_diff → llm_review → parse_response → build_review → persist_review → post_comment`) can be extended with parallel branches (e.g. static analysis, test generation) by adding nodes and edges to the graph.

---

## Review Output Format

The GitHub PR comment follows this structure:

```
## 🤖 AI Code Review — <PR Title>

> Verdict: 🚨 REQUEST_CHANGES

<summary>

### Scores
| Dimension    | Score |
|--------------|-------|
| Code Quality | 7/10  |
| Security     | 4/10  |
| Performance  | 8/10  |

### 🐛 Bugs
### 🔐 Security
### ⚡ Performance
### 🧹 Code Quality
### Suggested Fixes
```
