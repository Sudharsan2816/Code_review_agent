from app.models.review import Verdict
from app.services.github_service import PRDiff
from app.services.review_grounding import ground_review_data
from app.services.review_service import _build_prompt


def _readme_diff() -> PRDiff:
    patch = """@@ -1,2 +1,3 @@
 # Example
+![Python](https://img.shields.io/badge/python-3.12-blue)
-Old setup text
+New setup text
"""
    return PRDiff(
        repo="owner/repo",
        pr_number=1,
        pr_title="Update documentation",
        pr_url="https://github.com/owner/repo/pull/1",
        author="owner",
        base_branch="main",
        head_branch="docs",
        files_changed=[
            {
                "filename": "README.md",
                "status": "modified",
                "additions": 2,
                "deletions": 1,
                "changes": 3,
                "patch": patch,
            }
        ],
        diff_text=f"--- a/README.md\n+++ b/README.md\n{patch}",
    )


def _base_payload() -> dict:
    return {
        "bugs": [],
        "security": [],
        "performance": [],
        "code_quality": [],
        "suggested_fixes": [],
        "scores": {"quality": 6, "security": 5, "performance": 7},
        "final_verdict": "REQUEST_CHANGES",
        "summary": "Model-generated summary must not control the final result.",
    }


def _python_diff() -> PRDiff:
    patch = """@@ -1,2 +1,3 @@
 def authenticate(token):
+    return decode(token, options={})
"""
    return PRDiff(
        repo="owner/repo",
        pr_number=2,
        pr_title="Update authentication",
        pr_url="https://github.com/owner/repo/pull/2",
        author="owner",
        base_branch="main",
        head_branch="auth",
        files_changed=[
            {
                "filename": "app/auth.py",
                "status": "modified",
                "additions": 1,
                "deletions": 0,
                "changes": 1,
                "patch": patch,
            }
        ],
        diff_text=f"--- a/app/auth.py\n+++ b/app/auth.py\n{patch}",
    )


def test_grounding_drops_findings_for_files_outside_the_pr_diff():
    payload = _base_payload()
    payload["security"] = [
        {
            "file": "app/api/routes/login.py",
            "line": 10,
            "evidence": "options={}",
            "description": "JWT expiry is not validated",
            "severity": "critical",
        }
    ]

    grounded = ground_review_data(payload, _readme_diff())

    assert grounded.security == []
    assert grounded.dropped_items == 1
    assert grounded.final_verdict == Verdict.APPROVE
    assert grounded.scores.security >= 8


def test_low_severity_documentation_finding_is_grounded_but_does_not_block():
    payload = _base_payload()
    payload["code_quality"] = [
        {
            "file": "README.md",
            "line": None,
            "evidence": "![Python](https://img.shields.io/badge/python-3.12-blue)",
            "description": "The badge should state the supported Python range.",
            "severity": "low",
        }
    ]

    grounded = ground_review_data(payload, _readme_diff())

    assert len(grounded.code_quality) == 1
    assert grounded.code_quality[0].file == "README.md"
    assert grounded.code_quality[0].line == 2
    assert grounded.final_verdict == Verdict.COMMENT
    assert "none are severe enough to block" in grounded.summary


def test_high_severity_finding_requires_changes_only_when_evidence_matches():
    payload = _base_payload()
    payload["security"] = [
        {
            "file": "app/auth.py",
            "line": 999,
            "evidence": "return decode(token, options={})",
            "description": "Token expiry validation is disabled.",
            "severity": "high",
        }
    ]

    grounded = ground_review_data(payload, _python_diff())

    assert len(grounded.security) == 1
    assert grounded.security[0].line == 2
    assert grounded.final_verdict == Verdict.REQUEST_CHANGES


def test_readme_cannot_be_used_as_evidence_for_application_code_claims():
    payload = _base_payload()
    payload["security"] = [
        {
            "file": "README.md",
            "line": 999,
            "evidence": "New setup text",
            "description": "The login endpoint accepts expired JWT tokens.",
            "severity": "critical",
        }
    ]
    payload["suggested_fixes"] = [
        {
            "file": "README.md",
            "issue": "JWT expiry validation",
            "original": "New setup text",
            "improved": "Change the application token decoder.",
            "explanation": "Prevents unauthorized application access.",
        }
    ]

    grounded = ground_review_data(payload, _readme_diff())

    assert grounded.security == []
    assert grounded.suggested_fixes == []
    assert grounded.dropped_items == 2
    assert grounded.final_verdict == Verdict.APPROVE


def test_suggested_fix_must_quote_an_exact_changed_line():
    payload = _base_payload()
    payload["suggested_fixes"] = [
        {
            "file": "README.md",
            "issue": "Clarify setup",
            "original": "New setup text",
            "improved": "New setup text with prerequisites",
            "explanation": "Makes the instructions actionable.",
        },
        {
            "file": "README.md",
            "issue": "Fabricated setup",
            "original": "This line is not in the diff",
            "improved": "Replacement",
            "explanation": "Unsupported suggestion.",
        },
    ]

    grounded = ground_review_data(payload, _readme_diff())

    assert len(grounded.suggested_fixes) == 1
    assert grounded.suggested_fixes[0].original == "New setup text"
    assert grounded.dropped_items == 1


def test_prompt_requires_exact_changed_line_evidence():
    prompt = _build_prompt(_readme_diff())

    assert "Allowed changed files" in prompt
    assert "exact changed line into the evidence field" in prompt
    assert "merely mentioned by documentation" in prompt
    assert "application risk is not evidence" in prompt
