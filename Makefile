SHELL := /bin/bash
.DEFAULT_GOAL := run

.PHONY: run free score test validate evaluate web

run:
	@companies_flag=""; aggregators_flag=""; discovery_flag=""; company_flag=""; \
	read -rp "Fetch from companies.yaml? [Y/n] " ans; \
	[[ "$$ans" =~ ^[Nn] ]] && companies_flag="--skip-companies"; \
	read -rp "Fetch from aggregators.yaml? [Y/n] " ans; \
	[[ "$$ans" =~ ^[Nn] ]] && aggregators_flag="--skip-aggregators"; \
	read -rp "Auto-discover new companies from aggregator results? [Y/n] " ans; \
	[[ "$$ans" =~ ^[Nn] ]] && discovery_flag="--skip-discovery"; \
	read -rp "Only one company slug? (blank = all) " slug; \
	[[ -n "$$slug" ]] && company_flag="--company $$slug"; \
	python -m app.main $$companies_flag $$aggregators_flag $$discovery_flag $$company_flag

# Completely free end-to-end run. Adzuna entries are skipped with warnings if
# credentials are absent; free sources and direct public ATS boards continue.
free:
	python -m app.main
	python -m app.live_validate
	python -m app.local_score

score:
	python -m app.local_score

validate:
	python -m app.live_validate

test:
	python -m pytest app/ -q

# Optional paid/cloud scorer. Not needed for the free workflow.
evaluate:
	@dry_run_flag=""; limit_flag=""; \
	read -rp "Do you want a dry run? [Y/n] " ans; \
	[[ ! "$$ans" =~ ^[Nn] ]] && dry_run_flag="--dry-run"; \
	read -rp "Do you want to set a limit? (blank = all) " limit_val; \
	[[ -n "$$limit_val" ]] && limit_flag="--limit $$limit_val"; \
	python -m app.ai_evaluate $$dry_run_flag $$limit_flag

web:
	DB_PATH=$(CURDIR)/data/seen_jobs.sqlite3 npm --prefix web run dev
