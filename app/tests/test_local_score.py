"""Tests for the completely free deterministic scoring engine."""
import json
import os

from app import dedup, local_score

TEST_DB = "data/test_local_score.sqlite3"


def strong_job():
    return {
        "url": "https://example.com/jobs/strong",
        "company": "StrongCo",
        "title": "Junior Backend Engineer",
        "location": "Budapest, Hungary",
        "posted_at": None,
        "description": (
            "Entry-level role for a Bachelor's degree graduate. "
            "Build TypeScript and Node.js services with React, PostgreSQL, GraphQL, "
            "Redis, RabbitMQ, Docker and Kubernetes. No experience required. "
            + "Work with product and engineering teams. " * 40
        ),
    }


def risky_job():
    return {
        "url": "https://example.com/jobs/risky",
        "company": "RiskyCo",
        "title": "Software Engineer",
        "location": "Berlin, Germany",
        "posted_at": None,
        "description": (
            "We use TypeScript, Node.js and PostgreSQL. "
            "At least 3 years of professional software experience required. "
            "German C1 required. No visa sponsorship is available. "
            "Bachelor's degree required. "
            + "Build and maintain services. " * 40
        ),
    }


def test_strong_match_scores_high_and_is_explainable():
    result = local_score.evaluate(strong_job())
    assert result["match_score"] >= 90
    assert result["recommendation"] == "apply"
    assert result["tech_stack_fit"] == "strong"
    assert result["career_level_fit"] == "strong"
    breakdown = json.loads(result["score_breakdown"])
    assert breakdown["career"]["score"] == 25
    assert breakdown["stack"]["score"] >= 20
    assert breakdown["penalty"] == 0


def test_risks_reduce_score_and_are_reported():
    result = local_score.evaluate(risky_job())
    assert result["match_score"] < 80
    assert result["recommendation"] == "skip"
    assert result["work_authorization_risk"] == "high"
    assert result["language_risk"] == "high"
    breakdown = json.loads(result["score_breakdown"])
    assert breakdown["penalty"] == 14
    assert "3+ years" in result["genuine_gaps"]


def test_local_score_db_roundtrip():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    job = strong_job()
    with dedup.connect(TEST_DB) as conn:
        dedup.save_details(conn, job, passed_filters=True)
        queue = dedup.get_local_score_candidates(conn)
        assert len(queue) == 1

        result = local_score.evaluate(job)
        dedup.save_local_evaluation(conn, job["url"], result)
        conn.commit()

        assert dedup.get_local_score_candidates(conn) == []
        rows = list(dedup.iter_local_scored_candidates(conn))
        assert len(rows) == 1
        assert rows[0]["match_score"] == result["match_score"]

    os.remove(TEST_DB)
