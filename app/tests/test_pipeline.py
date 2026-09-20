"""Tests for the Europe/early-career deterministic filters and dedup."""
import os
from datetime import datetime, timezone

from app import dedup, filters

TEST_DB = "data/test_seen_jobs.sqlite3"

SAMPLE_JOBS = [
    # Strong early-career Europe fit.
    {"company": "Example", "title": "Junior Backend Engineer",
     "location": "Berlin, Germany", "url": "https://example.com/jobs/1",
     "posted_at": "2026-09-19T10:00:00Z",
     "description": "TypeScript, Node.js, PostgreSQL and Docker. 1+ years experience."},
    # Generic title is allowed if not explicitly senior.
    {"company": "Example", "title": "Software Engineer",
     "location": "Budapest, Hungary", "url": "https://example.com/jobs/2",
     "posted_at": "2026-09-18",
     "description": "Build Node.js APIs with PostgreSQL."},
    # Hard seniority rejection.
    {"company": "Example", "title": "Senior Software Engineer",
     "location": "Munich, Germany", "url": "https://example.com/jobs/3",
     "posted_at": "2026-09-20",
     "description": "TypeScript and Node.js."},
    # Explicit experience threshold too high.
    {"company": "Example", "title": "Backend Engineer",
     "location": "Amsterdam, Netherlands", "url": "https://example.com/jobs/4",
     "posted_at": "2026-09-20",
     "description": "At least 5 years of professional software experience. TypeScript."},
    # Europe country should pass even if city is absent.
    {"company": "Example", "title": "Graduate Software Engineer",
     "location": "Portugal", "url": "https://example.com/jobs/5",
     "posted_at": "2026-09-20",
     "description": "JavaScript, React and Node.js."},
    # US-only should fail.
    {"company": "Example", "title": "Junior Software Engineer",
     "location": "Remote US", "url": "https://example.com/jobs/6",
     "posted_at": "2026-09-20",
     "description": "TypeScript."},
    # Obvious non-target engineering role.
    {"company": "Example", "title": "Sales Engineer",
     "location": "Paris, France", "url": "https://example.com/jobs/7",
     "posted_at": "2026-09-20",
     "description": "TypeScript."},
    # Stale posting with parseable date should fail.
    {"company": "Example", "title": "Junior Full-Stack Engineer",
     "location": "Madrid, Spain", "url": "https://example.com/jobs/8",
     "posted_at": "2025-01-01",
     "description": "React and Node.js."},
    # Duplicate of first by company/title/location but a different URL.
    {"company": "Example", "title": "Junior Backend Engineer",
     "location": "Berlin, Germany", "url": "https://example.com/jobs/1-repost",
     "posted_at": "2026-09-20",
     "description": "TypeScript, Node.js, PostgreSQL and Docker."},
]


def test_filters_and_dedup():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    passed = [job for job in SAMPLE_JOBS if filters.passes_filters(job)]
    assert [j["url"] for j in passed] == [
        "https://example.com/jobs/1",
        "https://example.com/jobs/2",
        "https://example.com/jobs/5",
        "https://example.com/jobs/1-repost",
    ]

    with dedup.connect(TEST_DB) as conn:
        kept = []
        for job in passed:
            if dedup.is_new(conn, job):
                dedup.mark_seen(conn, job)
                kept.append(job)
        assert len(kept) == 3

    os.remove(TEST_DB)


def test_seniority_location_and_experience_helpers():
    assert filters.title_is_relevant("Junior Backend Engineer")
    assert filters.title_is_relevant("Software Engineer")
    assert not filters.title_is_relevant("Senior Software Engineer")
    assert not filters.title_is_relevant("Staff Backend Engineer")
    assert not filters.title_is_relevant("Sales Engineer")

    assert filters.location_is_allowed("Budapest, Hungary")
    assert filters.location_is_allowed("Remote - EMEA")
    assert filters.location_is_allowed("Barcelona, Spain")
    assert not filters.location_is_allowed("Remote US")

    assert filters.extract_explicit_required_years("At least 5 years of professional experience") == 5
    assert filters.extract_explicit_required_years("2+ years of software experience") == 2
    assert not filters.experience_requirement_is_allowed("Minimum 4 years of software experience")
    assert filters.experience_requirement_is_allowed("2+ years of software experience")


def test_freshness_parser():
    fixed_now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    assert filters.posted_at_is_fresh("2026-09-19", now=fixed_now)
    assert not filters.posted_at_is_fresh("2026-08-01", now=fixed_now)
    assert filters.posted_at_is_fresh(None, now=fixed_now)
    assert filters.posted_at_is_fresh("not-a-date", now=fixed_now)
