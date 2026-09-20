# European AI Job Search Tool

A customized fork for high-signal early-career software job discovery across Europe.

The pipeline fetches roles from first-party ATS boards and aggregators, rejects obvious mismatches deterministically, deduplicates everything in SQLite, verifies whether candidate links are still live, and can optionally score the remaining jobs with the OpenAI API.

## Search focus

This branch is tuned for:
- junior / graduate / entry-level software roles;
- backend and full-stack positions first;
- TypeScript / JavaScript / Node.js / React ecosystems;
- PostgreSQL / Supabase / GraphQL / Redis / RabbitMQ / PubSub;
- Docker / Kubernetes;
- selected applied-AI / ML-product roles;
- mainland Europe, EMEA and Europe-compatible remote work.

Obvious Senior, Staff, Principal, Lead and Engineering Manager titles are rejected before AI scoring.

## Pipeline

1. **Fetch** — `app/main.py`
   - Direct ATS boards: Greenhouse, Ashby, Workable, Lever, SmartRecruiters.
   - Broad discovery: Arbeitnow, Adzuna and Remotive.
   - Adzuna country selection is configurable instead of hard-coded to Canada.

2. **Deterministic filtering** — `app/filters.py`
   - target role/title;
   - seniority;
   - Europe-compatible location;
   - explicit minimum-years requirements;
   - posting age;
   - obvious stack mismatches.

3. **Deduplication** — `app/dedup.py`
   - exact URL;
   - normalized company + title + location;
   - persistent SQLite history.

4. **Live validation** — `app/live_validate.py`
   - marks clear 404/410/closed postings as dead;
   - treats bot blocks, rate limits and temporary server errors as inconclusive rather than falsely closing a role.

5. **OpenAI fit evaluation** — `app/ai_evaluate.py`
   - overall 0–100 match score;
   - Apply / Consider / Skip;
   - career-level fit;
   - tech-stack fit;
   - experience fit;
   - location fit;
   - work-authorization risk;
   - language risk;
   - concrete strengths, gaps and risk factors.

6. **Review board** — `web/`
   - local Next.js UI over the same SQLite database.

## Important: ChatGPT subscription vs API

A ChatGPT Plus/Pro subscription does **not** provide API credits. The OpenAI API is billed separately.

The entire fetch/filter/dedup/live-validation pipeline works without an OpenAI key. Only AI scoring requires `OPENAI_API_KEY`.

The default scoring model in this branch is:

```
gpt-5.6-luna
```

Override it with `OPENAI_MODEL` in your local `.env`.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
cp profile.ayush.example.yaml profile.yaml
```

`profile.yaml` is gitignored. Put any private work-authorization or personal context there rather than committing it to this public repository.

If you want Adzuna coverage, add:

```
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
```

If you want OpenAI scoring, add:

```
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

## Recommended daily flow

```bash
python -m app.main
python -m app.live_validate
python -m app.ai_evaluate --limit 50
```

Or use:

```bash
make run
make validate
make evaluate
```

The AI stage only sees jobs that already survived the deterministic filters and are not known to be closed.

## Main configuration

### `filters.yaml`
Controls:
- accepted role families;
- seniority exclusions;
- maximum explicit experience requirement;
- maximum posting age;
- Europe location patterns;
- stack rules.

### `aggregators.yaml`
Includes:
- Arbeitnow for Europe-focused ATS aggregation;
- country-specific Adzuna searches;
- Remotive for Europe-compatible remote roles.

### `companies.yaml`
A smaller direct-ATS registry of globally/Europe-relevant companies. Keep this high-signal; broad discovery should come from the aggregators.

### `profile.ayush.example.yaml`
A sanitized professional matching profile. Copy it to `profile.yaml` locally before adding private context.

## Data

Local state lives in:

```
data/seen_jobs.sqlite3
```

The database stores:
- all seen jobs;
- full descriptions;
- filter decisions;
- live/dead verification;
- OpenAI evaluations;
- user application status/notes.

Outputs:
- `data/candidates.csv`
- `data/scored_candidates.csv`

## Tests

```bash
pytest -q app/tests
```

GitHub Actions also runs the test suite on this branch.

## Current limitations

- Workday does not yet have a dedicated direct client.
- ATS/company coverage should keep growing as verified European boards are discovered.
- Live validation is intentionally conservative and cannot always distinguish a bot challenge from a real posting.
- Work authorization must still be checked against the actual JD and country rules; the scorer does not assume sponsorship.

## License

MIT
