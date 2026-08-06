"""Deterministic grounding and verdict calibration for LLM review output."""

from dataclasses import dataclass
import re

from loguru import logger

from app.models.review import FindingItem, Scores, SuggestedFix, Verdict
from app.services.github_service import PRDiff


_FINDING_CATEGORIES = ("bugs", "security", "performance", "code_quality")
_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class ChangedLine:
    text: str
    line: int


@dataclass
class GroundedReviewData:
    bugs: list[FindingItem]
    security: list[FindingItem]
    performance: list[FindingItem]
    code_quality: list[FindingItem]
    suggested_fixes: list[SuggestedFix]
    scores: Scores
    final_verdict: Verdict
    summary: str
    dropped_items: int


def _normalise_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def _normalise_evidence(value: str) -> str:
    value = value.strip().strip("`'\"")
    if value.startswith(("+", "-")):
        value = value[1:]
    return " ".join(value.split())


def _changed_lines(diff_text: str) -> dict[str, list[ChangedLine]]:
    """Return only added/deleted lines that were actually included in the prompt."""
    result: dict[str, list[ChangedLine]] = {}
    current_file: str | None = None
    old_line: int | None = None
    new_line: int | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = _normalise_path(raw_line[6:])
            result.setdefault(current_file, [])
            old_line = new_line = None
            continue

        match = _HUNK_HEADER.match(raw_line)
        if match and current_file:
            old_line = int(match.group(1))
            new_line = int(match.group(2))
            continue

        if current_file is None or old_line is None or new_line is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            result[current_file].append(ChangedLine(raw_line[1:], new_line))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            result[current_file].append(ChangedLine(raw_line[1:], old_line))
            old_line += 1
        elif raw_line.startswith(" "):
            old_line += 1
            new_line += 1

    return result


def _match_changed_line(evidence: str, lines: list[ChangedLine]) -> ChangedLine | None:
    needle = _normalise_evidence(evidence)
    if len(needle) < 8:
        return None
    for changed_line in lines:
        candidate = _normalise_evidence(changed_line.text)
        if needle == candidate or needle in candidate:
            return changed_line
    return None


def _ground_findings(
    raw_items: object,
    changed: dict[str, list[ChangedLine]],
) -> tuple[list[FindingItem], int]:
    grounded: list[FindingItem] = []
    dropped = 0
    if not isinstance(raw_items, list):
        return grounded, 1 if raw_items else 0

    for raw in raw_items:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        filename = _normalise_path(str(raw.get("file") or ""))
        evidence = str(raw.get("evidence") or "")
        severity = str(raw.get("severity") or "").lower()
        matched = _match_changed_line(evidence, changed.get(filename, []))
        if not filename or not matched or severity not in _SEVERITY_RANK:
            logger.warning(
                "Dropping ungrounded finding file={} evidence={!r}",
                filename or "<missing>",
                evidence[:120],
            )
            dropped += 1
            continue
        try:
            grounded.append(
                FindingItem(
                    file=filename,
                    line=matched.line,
                    evidence=matched.text.strip(),
                    description=str(raw.get("description") or "").strip(),
                    severity=severity,
                )
            )
        except Exception as exc:
            logger.warning("Dropping malformed grounded finding: {}", exc)
            dropped += 1
    return grounded, dropped


def _ground_fixes(
    raw_items: object,
    changed: dict[str, list[ChangedLine]],
) -> tuple[list[SuggestedFix], int]:
    grounded: list[SuggestedFix] = []
    dropped = 0
    if not isinstance(raw_items, list):
        return grounded, 1 if raw_items else 0

    for raw in raw_items:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        filename = _normalise_path(str(raw.get("file") or ""))
        original = str(raw.get("original") or "")
        matched = next(
            (
                match
                for line in original.splitlines()
                if (match := _match_changed_line(line, changed.get(filename, [])))
            ),
            None,
        )
        if not filename or not matched:
            logger.warning("Dropping ungrounded suggested fix file={}", filename or "<missing>")
            dropped += 1
            continue
        try:
            grounded.append(
                SuggestedFix(
                    file=filename,
                    issue=str(raw.get("issue") or "").strip(),
                    original=matched.text.strip(),
                    improved=str(raw.get("improved") or "").strip(),
                    explanation=str(raw.get("explanation") or "").strip(),
                )
            )
        except Exception as exc:
            logger.warning("Dropping malformed grounded fix: {}", exc)
            dropped += 1
    return grounded, dropped


def _score(raw: object, issues: list[FindingItem]) -> int:
    try:
        value = max(1, min(10, int(raw)))
    except (TypeError, ValueError):
        value = 5
    return value if issues else max(8, value)


def ground_review_data(data: dict, pr_diff: PRDiff) -> GroundedReviewData:
    """Validate LLM findings against the exact changed lines sent to the model."""
    changed = _changed_lines(pr_diff.diff_text)
    grounded_by_category: dict[str, list[FindingItem]] = {}
    dropped = 0

    for category in _FINDING_CATEGORIES:
        items, category_dropped = _ground_findings(data.get(category, []), changed)
        grounded_by_category[category] = items
        dropped += category_dropped

    fixes, fixes_dropped = _ground_fixes(data.get("suggested_fixes", []), changed)
    dropped += fixes_dropped

    findings = [
        item
        for category in _FINDING_CATEGORIES
        for item in grounded_by_category[category]
    ]
    blocking = [
        item for item in findings if _SEVERITY_RANK.get(item.severity or "", 0) >= 3
    ]

    if not findings:
        verdict = Verdict.APPROVE
        summary = "No evidence-grounded issues were found in the changed lines."
    elif blocking:
        verdict = Verdict.REQUEST_CHANGES
        summary = (
            f"Found {len(findings)} evidence-grounded issue(s), including "
            f"{len(blocking)} high/critical issue(s) that should be resolved before merge."
        )
    else:
        verdict = Verdict.COMMENT
        summary = (
            f"Found {len(findings)} evidence-grounded low/medium issue(s); "
            "none are severe enough to block the merge."
        )

    raw_scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    quality_issues = grounded_by_category["bugs"] + grounded_by_category["code_quality"]
    scores = Scores(
        quality=_score(raw_scores.get("quality"), quality_issues),
        security=_score(raw_scores.get("security"), grounded_by_category["security"]),
        performance=_score(
            raw_scores.get("performance"), grounded_by_category["performance"]
        ),
    )

    if dropped:
        logger.warning("Discarded {} unsupported review item(s)", dropped)

    return GroundedReviewData(
        bugs=grounded_by_category["bugs"],
        security=grounded_by_category["security"],
        performance=grounded_by_category["performance"],
        code_quality=grounded_by_category["code_quality"],
        suggested_fixes=fixes,
        scores=scores,
        final_verdict=verdict,
        summary=summary,
        dropped_items=dropped,
    )
