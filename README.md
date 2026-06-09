# AI Code Review Agent

FastAPI service that reviews GitHub pull requests with an LLM and can post structured review comments back to GitHub.

This project is a backend/AI engineering showcase: it combines GitHub API integration, structured LLM output parsing, MongoDB persistence, optional human approval, and a LangGraph-compatible review pipeline.

## What It Does

- Fetches pull request metadata and unified diffs from GitHub.
- Sends the diff to Claude or OpenAI with a structured review prompt.
- Parses LLM output into typed Pydantic models.
- Scores code quality, security, and performance.
- Stores review history in MongoDB.
- Posts a GitHub PR comment when automatic posting is enabled.
- Supports a human approval gate before publishing review comments.
- Exposes a LangGraph-compatible pipeline for future multi-agent extensions.

## Architecture

```text
GitHub PR webhook / API request
  -> FastAPI route
  -> GitHubService fetches PR diff
  -> ReviewService builds prompt
  -> Claude/OpenAI client generates structured review
  -> Pydantic models validate review
  -> MongoDB stores review history
  -> GitHubService optionally posts markdown comment
```

## Tech Stack

- Python, FastAPI, Pydantic
- PyGithub for GitHub PR and comment operations
- Anthropic Claude and OpenAI provider support
- MongoDB with Motor/PyMongo
- LangGraph-compatible orchestration module
- Loguru structured application logging

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/review` | Run a review for a GitHub PR |
| `GET` | `/review/{review_id}` | Fetch a stored review |
| `GET` | `/review` | List review history |
| `POST` | `/review/approve` | Approve and post a pending review |
| `POST` | `/webhook/github` | Receive GitHub pull request webhooks |
| `GET` | `/health` | Liveness check |

## Run Locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Start MongoDB:

```bash
docker run -d -p 27017:27017 --name code-review-mongo mongo:7
```

Run the API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open API docs at http://localhost:8000/docs.

## Example Request

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{
    "repo_name": "owner/repo",
    "pr_number": 42,
    "post_comment": false
  }'
```

## Recruiter Notes

This repo demonstrates:

- Backend API design around real external systems.
- LLM provider abstraction instead of hardcoding one model.
- Typed structured output validation.
- GitHub webhook and PR-comment workflow knowledge.
- Human-in-the-loop approval design for risky automated actions.
- A path toward multi-agent code review using LangGraph.

## Current Production Gaps

- Add webhook signature verification before trusting GitHub payloads.
- Add rate limiting and API authentication.
- Add more tests around LLM parsing and GitHub comment rendering.
- Add Docker Compose for API plus MongoDB.
- Add CI coverage for unit tests and linting.
- Add deployment docs for Render/Railway/Fly.io.

## Recommended Public Metadata

- Recommended repo name: `ai-code-review-agent`
- Description: `AI-powered GitHub PR review service with FastAPI, GitHub webhooks, Anthropic/OpenAI support, MongoDB review history, and LangGraph orchestration.`
- Topics: `python`, `fastapi`, `github-api`, `llm`, `anthropic`, `openai`, `mongodb`, `langgraph`, `code-review`, `backend`
