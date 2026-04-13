"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Resume } from "@/types";

export default function ResumesPage() {
  const { data: resumes, isLoading } = useQuery({
    queryKey: ["resumes"],
    queryFn: () => api.get<Resume[]>("/api/v1/resumes"),
  });

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Resumes</h1>
          <p className="text-muted-foreground">
            AI-generated, evidence-backed resume versions.
          </p>
        </div>
        <button
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          onClick={() => alert("TODO: Create resume flow — Phase 1 Sprint 3")}
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
            <li
              key={resume.id}
              className="rounded-lg border border-border p-4 hover:bg-muted/50 transition-colors"
            >
              <p className="font-medium">Resume {resume.id.slice(0, 8)}</p>
              {resume.job_id && (
                <p className="text-sm text-muted-foreground">
                  For job: {resume.job_id.slice(0, 8)}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
