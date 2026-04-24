"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiRequestError } from "@/lib/api";
import type {
  ResumeBulletRead,
  BulletsGenerateRequest,
  ResumeVersionListItem,
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
  const [entityId, setEntityId] = useState("");
  const [requirementsRaw, setRequirementsRaw] = useState("");
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

  const resumeVersions = allVersions?.filter((v) => v.resume_id === resumeId) ?? [];

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setGenerateError(null);
    setIsGenerating(true);
    const requirementIds = requirementsRaw
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const body: BulletsGenerateRequest = {
      profile_entity_type: entityType,
      profile_entity_id: entityId.trim(),
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

          <div className="space-y-1">
            <label className="text-sm font-medium">Profile Entity Type</label>
            <select
              value={entityType}
              onChange={(e) => setEntityType(e.target.value as "work_experience" | "project")}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="work_experience">Work Experience</option>
              <option value="project">Project</option>
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium">Profile Entity ID (UUID)</label>
            <input
              type="text"
              required
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring font-mono"
              placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6"
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium">
              Requirement IDs (one per line or comma-separated)
            </label>
            <textarea
              required
              rows={4}
              value={requirementsRaw}
              onChange={(e) => setRequirementsRaw(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring font-mono"
              placeholder={"req-uuid-1\nreq-uuid-2"}
            />
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
