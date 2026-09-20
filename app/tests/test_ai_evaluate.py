"""Offline tests for OpenAI evaluation helpers (no API calls)."""
import os
from pathlib import Path

from app import ai_evaluate, dedup, filters

TEST_DB = "data/test_ai_evaluate.sqlite3"
TEST_CSV = Path("data/test_scored.csv")


def test_profile_prompt_and_db_roundtrip():
    for path in (TEST_DB, str(TEST_CSV)):
        if os.path.exists(path):
            os.remove(path)

    profile = ai_evaluate.load_profile("profile.ayush.example.yaml")
    assert profile["identity"]["experience_level"] == "early-career"
    assert "TypeScript" in profile["core_stack"]["strongest"]

    job = {
        "company": "ExampleCo",
        "title": "Junior Backend Engineer",
        "location": "Berlin, Germany",
        "url": "https://example.com/jobs/123",
        "posted_at": "2026-09-20",
        "description": "<p>Build <b>TypeScript</b> and Node.js services with PostgreSQL.</p> " + "A" * 500,
    }
    prompt = ai_evaluate.build_user_prompt(profile, job)
    assert "TypeScript" in prompt
    assert "<b>" not in prompt
    assert "ExampleCo" in prompt
    assert "Early-career title signal: True" in prompt

    with dedup.connect(TEST_DB) as conn:
        dedup.save_details(conn, job, passed_filters=True)
        assert len(dedup.get_unevaluated_candidates(conn)) == 1

        fake = {
            "match_score": 94,
            "recommendation": "apply",
            "career_level_fit": "strong",
            "tech_stack_fit": "strong",
            "experience_fit": "strong",
            "location_fit": "strong",
            "work_authorization_risk": "unclear",
            "language_risk": "low",
            "genuine_gaps": "Work authorization wording is not stated.",
            "transferable_strengths": "Direct TypeScript/Node/PostgreSQL overlap.",
            "risk_factors": "Verify country-specific eligibility before applying.",
        }
        assert ai_evaluate._validate_evaluation(fake) == fake
        dedup.save_evaluation(conn, job["url"], fake, model="gpt-5.6-luna")
        assert len(dedup.get_unevaluated_candidates(conn)) == 0
        assert ai_evaluate.write_csv(conn, TEST_CSV) == 1

    text = TEST_CSV.read_text()
    assert "94" in text and "apply" in text

    os.remove(TEST_DB)
    os.remove(TEST_CSV)


def test_truncated_prompt_note():
    profile = ai_evaluate.load_profile("profile.ayush.example.yaml")
    job = {
        "company": "ExampleCo",
        "title": "Software Engineer",
        "location": "Budapest, Hungary",
        "url": "https://example.com/jobs/456",
        "posted_at": "2026-09-20",
        "description": "Short aggregator teaser...",
    }
    prompt = ai_evaluate.build_user_prompt(profile, job)
    assert "description appears truncated" in prompt
    assert filters.looks_truncated(job["description"])
