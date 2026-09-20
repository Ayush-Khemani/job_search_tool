export type SortKey = "company" | "title" | "location" | "match_score" | "status" | "evaluation_source" | "my_status" | "posted_at";
export type SortDir = "asc" | "desc";
export type SaveState = "idle" | "saving" | "saved" | "error";

export type Job = {
    url: string;
    company: string;
    title: string;
    location: string;
    posted_at: string | null;
    description: string;
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
    my_status: string | null;
    notes: string | null;
    status: string;
};
