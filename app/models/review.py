"""Pydantic models for code review data structures."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class Scores(BaseModel):
    quality: int = Field(..., ge=1, le=10, description="Code quality score 1-10")
    security: int = Field(..., ge=1, le=10, description="Security score 1-10")
    performance: int = Field(..., ge=1, le=10, description="Performance score 1-10")


class FindingItem(BaseModel):
    file: Optional[str] = None
    line: Optional[int] = None
    description: str
    severity: Optional[str] = None  # "low" | "medium" | "high" | "critical"


class SuggestedFix(BaseModel):
    file: Optional[str] = None
    issue: str
    original: Optional[str] = None
    improved: str
    explanation: str


class CodeReview(BaseModel):
    """Full structured code review output."""

    repo: str
    pr_number: int
    pr_title: str
    pr_url: str
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    llm_provider: str

    bugs: list[FindingItem] = Field(default_factory=list)
    security: list[FindingItem] = Field(default_factory=list)
    performance: list[FindingItem] = Field(default_factory=list)
    code_quality: list[FindingItem] = Field(default_factory=list)
    suggested_fixes: list[SuggestedFix] = Field(default_factory=list)

    scores: Scores
    final_verdict: Verdict
    summary: str

    # Populated after human approval flow
    posted_to_github: bool = False
    approved_by: Optional[str] = None


class ReviewRequest(BaseModel):
    """API request body for POST /review."""

    repo_name: str = Field(..., example="owner/repo")
    pr_number: int = Field(..., example=42)
    post_comment: bool = Field(
        default=True, description="Post the review as a GitHub PR comment"
    )


class ApprovalRequest(BaseModel):
    """Approve a pending review before it is posted."""

    review_id: str
    approved_by: str = Field(..., example="alice")
