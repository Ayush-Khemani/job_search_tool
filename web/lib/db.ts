import Database from "better-sqlite3";
import path from "node:path";

const DB_PATH = process.env.DB_PATH || path.join(process.cwd(), "..", "data", "seen_jobs.sqlite3");

export const MY_STATUS_VALUES = ["applied", "interview", "rejected", "skipped", "silence"] as const;
export type MyStatus = (typeof MY_STATUS_VALUES)[number];

export type JobRow = {
  url: string;
  company: string;
  title: string;
  location: string;
  posted_at: string | null;
  description: string;
  passed_filters: number;
  match_score: number | null;
  recommendation: string | null;
  career_level_fit: string | null;
  tech_stack_fit: string | null;
  experience_fit: string | null;
  location_fit: string | null;
  work_authorization_risk: string | null;
  language_risk: string | null;
  genuine_gaps: string | null;
  transferable_strengths: string | null;
  risk_factors: string | null;
  matched_keywords: string | null;
  score_breakdown: string | null;
  evaluation_source: "openai" | "local" | null;
  my_status: MyStatus | null;
  notes: string | null;
  status: string;
};

let db: Database.Database | null = null;

function getDb(): Database.Database {
  if (db) return db;
  db = new Database(DB_PATH);
  db.exec(`
    CREATE TABLE IF NOT EXISTS job_details (
      url TEXT PRIMARY KEY,
      company TEXT,
      title TEXT,
      location TEXT,
      posted_at TEXT,
      description TEXT,
      passed_filters INTEGER,
      fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS ai_evaluations (
      url TEXT PRIMARY KEY,
      match_score INTEGER,
      recommendation TEXT,
      career_level_fit TEXT,
      tech_stack_fit TEXT,
      experience_fit TEXT,
      location_fit TEXT,
      work_authorization_risk TEXT,
      language_risk TEXT,
      genuine_gaps TEXT,
      transferable_strengths TEXT,
      risk_factors TEXT,
      model TEXT,
      evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS local_evaluations (
      url TEXT PRIMARY KEY,
      match_score INTEGER,
      recommendation TEXT,
      career_level_fit TEXT,
      tech_stack_fit TEXT,
      experience_fit TEXT,
      location_fit TEXT,
      work_authorization_risk TEXT,
      language_risk TEXT,
      genuine_gaps TEXT,
      transferable_strengths TEXT,
      risk_factors TEXT,
      matched_keywords TEXT,
      score_breakdown TEXT,
      rule_version TEXT,
      evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS user_status (
      url TEXT PRIMARY KEY,
      my_status TEXT,
      notes TEXT,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
  `);
  return db;
}

export function getJobs(): JobRow[] {
  const rows = getDb()
    .prepare(
      `
      SELECT jd.url, jd.company, jd.title, jd.location, jd.posted_at,
             jd.description, jd.passed_filters,
             COALESCE(ae.match_score, le.match_score) AS match_score,
             COALESCE(ae.recommendation, le.recommendation) AS recommendation,
             COALESCE(ae.career_level_fit, le.career_level_fit) AS career_level_fit,
             COALESCE(ae.tech_stack_fit, le.tech_stack_fit) AS tech_stack_fit,
             COALESCE(ae.experience_fit, le.experience_fit) AS experience_fit,
             COALESCE(ae.location_fit, le.location_fit) AS location_fit,
             COALESCE(ae.work_authorization_risk, le.work_authorization_risk) AS work_authorization_risk,
             COALESCE(ae.language_risk, le.language_risk) AS language_risk,
             COALESCE(ae.genuine_gaps, le.genuine_gaps) AS genuine_gaps,
             COALESCE(ae.transferable_strengths, le.transferable_strengths) AS transferable_strengths,
             COALESCE(ae.risk_factors, le.risk_factors) AS risk_factors,
             le.matched_keywords,
             le.score_breakdown,
             CASE
               WHEN ae.url IS NOT NULL THEN 'openai'
               WHEN le.url IS NOT NULL THEN 'local'
               ELSE NULL
             END AS evaluation_source,
             us.my_status, us.notes
      FROM job_details jd
      LEFT JOIN ai_evaluations ae ON jd.url = ae.url
      LEFT JOIN local_evaluations le ON jd.url = le.url
      LEFT JOIN user_status us ON jd.url = us.url
      WHERE jd.passed_filters = 1
      ORDER BY COALESCE(ae.match_score, le.match_score) DESC, jd.fetched_at DESC
      `
    )
    .all() as Omit<JobRow, "status">[];

  return rows.map((r) => ({
    ...r,
    status: r.recommendation ?? "not_evaluated",
  }));
}

export function jobExists(url: string): boolean {
  return getDb().prepare("SELECT 1 FROM job_details WHERE url = ?").get(url) !== undefined;
}

export function saveUserStatus(url: string, myStatus: string | null, notes: string | null): void {
  getDb()
    .prepare(
      `
      INSERT INTO user_status (url, my_status, notes, updated_at)
      VALUES (?, ?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(url) DO UPDATE SET
        my_status = excluded.my_status,
        notes = excluded.notes,
        updated_at = CURRENT_TIMESTAMP
      `
    )
    .run(url, myStatus || null, notes || null);
}
