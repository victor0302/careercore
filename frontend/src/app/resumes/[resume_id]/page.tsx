"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiRequestError } from "@/lib/api";
import type {
  ResumeBulletRead,
  BulletsGenerateRequest,
  ResumeVersionListItem,
  ResumeRead,
  WorkExperience,
  Project,
  JobDetailRead,
} from "@/types";

function BulletRow({
  bullet,
  resumeId,
  onApproved,
  onDeleted,
}: {
  bullet: ResumeBulletRead;
  resumeId: string;
  onApproved: (updated: ResumeBulletRead) => void;
  onDeleted: (id: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.patch<ResumeBulletRead>(
        `/api/v1/resumes/${resumeId}/bullets/${bullet.id}/approve`
      );
      onApproved(updated);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.detail : "Request failed.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.delete(`/api/v1/resumes/${resumeId}/bullets/${bullet.id}`);
      onDeleted(bullet.id);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.detail : "Request failed.");
      setBusy(false);
    }
  };

  return (
    <li className="rounded-lg border border-border p-4 space-y-2">
      <p className="text-sm">{bullet.text}</p>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {bullet.confidence != null && (
          <span>Confidence: {(bullet.confidence * 100).toFixed(0)}%</span>
        )}
        <span
          className={`rounded-full px-2 py-0.5 font-medium ${
            bullet.is_approved
              ? "bg-green-100 text-green-700"
              : "bg-yellow-100 text-yellow-700"
          }`}
        >
          {bullet.is_approved ? "Approved" : "Pending"}
        </span>
        {bullet.is_ai_generated && (
          <span className="rounded-full bg-blue-100 px-2 py-0.5 font-medium text-blue-700">AI</span>
        )}
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        {!bullet.is_approved && (
          <button
            onClick={approve}
            disabled={busy}
            className="rounded-md border border-border px-3 py-1 text-xs font-medium hover:bg-muted/50 disabled:opacity-50"
          >
            Approve
          </button>
        )}
        <button
          onClick={remove}
          disabled={busy}
          className="rounded-md border border-destructive/50 px-3 py-1 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

export default function ResumeWorkflowPage() {
  const params = useParams();
  const resumeId = params.resume_id as string;
  const queryClient = useQueryClient();

  const [bullets, setBullets] = useState<ResumeBulletRead[]>([]);
  const [entityType, setEntityType] = useState<"work_experience" | "project">("work_experience");
  const [selectedEntityId, setSelectedEntityId] = useState("");
  const [selectedRequirementIds, setSelectedRequirementIds] = useState<string[]>([]);
  const [rawIds, setRawIds] = useState("");
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const [snapshotMessage, setSnapshotMessage] = useState<string | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [isSnapshotting, setIsSnapshotting] = useState(false);

  const versionsKey = ["versions"];
  const { data: allVersions, isLoading: versionsLoading } = useQuery({
    queryKey: versionsKey,
    queryFn: () => api.get<ResumeVersionListItem[]>("/api/v1/resumes/versions"),
  });

  const { data: resume } = useQuery({
    queryKey: ["resumes", resumeId],
    queryFn: () => api.get<ResumeRead>(`/api/v1/resumes/${resumeId}`),
  });

  const jobId = resume?.job_id ?? null;

  const { data: experiences } = useQuery({
    queryKey: ["profile", "experience"],
    queryFn: () => api.get<WorkExperience[]>("/api/v1/profile/experience"),
  });

  const { data: projects } = useQuery({
    queryKey: ["profile", "projects"],
    queryFn: () => api.get<Project[]>("/api/v1/profile/projects"),
  });

  const { data: jobDetail } = useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => api.get<JobDetailRead>(`/api/v1/jobs/${jobId}`),
    enabled: !!jobId,
  });

  const resumeVersions = allVersions?.filter((v) => v.resume_id === resumeId) ?? [];

  const toggleRequirement = (reqId: string) => {
    setSelectedRequirementIds((prev) =>
      prev.includes(reqId) ? prev.filter((id) => id !== reqId) : [...prev, reqId]
    );
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setGenerateError(null);

    const requirementIds = jobId
      ? selectedRequirementIds
      : rawIds.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);

    if (!selectedEntityId.trim()) {
      setGenerateError("Please select a profile entity.");
      return;
    }
    if (requirementIds.length === 0) {
      setGenerateError("Please select at least one requirement.");
      return;
    }

    setIsGenerating(true);
    const body: BulletsGenerateRequest = {
      profile_entity_type: entityType,
      profile_entity_id: selectedEntityId.trim(),
      requirement_ids: requirementIds,
    };
    try {
      const newBullets = await api.post<ResumeBulletRead[]>(
        `/api/v1/resumes/${resumeId}/bullets/generate`,
        body
      );
      setBullets((prev) => {
        const ids = new Set(prev.map((b) => b.id));
        return [...prev, ...newBullets.filter((b) => !ids.has(b.id))];
      });
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.status === 429) {
          setGenerateError("Rate limit reached. Please wait before generating more bullets.");
        } else if (err.status === 402) {
          setGenerateError("Daily AI budget exceeded. Try again tomorrow.");
        } else {
          setGenerateError(err.detail);
        }
      } else {
        setGenerateError("Failed to generate bullets.");
      }
    } finally {
      setIsGenerating(false);
    }
  };

  const handleApproved = (updated: ResumeBulletRead) => {
    setBullets((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
  };

  const handleDeleted = (id: string) => {
    setBullets((prev) => prev.filter((b) => b.id !== id));
  };

  const handleSnapshot = async () => {
    setSnapshotMessage(null);
    setSnapshotError(null);
    setIsSnapshotting(true);
    try {
      await api.post(`/api/v1/resumes/${resumeId}/versions`, {});
      setSnapshotMessage("Version snapshot created successfully.");
      queryClient.invalidateQueries({ queryKey: versionsKey });
    } catch (err) {
      setSnapshotError(
        err instanceof ApiRequestError ? err.detail : "Failed to create snapshot."
      );
    } finally {
      setIsSnapshotting(false);
    }
  };

  const SELECT_CLS =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 space-y-10">
      <div>
        <a href="/resumes" className="text-sm text-muted-foreground hover:underline">
          ← Back to Resumes
        </a>
        <h1 className="mt-2 text-2xl font-bold">Resume Workflow</h1>
        <p className="text-sm text-muted-foreground font-mono">{resumeId}</p>
      </div>

      {/* Generate Bullets */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b border-border pb-2">Generate Bullets</h2>
        <form onSubmit={handleGenerate} className="space-y-4">
          {generateError && (
            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {generateError}
            </div>
          )}

          {/* Entity type */}
          <div className="space-y-1">
            <label className="text-sm font-medium">Profile Entity Type</label>
            <select
              value={entityType}
              onChange={(e) => {
                setEntityType(e.target.value as "work_experience" | "project");
                setSelectedEntityId("");
              }}
              className={SELECT_CLS}
            >
              <option value="work_experience">Work Experience</option>
              <option value="project">Project</option>
            </select>
          </div>

          {/* Entity dropdown */}
          <div className="space-y-1">
            <label className="text-sm font-medium">Profile Entity</label>
            {entityType === "work_experience" ? (
              experiences ? (
                <select
                  value={selectedEntityId}
                  onChange={(e) => setSelectedEntityId(e.target.value)}
                  className={SELECT_CLS}
                >
                  <option value="">— select work experience —</option>
                  {experiences.map((exp) => (
                    <option key={exp.id} value={exp.id}>
                      {exp.role_title} at {exp.employer}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-sm text-muted-foreground">Loading...</p>
              )
            ) : projects ? (
              <select
                value={selectedEntityId}
                onChange={(e) => setSelectedEntityId(e.target.value)}
                className={SELECT_CLS}
              >
                <option value="">— select project —</option>
                {projects.map((proj) => (
                  <option key={proj.id} value={proj.id}>
                    {proj.name}
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-sm text-muted-foreground">Loading...</p>
            )}
          </div>

          {/* Requirements selector */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Requirements</label>

            {!jobId ? (
              /* No linked job — fallback to manual textarea */
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">
                  This resume has no linked job. Paste requirement IDs manually.
                </p>
                <textarea
                  rows={4}
                  value={rawIds}
                  onChange={(e) => setRawIds(e.target.value)}
                  className={`${SELECT_CLS} font-mono`}
                  placeholder={"req-uuid-1\nreq-uuid-2"}
                />
              </div>
            ) : !jobDetail?.latest_analysis ? (
              /* Job exists but not analyzed yet */
              <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                Job has not been analyzed yet — run analysis from the Jobs page first.
              </p>
            ) : (
              /* Analysis available — checkbox list */
              <ul className="space-y-2 rounded-md border border-border p-3 max-h-64 overflow-y-auto">
                {jobDetail.latest_analysis.matched_requirements.map((req) => (
                  <li key={req.id} className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      id={`req-${req.id}`}
                      value={req.requirement_id}
                      checked={selectedRequirementIds.includes(req.requirement_id)}
                      onChange={() => toggleRequirement(req.requirement_id)}
                      className="mt-0.5 shrink-0"
                    />
                    <label htmlFor={`req-${req.id}`} className="text-sm cursor-pointer">
                      <span className="capitalize">{req.match_type.replace(/_/g, " ")}</span>
                      {" — "}
                      <span className="text-muted-foreground">
                        {Math.round(req.confidence * 100)}% confidence
                      </span>
                    </label>
                  </li>
                ))}
                {jobDetail.latest_analysis.missing_requirements.map((req) => (
                  <li key={req.id} className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      id={`req-${req.id}`}
                      value={req.requirement_id}
                      checked={selectedRequirementIds.includes(req.requirement_id)}
                      onChange={() => toggleRequirement(req.requirement_id)}
                      className="mt-0.5 shrink-0"
                    />
                    <label htmlFor={`req-${req.id}`} className="text-sm cursor-pointer text-amber-700 dark:text-amber-400">
                      Missing — {req.suggested_action ?? "No suggestion"}
                    </label>
                  </li>
                ))}
                {jobDetail.latest_analysis.matched_requirements.length === 0 &&
                  jobDetail.latest_analysis.missing_requirements.length === 0 && (
                    <li className="text-sm text-muted-foreground">No requirements found in analysis.</li>
                  )}
              </ul>
            )}
          </div>

          <button
            type="submit"
            disabled={isGenerating}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {isGenerating ? "Generating..." : "Generate Bullets"}
          </button>
        </form>
      </section>

      {/* Current Bullets */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b border-border pb-2">
          Current Bullets {bullets.length > 0 && `(${bullets.length})`}
        </h2>
        {bullets.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No bullets yet. Use the form above to generate some.
          </p>
        ) : (
          <ul className="space-y-3">
            {bullets.map((bullet) => (
              <BulletRow
                key={bullet.id}
                bullet={bullet}
                resumeId={resumeId}
                onApproved={handleApproved}
                onDeleted={handleDeleted}
              />
            ))}
          </ul>
        )}
      </section>

      {/* Snapshot Version */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b border-border pb-2">Snapshot Version</h2>
        <p className="text-sm text-muted-foreground">
          Save the current set of approved bullets as a named version.
        </p>
        {snapshotMessage && (
          <div className="rounded-md bg-green-50 p-3 text-sm text-green-700">
            {snapshotMessage}
          </div>
        )}
        {snapshotError && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {snapshotError}
          </div>
        )}
        <button
          onClick={handleSnapshot}
          disabled={isSnapshotting}
          className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {isSnapshotting ? "Saving..." : "Create Snapshot"}
        </button>
      </section>

      {/* Version History */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold border-b border-border pb-2">Version History</h2>
        {versionsLoading && (
          <p className="text-sm text-muted-foreground">Loading versions...</p>
        )}
        {!versionsLoading && resumeVersions.length === 0 && (
          <p className="text-sm text-muted-foreground">No versions yet.</p>
        )}
        {resumeVersions.length > 0 && (
          <ul className="space-y-3">
            {resumeVersions.map((version) => (
              <li key={version.id}>
                <a
                  href={`/resumes/versions/${version.id}`}
                  className="block rounded-lg border border-border p-4 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-sm">
                        {version.job_title ?? "Untitled"}
                        {version.job_company ? ` — ${version.job_company}` : ""}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {new Date(version.created_at).toLocaleString()}
                      </p>
                    </div>
                    {version.fit_score_at_gen != null && (
                      <span className="text-sm font-semibold text-primary">
                        {(version.fit_score_at_gen * 100).toFixed(0)}% fit
                      </span>
                    )}
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
