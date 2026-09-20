"""Completely free deterministic job scoring.

No cloud service, API key, model download or subscription is required.
The scorer is deliberately transparent: every point comes from rules in
local_scoring.yaml and every result stores its score breakdown in SQLite.

Run:
    python -m app.local_score
    python -m app.local_score --rescore
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app import dedup, filters

CONFIG_PATH = "local_scoring.yaml"
OUTPUT_CSV = Path("data/local_scored_candidates.csv")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", filters.strip_html(text or "").lower()).strip()


def _contains(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term.lower() in text]


def _career_score(title: str, description: str, cfg: dict) -> tuple[int, list[str]]:
    maximum = int(cfg["weights"]["career"])
    t = _norm(title)
    d = _norm(description)
    combined = f"{t} {d}"
    signals: list[str] = []

    early = _contains(combined, cfg["career"]["early_signals"])
    if early:
        signals.extend(early)
        return maximum, signals

    if _contains(t, cfg["career"]["backend_signals"]):
        signals.append("backend role")
        return min(maximum, 23), signals
    if _contains(t, cfg["career"]["fullstack_signals"]):
        signals.append("full-stack role")
        return min(maximum, 22), signals
    if _contains(t, cfg["career"]["general_software_signals"]):
        signals.append("general software role")
        return min(maximum, 20), signals
    if _contains(t, cfg["career"]["secondary_signals"]):
        signals.append("secondary AI/ML target")
        return min(maximum, 17), signals
    return min(maximum, 12), ["role title is only a partial target match"]


def _stack_score(description: str, cfg: dict) -> tuple[int, list[str]]:
    maximum = int(cfg["weights"]["stack"])
    text = _norm(description)
    matched: list[str] = []
    raw = 0

    for group in cfg["tech_groups"]:
        terms = _contains(text, group["terms"])
        if terms:
            raw += int(group["points"])
            matched.append(f"{group['name']}: {', '.join(terms[:3])}")

    if raw == 0:
        secondary = _contains(text, cfg.get("secondary_tech", []))
        if secondary:
            return min(maximum, 10), [f"secondary stack: {', '.join(secondary[:4])}"]
        # A thin/empty description should be uncertain rather than treated
        # as proof of stack mismatch.
        if len(text) < 250:
            return min(maximum, 15), ["stack unclear from short description"]
        return min(maximum, 6), ["no strong primary-stack overlap detected"]

    return min(maximum, raw), matched


def _experience_score(description: str, cfg: dict) -> tuple[int, str]:
    maximum = int(cfg["weights"]["experience"])
    text = _norm(description)
    early_phrases = [
        "no experience required", "new grad", "graduate role", "entry level",
        "entry-level", "0-1 year", "0–1 year", "internship experience",
    ]
    if any(p in text for p in early_phrases):
        return maximum, "explicitly early-career friendly"

    years = filters.extract_explicit_required_years(description)
    if years is None:
        return min(maximum, 16), "no clear minimum-years requirement"
    if years <= 1:
        return maximum, f"{years}+ year requirement"
    if years == 2:
        return min(maximum, 17), "2-year requirement"
    if years == 3:
        return min(maximum, 12), "3-year requirement"
    return 0, f"{years}-year requirement"


def _location_score(location: str, cfg: dict) -> tuple[int, str]:
    maximum = int(cfg["weights"]["location"])
    text = _norm(location)
    if _contains(text, cfg["location"]["home_terms"]):
        return maximum, "home market"
    if _contains(text, cfg["location"]["europe_remote_terms"]):
        return min(maximum, 9), "Europe/EMEA remote"
    if filters.location_is_allowed(location):
        return min(maximum, 8), "target European location"
    return 0, "location outside target scope"


def _freshness_score(posted_at, cfg: dict) -> tuple[int, str]:
    maximum = int(cfg["weights"]["freshness"])
    dt = filters._parse_posted_at(posted_at)
    if dt is None:
        return min(maximum, 2), "posting date unknown"
    age = max(0, (datetime.now(timezone.utc) - dt).days)
    if age <= 3:
        return maximum, f"{age} day(s) old"
    if age <= 7:
        return min(maximum, 4), f"{age} days old"
    if age <= 14:
        return min(maximum, 2), f"{age} days old"
    return 0, f"{age} days old"


def _education_score(description: str, cfg: dict) -> tuple[int, str, list[str]]:
    maximum = int(cfg["weights"]["education"])
    text = _norm(description)
    gaps: list[str] = []
    phd_required = bool(re.search(r"\bph\.?d\b.{0,30}\b(required|must|minimum)\b|\b(required|must|minimum)\b.{0,30}\bph\.?d\b", text))
    masters_required = bool(re.search(r"\bmaster'?s?\b.{0,35}\b(required|must|minimum)\b|\b(required|must|minimum)\b.{0,35}\bmaster'?s?\b", text))

    if phd_required:
        gaps.append("PhD appears to be required")
        return 0, "PhD requirement", gaps
    if masters_required:
        gaps.append("Master's degree appears to be required")
        return min(maximum, 1), "Master's requirement", gaps
    if "bachelor" in text or "bsc" in text or "computer science degree" in text:
        return maximum, "Bachelor/CS degree aligns", gaps
    return min(maximum, 4), "education requirement compatible/unspecified", gaps


def _description_quality_score(description: str, cfg: dict) -> tuple[int, str]:
    maximum = int(cfg["weights"]["description_quality"])
    length = len(_norm(description))
    if length >= 1000:
        return maximum, "full JD"
    if length >= 500:
        return min(maximum, 4), "substantial JD"
    if length >= 250:
        return min(maximum, 3), "moderate JD"
    if length >= 100:
        return min(maximum, 2), "short JD"
    return min(maximum, 1), "very short/partial JD"


def _risks(description: str, cfg: dict) -> tuple[int, str, str, list[str]]:
    text = _norm(description)
    penalty = 0
    work_auth = "unclear"
    language = "low"
    reasons: list[str] = []

    auth_cfg = cfg["risk_patterns"]["no_sponsorship"]
    hits = _contains(text, auth_cfg["phrases"])
    if hits:
        penalty += int(auth_cfg["penalty"])
        work_auth = "high"
        reasons.append(f"work authorization/sponsorship restriction: {hits[0]}")

    lang_cfg = cfg["risk_patterns"]["local_language"]
    for lang in lang_cfg["languages"]:
        for req in lang_cfg["requirement_words"]:
            if re.search(rf"\b{re.escape(lang)}\b.{{0,45}}\b{re.escape(req)}\b|\b{re.escape(req)}\b.{{0,45}}\b{re.escape(lang)}\b", text):
                penalty += int(lang_cfg["penalty"])
                language = "high"
                reasons.append(f"{lang.title()} appears required")
                break
        if language == "high":
            break

    return penalty, work_auth, language, reasons


def evaluate(job: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()

    career, career_reasons = _career_score(job.get("title", ""), job.get("description", ""), cfg)
    stack, stack_reasons = _stack_score(job.get("description", ""), cfg)
    experience, experience_reason = _experience_score(job.get("description", ""), cfg)
    location, location_reason = _location_score(job.get("location", ""), cfg)
    freshness, freshness_reason = _freshness_score(job.get("posted_at"), cfg)
    education, education_reason, education_gaps = _education_score(job.get("description", ""), cfg)
    quality, quality_reason = _description_quality_score(job.get("description", ""), cfg)
    penalty, auth_risk, language_risk, risk_reasons = _risks(job.get("description", ""), cfg)

    raw = career + stack + experience + location + freshness + education + quality
    score = max(0, min(100, raw - penalty))

    thresholds = cfg["thresholds"]
    if score >= int(thresholds["apply"]):
        recommendation = "apply"
    elif score >= int(thresholds["consider"]):
        recommendation = "consider"
    else:
        recommendation = "skip"

    gaps = list(education_gaps)
    years = filters.extract_explicit_required_years(job.get("description", ""))
    if years is not None and years >= 3:
        gaps.append(f"Role asks for {years}+ years of experience")
    if stack <= 10:
        gaps.append("Limited overlap with the primary TypeScript/Node stack")
    if quality <= 2:
        gaps.append("Job description is too short for a confident deterministic score")

    strengths: list[str] = []
    if career >= 22:
        strengths.append("Role family/level aligns closely")
    if stack >= 20:
        strengths.append("Strong primary-stack overlap")
    if experience >= 17:
        strengths.append("Experience requirement is early-career compatible")
    if location >= 9:
        strengths.append("Location setup is especially favorable")

    breakdown = {
        "career": {"score": career, "max": cfg["weights"]["career"], "reason": "; ".join(career_reasons)},
        "stack": {"score": stack, "max": cfg["weights"]["stack"], "reason": "; ".join(stack_reasons)},
        "experience": {"score": experience, "max": cfg["weights"]["experience"], "reason": experience_reason},
        "location": {"score": location, "max": cfg["weights"]["location"], "reason": location_reason},
        "freshness": {"score": freshness, "max": cfg["weights"]["freshness"], "reason": freshness_reason},
        "education": {"score": education, "max": cfg["weights"]["education"], "reason": education_reason},
        "description_quality": {"score": quality, "max": cfg["weights"]["description_quality"], "reason": quality_reason},
        "penalty": penalty,
    }

    return {
        "match_score": score,
        "recommendation": recommendation,
        "career_level_fit": "strong" if career >= 22 else "acceptable" if career >= 18 else "weak",
        "tech_stack_fit": "strong" if stack >= 22 else "acceptable" if stack >= 15 else "weak",
        "experience_fit": "strong" if experience >= 17 else "acceptable" if experience >= 12 else "weak",
        "location_fit": "strong" if location >= 9 else "acceptable" if location >= 8 else "unclear",
        "work_authorization_risk": auth_risk,
        "language_risk": language_risk,
        "genuine_gaps": "; ".join(gaps) if gaps else "No major deterministic gap detected.",
        "transferable_strengths": "; ".join(strengths) if strengths else "Some transferable overlap; review the JD manually.",
        "risk_factors": "; ".join(risk_reasons) if risk_reasons else "No explicit local-rule risk detected.",
        "matched_keywords": "; ".join(stack_reasons),
        "score_breakdown": json.dumps(breakdown, ensure_ascii=False),
        "rule_version": cfg["version"],
    }


def write_csv(conn, path: Path = OUTPUT_CSV) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(dedup.iter_local_scored_candidates(conn))
    fields = [
        "match_score", "recommendation", "company", "title", "location",
        "career_level_fit", "tech_stack_fit", "experience_fit", "location_fit",
        "work_authorization_risk", "language_risk", "transferable_strengths",
        "genuine_gaps", "risk_factors", "matched_keywords", "url", "posted_at",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def run(rescore: bool = False, limit: int | None = None) -> int:
    cfg = load_config()
    scored = 0
    with dedup.connect() as conn:
        queue = dedup.get_local_score_candidates(conn, rescore=rescore)
        if limit:
            queue = queue[:limit]

        for i, job in enumerate(queue, 1):
            result = evaluate(job, cfg)
            dedup.save_local_evaluation(conn, job["url"], result)
            scored += 1
            print(
                f"[{i}/{len(queue)}] {result['match_score']:3d} "
                f"{result['recommendation']:8s} | {job['company']} | {job['title']}"
            )

        total = write_csv(conn)
        conn.commit()
    print(f"\nScored {scored} job(s). {total} local scores in {OUTPUT_CSV}.")
    return scored


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rescore", action="store_true", help="Recompute existing local scores after changing the rules.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(rescore=args.rescore, limit=args.limit)
