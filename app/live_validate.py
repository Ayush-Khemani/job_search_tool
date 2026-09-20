"""Best-effort live-job verification.

This stage rechecks candidate URLs before AI scoring/application review. It
uses conservative closure detection: obvious 404/410 responses and a short
list of strong "position closed" phrases are marked dead. Ambiguous pages stay
live so temporary bot protection or unusual career-site wording does not cause
false removals.
"""
import argparse
import sys
from urllib.parse import urlparse

import httpx

from app import dedup

USER_AGENT = "job-search-pipeline/0.2 (personal use)"
TIMEOUT = 15.0

STRONG_CLOSED_PHRASES = (
    "this job is no longer available",
    "this position is no longer available",
    "this position has been filled",
    "this job has been filled",
    "job posting has expired",
    "job has expired",
    "position is closed",
    "position has closed",
    "job is closed",
    "no longer accepting applications",
    "we are no longer accepting applications",
)


def _looks_like_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def check_url(url: str) -> tuple[bool, str]:
    if not _looks_like_http_url(url):
        return False, "invalid URL"

    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
    except httpx.RequestError as exc:
        # Network/bot failures are uncertain, not proof that a job is dead.
        return True, f"verification inconclusive: {type(exc).__name__}"

    if resp.status_code in {404, 410}:
        return False, f"HTTP {resp.status_code}"
    if resp.status_code >= 500:
        return True, f"verification inconclusive: HTTP {resp.status_code}"
    if resp.status_code in {401, 403, 429}:
        return True, f"verification blocked: HTTP {resp.status_code}"
    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}"

    # Limit text inspected to keep this cheap even for very large pages.
    text = (resp.text or "")[:500_000].lower()
    for phrase in STRONG_CLOSED_PHRASES:
        if phrase in text:
            return False, f"closure text: {phrase}"

    return True, f"HTTP {resp.status_code}"


def run(limit: int | None = None, include_filtered: bool = False) -> tuple[int, int]:
    checked = 0
    dead = 0

    with dedup.connect() as conn:
        jobs = list(dedup.iter_jobs_for_live_check(conn, passed_only=not include_filtered))
        if limit:
            jobs = jobs[:limit]

        for i, job in enumerate(jobs, 1):
            is_live, reason = check_url(job["url"])
            dedup.set_live_status(conn, job["url"], is_live, reason)
            conn.commit()
            checked += 1
            dead += 0 if is_live else 1
            state = "LIVE" if is_live else "CLOSED"
            print(f"[{i}/{len(jobs)}] {state:6s} | {job['company']} | {job['title']} | {reason}")

    return checked, dead


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--include-filtered",
        action="store_true",
        help="Also verify jobs that failed deterministic filters.",
    )
    args = parser.parse_args()

    checked, dead = run(args.limit, args.include_filtered)
    print(f"\nVerified {checked} job(s); {dead} marked closed.")
    if checked == 0:
        sys.exit(0)
