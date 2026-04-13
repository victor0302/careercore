"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { JobDescription } from "@/types";

export default function JobsPage() {
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<JobDescription[]>("/api/v1/jobs"),
  });

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Job Descriptions</h1>
          <p className="text-muted-foreground">
            Paste job postings to get AI-powered fit analysis.
          </p>
        </div>
        <a
          href="/jobs/new"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Add Job
        </a>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading...</p>}

      {jobs && jobs.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center">
          <p className="text-muted-foreground text-sm">
            No job descriptions yet. Click &quot;Add Job&quot; to get started.
          </p>
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <ul className="space-y-3">
          {jobs.map((job) => (
            <li
              key={job.id}
              className="rounded-lg border border-border p-4 hover:bg-muted/50 transition-colors"
            >
              <p className="font-medium">{job.title}</p>
              {job.company && (
                <p className="text-sm text-muted-foreground">{job.company}</p>
              )}
              {job.parsed_at && (
                <p className="text-xs text-muted-foreground mt-1">
                  Parsed {new Date(job.parsed_at).toLocaleDateString()}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
