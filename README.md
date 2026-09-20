# European Job Search Tool — Free Local First

A local-first job discovery and matching pipeline for early-career software roles across Europe.

The default workflow is now **completely free**: no OpenAI key, no Anthropic key, no Ollama, and no cloud server are required. The tool fetches jobs, filters obvious mismatches, deduplicates them, checks whether candidate links are still live, calculates a transparent 0–100 local fit score, and shows the results in a local dashboard.

OpenAI remains an optional later-stage evaluator. Ollama/local-LLM support can be added on top without replacing the deterministic scorer.

## Search focus

The repository is tuned for:
- junior / graduate / entry-level software roles;
- backend and full-stack positions first;
- TypeScript / JavaScript / Node.js / React;
- PostgreSQL / Supabase / GraphQL / Redis / RabbitMQ / Pub/Sub;
- Docker / Kubernetes;
- selected applied-AI / ML-product roles;
- mainland Europe, EMEA and Europe-compatible remote work.

Obvious Senior, Staff, Principal, Lead and Engineering Manager titles are rejected before scoring.

## Completely free workflow

### Windows PowerShell

```powershell
git clone https://github.com/Ayush-Khemani/job_search_tool.git
cd job_search_tool

py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item profile.ayush.example.yaml profile.yaml

python -m app.free_run
```

### macOS / Linux

```bash
git clone https://github.com/Ayush-Khemani/job_search_tool.git
cd job_search_tool

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp profile.ayush.example.yaml profile.yaml

python -m app.free_run
```

That single command runs:

1. job fetch + deterministic filtering;
2. deduplication in local SQLite;
3. live/closed-link verification;
4. completely local 0–100 scoring.

No API key is required for the free path.

## Free local score

`app/local_score.py` uses the transparent rules in `local_scoring.yaml`.

Maximum score: **100 points**.

| Dimension | Max |
|---|---:|
| Career level / role family | 25 |
| Primary tech-stack overlap | 30 |
| Required experience | 20 |
| Location fit | 10 |
| Posting freshness | 5 |
| Education compatibility | 5 |
| Job-description confidence | 5 |

Explicit risk wording can reduce the score, for example:
- no sponsorship / existing work-right requirement;
- a mandatory local-language requirement.

Default recommendation bands:
- **90–100:** Apply
- **80–89:** Consider
- **below 80:** Skip / lower priority

These are prioritization rules, not claims that a company will interview or hire you. Every local score stores its full point breakdown so it can be audited and tuned.

To score only newly discovered jobs:

```bash
python -m app.local_score
```

To recalculate all local scores after editing `local_scoring.yaml`:

```bash
python -m app.local_score --rescore
```

Output:

```
data/local_scored_candidates.csv
```

## Local dashboard

Install the dashboard dependencies once:

```bash
cd web
npm install
cd ..
```

Then start it:

```bash
npm --prefix web run dev
```

Or, where GNU Make is available:

```bash
make web
```

The board reads the same local SQLite database. It displays:
- score;
- recommendation;
- whether the score came from **Local rules** or **OpenAI**;
- career, stack, experience and location fit;
- work-authorization and language risks;
- matched technologies;
- the full local point breakdown;
- strengths, gaps and risk factors;
- your application status and notes.

## Pipeline

1. **Fetch — `app/main.py`**
   - public company ATS boards: Greenhouse, Ashby, Workable, Lever, SmartRecruiters;
   - broad discovery: Arbeitnow, optional Adzuna, Remotive.

2. **Filter — `app/filters.py`**
   - role/title;
   - seniority;
   - Europe-compatible location;
   - explicit minimum-years requirement;
   - posting age;
   - obvious stack mismatch.

3. **Dedup — `app/dedup.py`**
   - exact URL;
   - normalized company + title + location;
   - persistent local history.

4. **Live validation — `app/live_validate.py`**
   - clear 404/410/closed postings are marked dead;
   - bot blocks, rate limits and temporary server errors remain inconclusive instead of being falsely marked closed.

5. **Free local evaluation — `app/local_score.py`**
   - transparent deterministic 0–100 score;
   - no network/model/API call.

6. **Optional OpenAI evaluation — `app/ai_evaluate.py`**
   - only runs when explicitly invoked and an OpenAI API key is configured;
   - when both evaluations exist, the dashboard prefers the richer OpenAI result while preserving the free local score in SQLite.

7. **Review board — `web/`**
   - local Next.js app over the same SQLite database.

## What is free and what is optional?

### Free with no account/key
- direct public ATS fetching;
- Arbeitnow;
- Remotive public feed;
- filtering;
- deduplication;
- live validation;
- local deterministic scoring;
- SQLite storage;
- CSV output;
- local dashboard.

### Optional
- **Adzuna** — requires Adzuna credentials if you want those configured searches. Missing credentials do not stop the other sources.
- **OpenAI** — requires separate OpenAI API billing and is not needed for the free workflow.
- **Ollama** — not required yet. A later local-LLM layer can be added after Ollama is installed.

## Configuration

### `filters.yaml`
Controls hard pre-filtering: titles, seniority, locations, maximum experience requirement, freshness and stack rules.

### `local_scoring.yaml`
Controls the free score weights, stack groups, recommendation thresholds and explicit-risk penalties.

### `aggregators.yaml`
Controls broad-source searches.

### `companies.yaml`
Direct ATS registry.

### `profile.ayush.example.yaml`
Sanitized professional profile. Copy it to the gitignored `profile.yaml` before adding any private personal/work-authorization context.

## Local data

Main database:

```
data/seen_jobs.sqlite3
```

Outputs:
- `data/candidates.csv`
- `data/local_scored_candidates.csv`
- `data/scored_candidates.csv` when the optional OpenAI evaluator is used.

The database keeps:
- seen jobs;
- full JDs;
- filter decisions;
- live/dead status;
- local evaluations;
- optional OpenAI evaluations;
- your application status and notes.

## Tests

```bash
pytest -q app/tests
```

GitHub Actions validates both the Python pipeline and the web dashboard build.

## Current limitations

- Workday does not yet have a dedicated direct client.
- Public feeds never cover every job on the internet; the direct ATS registry should keep expanding.
- Live validation is intentionally conservative around bot protection.
- Deterministic scoring cannot understand nuanced JDs as deeply as an LLM. That is exactly where a later Ollama layer will help.
- Work authorization must still be confirmed against the actual job and country.

## License

MIT
