"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, ApiRequestError } from "@/lib/api";
import type { Resume, ResumeRead, JobDescription } from "@/types";

function NewResumeModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [jobId, setJobId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: jobs, isLoading: jobsLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<JobDescription[]>("/api/v1/jobs"),
  });

  const handleCreate = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      const resume = await api.post<ResumeRead>("/api/v1/resumes", {
        job_id: jobId || null,
      });
      router.push(`/resumes/${resume.id}`);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.detail);
      } else {
        setError("Failed to create resume.");
      }
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold">New Resume</h2>

        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
        )}

        <div className="space-y-1">
          <label htmlFor="job-select" className="text-sm font-medium">
            Link to Job (optional)
          </label>
          {jobsLoading ? (
            <p className="text-sm text-muted-foreground">Loading jobs...</p>
          ) : (
            <select
              id="job-select"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">— No job selected —</option>
              {jobs?.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title}{job.company ? ` — ${job.company}` : ""}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={handleCreate}
            disabled={isSubmitting}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {isSubmitting ? "Creating..." : "Create Resume"}
          </button>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-md border border-border px-5 py-2 text-sm font-medium hover:bg-muted/50 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ResumesPage() {
  const [showModal, setShowModal] = useState(false);

  const { data: resumes, isLoading } = useQuery({
    queryKey: ["resumes"],
    queryFn: () => api.get<Resume[]>("/api/v1/resumes"),
  });

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-6">
      {showModal && <NewResumeModal onClose={() => setShowModal(false)} />}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Resumes</h1>
          <p className="text-muted-foreground">
            AI-generated, evidence-backed resume versions.
          </p>
        </div>
        <button
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          onClick={() => setShowModal(true)}
        >
          New Resume
        </button>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading...</p>}

      {resumes && resumes.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center">
          <p className="text-muted-foreground text-sm">
            No resumes yet. Add a job description and generate bullets to create your first resume.
          </p>
        </div>
      )}

      {resumes && resumes.length > 0 && (
        <ul className="space-y-3">
          {resumes.map((resume) => (
            <li key={resume.id}>
              <a
                href={`/resumes/${resume.id}`}
                className="block rounded-lg border border-border p-4 hover:bg-muted/50 transition-colors"
              >
                <p className="font-medium">Resume {resume.id.slice(0, 8)}</p>
                {resume.job_id && (
                  <p className="text-sm text-muted-foreground">
                    For job: {resume.job_id.slice(0, 8)}
                  </p>
                )}
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
