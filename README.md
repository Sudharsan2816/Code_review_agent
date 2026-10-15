# AI Code Review Agent

FastAPI service that reviews GitHub pull requests with an LLM and can post structured review comments back to GitHub.

Every review runs as a LangGraph StateGraph: fetch diff, LLM review, parse, ground findings against the diff, persist to MongoDB, then either post the comment or hold it for human approval.

## What It Does

- Fetches pull request metadata and unified diffs from GitHub.
- Sends the diff to Claude or OpenAI with a structured review prompt.
- Parses LLM output into typed Pydantic models.
- Scores code quality, security, and performance.
- Stores review history in MongoDB.
- Posts a GitHub PR comment when automatic posting is enabled.
- Supports a human approval gate before publishing review comments.
- Rejects webhook calls without a valid `X-Hub-Signature-256` HMAC-SHA256 signature.
- Requires an API token on manual review and approval routes.

## Architecture

```text
GitHub PR webhook (HMAC verified) / API request (token)
  -> FastAPI route
  -> ReviewService.run_review executes the LangGraph StateGraph:
       fetch_diff -> llm_review -> parse_response -> build_review -> persist_review
         -> post_comment            (auto-posting allowed)
         -> END, pending approval   (REQUIRE_HUMAN_APPROVAL=true)
  -> POST /review/approve posts a held review after a human approves it
```

## Tech Stack

- Python, FastAPI, Pydantic
- PyGithub for GitHub PR and comment operations
- Anthropic Claude and OpenAI provider support
- MongoDB with Motor/PyMongo
- LangGraph StateGraph orchestration
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

## Engineering Highlights

- Webhook payloads are trusted only after HMAC-SHA256 verification.
- The LLM provider sits behind one interface (Claude, OpenAI, NVIDIA).
- Findings are validated into typed models and grounded against changed lines before saving.
- Posting to GitHub is a conditional branch in the graph, so the approval gate is part of the pipeline itself.

## Known Gaps

- Add rate limiting on the API routes.
- Add Docker Compose for API plus MongoDB.
- Add idempotency for repeated webhook deliveries of the same commit.
- Add linting to CI.

