"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { JobListRead } from "@/types";

export default function JobsPage() {
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<JobListRead[]>("/api/v1/jobs"),
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
        <Link
          href="/jobs/new"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Add Job
        </Link>
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
            <li key={job.id}>
              <Link
                href={`/jobs/${job.id}`}
                className="flex items-start justify-between gap-4 rounded-lg border border-border p-4 hover:bg-muted/50 transition-colors"
              >
                <div className="min-w-0">
                  <p className="font-medium truncate">{job.title}</p>
                  {job.company && (
                    <p className="text-sm text-muted-foreground">{job.company}</p>
                  )}
                  {job.parsed_at && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Parsed {new Date(job.parsed_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
                {job.latest_analysis && (
                  <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                    {Math.round(job.latest_analysis.fit_score)}%
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
