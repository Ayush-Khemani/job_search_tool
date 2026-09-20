"""Stage 2: AI evaluation via the OpenAI Responses API.

Reads jobs that passed deterministic filters but have not been scored yet,
sends each posting together with the candidate profile, and stores a structured
fit assessment in SQLite.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import dedup
from app import filters

load_dotenv()

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
OUTPUT_CSV = Path("data/scored_candidates.csv")

REQUIRED_EVAL_FIELDS = [
    "match_score",
    "recommendation",
    "career_level_fit",
    "tech_stack_fit",
    "experience_fit",
    "location_fit",
    "work_authorization_risk",
    "language_risk",
    "genuine_gaps",
    "transferable_strengths",
    "risk_factors",
]

SYSTEM_PROMPT = """You are a strict early-career software job fit evaluator.

Evaluate FUNCTIONAL FIT, not superficial keyword overlap. The candidate is a
recent Computer Science graduate targeting junior/graduate/entry-level backend,
full-stack and selected AI/software roles in Europe.

Important scoring rules:
- Senior/staff/principal/lead/manager roles are not appropriate.
- Weight actual responsibilities and required experience more than title.
- Strongest stack fit is TypeScript/JavaScript, Node.js/NestJS/Express, React,
  PostgreSQL/Supabase, GraphQL, Redis, RabbitMQ/PubSub, Docker and Kubernetes.
- Python/FastAPI/AI experience can count as transferable secondary experience,
  but a Python-only role should not receive an excellent score merely because
  the candidate has used Python.
- Treat 3+ years as a real gap for a recent graduate unless the JD clearly
  frames equivalent project/internship experience as acceptable.
- Distinguish a hard requirement from a preference/nice-to-have.
- Be conservative about language requirements and country-specific remote rules.
- Do not assume visa sponsorship. If the posting is unclear, report uncertainty.
- A 95+ score should be rare and mean an unusually close match.

Return ONLY one valid JSON object with exactly these fields:
match_score (0-100 integer), recommendation (apply|consider|skip),
career_level_fit (strong|acceptable|weak|mismatch),
tech_stack_fit (strong|acceptable|weak|mismatch),
experience_fit (strong|acceptable|weak|mismatch),
location_fit (strong|acceptable|unclear|mismatch),
work_authorization_risk (low|medium|high|unclear),
language_risk (low|medium|high|unclear),
genuine_gaps, transferable_strengths, risk_factors.
"""


def load_profile(path: str | None = None) -> dict:
    candidates = [path] if path else ["profile.yaml", "profile.ayush.example.yaml"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            with open(candidate, encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(
        "No profile found. Copy profile.ayush.example.yaml to profile.yaml and edit if needed."
    )


def build_user_prompt(profile: dict, job: dict) -> str:
    raw_description = job.get("description", "")
    description = filters.strip_html(raw_description).strip() or "(no JD text available)"
    partial_note = ""
    if raw_description and filters.looks_truncated(raw_description):
        partial_note = (
            "\nNOTE: The description appears truncated. Do not invent missing "
            "requirements. Lower confidence and explain uncertainty where needed.\n"
        )

    years = filters.extract_explicit_required_years(raw_description)
    seniority_hint = filters.has_preferred_seniority_signal(job.get("title", ""))

    return f"""CANDIDATE PROFILE:
{yaml.dump(profile, sort_keys=False, allow_unicode=True)}

JOB:
Company: {job['company']}
Title: {job['title']}
Location: {job['location']}
URL: {job['url']}
Posted: {job.get('posted_at') or 'unknown'}
Early-career title signal: {seniority_hint}
Explicit minimum years detected: {years if years is not None else 'none'}
{partial_note}
DESCRIPTION:
{description}
"""


def _validate_evaluation(data: dict) -> dict:
    missing = [field for field in REQUIRED_EVAL_FIELDS if field not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    score = data["match_score"]
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError(f"Invalid match_score: {score!r}")
    if data["recommendation"] not in {"apply", "consider", "skip"}:
        raise ValueError(f"Invalid recommendation: {data['recommendation']!r}")
    return data


def evaluate_one(client, profile: dict, job: dict, max_retries: int = 1) -> dict:
    prompt = build_user_prompt(profile, job)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.responses.create(
                model=MODEL,
                instructions=SYSTEM_PROMPT,
                input=prompt,
            )
            output = (response.output_text or "").strip()
            # Tolerate models that wrap JSON in a markdown fence.
            if output.startswith(chr(96) * 3):
                output = output.strip(chr(96)).strip()
                if output.lower().startswith("json"):
                    output = output[4:].lstrip()
            return _validate_evaluation(json.loads(output))
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            prompt += "\n\nRetry: return one valid JSON object only, with every required field."

    raise RuntimeError(f"OpenAI evaluation failed for {job['url']}: {last_error}")


def write_csv(conn, path: Path = OUTPUT_CSV) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(dedup.iter_scored_candidates(conn))
    fields = [
        "match_score", "recommendation", "company", "title", "location",
        "transferable_strengths", "genuine_gaps", "risk_factors", "url", "posted_at",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--profile", default=None, help="Optional profile YAML path")
    args = parser.parse_args()

    profile = load_profile(args.profile)

    with dedup.connect() as conn:
        queue = dedup.get_unevaluated_candidates(conn)
        if args.limit:
            queue = queue[: args.limit]

        print(f"{len(queue)} candidate(s) queued for OpenAI evaluation.")
        if not queue:
            sys.exit(0)

        if args.dry_run:
            for job in queue:
                print(f"WOULD EVALUATE | {job['company']:24s} | {job['title']}")
            sys.exit(0)

        try:
            from openai import OpenAI
        except ImportError:
            sys.exit("Missing dependency: pip install openai")

        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("OPENAI_API_KEY is not set. Fetch/filter/dedup still work without it.")

        client = OpenAI()

        for i, job in enumerate(queue, 1):
            try:
                evaluation = evaluate_one(client, profile, job)
            except Exception as exc:
                print(
                    f"[WARN] {job['company']} — {job['title']}: evaluation failed — {exc}",
                    file=sys.stderr,
                )
                continue

            dedup.save_evaluation(conn, job["url"], evaluation, MODEL)
            conn.commit()
            print(
                f"[{i}/{len(queue)}] {evaluation['match_score']:3d} "
                f"{evaluation['recommendation']:9s} | {job['company']:24s} | {job['title']}"
            )

        total = write_csv(conn)
        print(f"\nWrote {total} scored candidates to {OUTPUT_CSV}.")
