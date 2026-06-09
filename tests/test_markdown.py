from app.models.review import CodeReview, FindingItem, Scores, Verdict
from app.utils.markdown import review_to_markdown


def test_review_to_markdown_renders_scores_and_findings():
    review = CodeReview(
        repo="owner/repo",
        pr_number=42,
        pr_title="Add payment webhook",
        pr_url="https://github.com/owner/repo/pull/42",
        llm_provider="claude",
        bugs=[
            FindingItem(
                file="app.py",
                line=12,
                description="Missing signature validation",
                severity="high",
            )
        ],
        scores=Scores(quality=7, security=4, performance=8),
        final_verdict=Verdict.REQUEST_CHANGES,
        summary="The change needs a security fix before merge.",
    )

    markdown = review_to_markdown(review)

    assert "AI Code Review - Add payment webhook" in markdown
    assert "**REQUEST_CHANGES**" in markdown
    assert "| Security | 4/10 |" in markdown
    assert "[HIGH] Missing signature validation - `app.py` line 12" in markdown
    assert "ð" not in markdown
