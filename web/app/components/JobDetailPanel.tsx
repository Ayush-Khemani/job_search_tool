import DOMPurify from "dompurify";
import {MY_STATUS_LABEL, MY_STATUS_VALUES} from "@/app/constants";
import {Job, SaveState} from "@/app/types";
import StatusBadge from "@/app/components/StatusBadge";
import {formatDescription} from "@/lib/formatDescription";

type JobDetailPanelProps = {
  job: Job;
  draftStatus: string;
  onDraftStatusChange: (value: string) => void;
  draftNotes: string;
  onDraftNotesChange: (value: string) => void;
  saveState: SaveState;
  onSave: () => void;
  onClose: () => void;
};

function scoreBreakdown(job: Job): Array<[string, {score?: number; max?: number; reason?: string} | number]> {
  if (!job.score_breakdown || job.evaluation_source !== "local") return [];
  try {
    const parsed = JSON.parse(job.score_breakdown) as Record<string, {score?: number; max?: number; reason?: string} | number>;
    return Object.entries(parsed);
  } catch {
    return [];
  }
}

export default function JobDetailPanel({
  job, draftStatus, onDraftStatusChange, draftNotes, onDraftNotesChange, saveState, onSave, onClose,
}: JobDetailPanelProps) {
  const breakdown = scoreBreakdown(job);
  return (
    <div id="overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div id="panel">
        <div id="panel-header">
          <button id="panel-close" onClick={onClose} aria-label="Close">&times;</button>
          <h2>{job.title}</h2>
          <div className="panel-meta">
            {job.company} · {job.location} · <StatusBadge status={job.status} />
            {job.match_score != null && ` · score ${job.match_score}`}
            {job.evaluation_source && ` · ${job.evaluation_source === "local" ? "local rules" : "OpenAI"}`}
          </div>
        </div>
        <div id="panel-body">
          <h3>My status</h3>
          <div className="panel-status-row">
            <select value={draftStatus} onChange={(e) => onDraftStatusChange(e.target.value)}>
              <option value="">— not set —</option>
              {MY_STATUS_VALUES.map((v) => (
                <option key={v} value={v}>{MY_STATUS_LABEL[v]}</option>
              ))}
            </select>
          </div>

          <h3>Notes</h3>
          <textarea
            value={draftNotes}
            onChange={(e) => onDraftNotesChange(e.target.value)}
            placeholder="e.g.: applied via referral, follow up by Friday"
          />

          <div className="panel-actions">
            <button className="btn" onClick={onSave}>Save</button>
            {saveState === "saving" && <span className="save-status">Saving...</span>}
            {saveState === "saved" && <span className="save-status">✓ Saved</span>}
            {saveState === "error" && <span className="save-status">Error</span>}
            <a className="btn secondary" href={job.url} target="_blank" rel="noopener noreferrer">
              Open job ↗
            </a>
          </div>

          {job.match_score != null && (
            <>
              <h3>Fit dimensions</h3>
              <div>
                Career: {job.career_level_fit || "—"} · Stack: {job.tech_stack_fit || "—"} ·
                Experience: {job.experience_fit || "—"} · Location: {job.location_fit || "—"}
              </div>
              <div>
                Work authorization risk: {job.work_authorization_risk || "—"} ·
                Language risk: {job.language_risk || "—"}
              </div>

              {breakdown.length > 0 && (
                <>
                  <h3>Local score breakdown</h3>
                  <div>
                    {breakdown.map(([name, value]) => {
                      if (typeof value === "number") {
                        return <div key={name}>{name}: -{value}</div>;
                      }
                      return (
                        <div key={name}>
                          {name.replace(/_/g, " ")}: {value.score}/{value.max}
                          {value.reason ? ` — ${value.reason}` : ""}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}

              {job.matched_keywords && (
                <>
                  <h3>Matched stack</h3>
                  <div>{job.matched_keywords}</div>
                </>
              )}
              <h3>Transferable strengths</h3>
              <div>{job.transferable_strengths || "—"}</div>
              <h3>Genuine gaps</h3>
              <div>{job.genuine_gaps || "—"}</div>
              <h3>Risk factors</h3>
              <div>{job.risk_factors || "—"}</div>
            </>
          )}

          <h3>Job description</h3>
          {job.description ? (
            (() => {
              const formatted = formatDescription(job.description);
              return formatted.kind === "html"
                ? <div className="desc" dangerouslySetInnerHTML={{__html: DOMPurify.sanitize(formatted.html)}} />
                : <div className="desc desc-plain">{formatted.text}</div>;
            })()
          ) : (
            <div className="desc"><em>No description.</em></div>
          )}
        </div>
      </div>
    </div>
  );
}
