"""Cross-platform, completely free end-to-end runner.

This is the easiest entry point on Windows/macOS/Linux:
    python -m app.free_run

It fetches jobs, applies deterministic filters/dedup, validates candidate
links, and calculates transparent local scores. No OpenAI/Ollama/cloud key
is used.
"""
from app import aggregator_clients, discover_companies, live_validate, local_score, main


def run() -> None:
    print("=== 1/3 Fetch + filter + dedup ===")
    companies = main.load_yaml_list("companies.yaml", "companies")
    aggregators = main.load_yaml_list("aggregators.yaml", "aggregators")
    candidates = main.run(companies, aggregators)
    main.write_csv(candidates)
    print(f"Wrote {len(candidates)} new candidates to {main.OUTPUT_CSV}")

    added = discover_companies.append_new_companies(aggregator_clients.DISCOVERED_COMPANIES)
    if added:
        suffix = "y" if len(added) == 1 else "ies"
        print(f"Discovered {len(added)} new direct ATS compan{suffix}.")

    print("\n=== 2/3 Verify live postings ===")
    checked, dead = live_validate.run()
    print(f"Verified {checked} candidate link(s); {dead} marked closed.")

    print("\n=== 3/3 Free local scoring ===")
    local_score.run()

    print("\nDone. Open data/local_scored_candidates.csv or start the local dashboard.")


if __name__ == "__main__":
    run()
