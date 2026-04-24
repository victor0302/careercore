"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiRequestError } from "@/lib/api";
import type { JobDetailRead } from "@/types";

export default function JobDetailPage({
  params,
}: {
  params: Promise<{ job_id: string }>;
}) {
  const { job_id } = use(params);
  const queryClient = useQueryClient();
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const {
    data: job,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["jobs", job_id],
    queryFn: () => api.get<JobDetailRead>(`/api/v1/jobs/${job_id}`),
  });

  const handleRunAnalysis = async () => {
    setParseError(null);
    setParsing(true);
    try {
      await api.post(`/api/v1/jobs/${job_id}/parse`);
      await queryClient.invalidateQueries({ queryKey: ["jobs", job_id] });
    } catch (err) {
      setParseError(
        err instanceof ApiRequestError ? err.detail : "Failed to start analysis.",
      );
    } finally {
      setParsing(false);
    }
  };

  if (isLoading) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-10">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </main>
    );
  }

  if (error || !job) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-10 space-y-4">
        <Link href="/jobs" className="text-sm text-muted-foreground hover:text-foreground">
          ← Back to Jobs
        </Link>
        <div className="rounded-md bg-destructive/10 p-4 text-sm text-destructive">
          {error instanceof ApiRequestError
            ? error.detail
            : "Failed to load job details."}
        </div>
      </main>
    );
  }

  const analysis = job.latest_analysis;

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-6">
      <Link href="/jobs" className="text-sm text-muted-foreground hover:text-foreground">
        ← Back to Jobs
      </Link>

      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <h1 className="text-2xl font-bold">{job.title}</h1>
          {analysis && (
            <span className="rounded-full bg-primary/10 px-3 py-1 text-sm font-semibold text-primary">
              {Math.round(analysis.fit_score)}% fit
            </span>
          )}
        </div>
        {job.company && (
          <p className="text-muted-foreground">{job.company}</p>
        )}
        {job.parsed_at && (
          <p className="text-xs text-muted-foreground">
            Parsed {new Date(job.parsed_at).toLocaleDateString()}
          </p>
        )}
      </div>

      {/* Not yet analyzed */}
      {!job.parsed_at && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center space-y-3">
          <p className="font-medium">Not yet analyzed</p>
          <p className="text-sm text-muted-foreground">
            Run analysis to get your fit score and requirement breakdown.
          </p>
          {parseError && (
            <p className="text-sm text-destructive">{parseError}</p>
          )}
          <button
            onClick={handleRunAnalysis}
            disabled={parsing}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {parsing ? "Running..." : "Run analysis"}
          </button>
        </div>
      )}

      {/* Analysis */}
      {analysis && (
        <div className="space-y-5">
          <p className="text-xs text-muted-foreground">
            Analyzed {new Date(analysis.analyzed_at).toLocaleString()}
          </p>

          {/* Matched requirements */}
          <section className="rounded-lg border border-border p-5 space-y-3">
            <h2 className="font-semibold text-green-700 dark:text-green-400">
              Matched Requirements ({analysis.matched_requirements.length})
            </h2>
            {analysis.matched_requirements.length === 0 ? (
              <p className="text-sm text-muted-foreground">No matched requirements.</p>
            ) : (
              <ul className="space-y-2">
                {analysis.matched_requirements.map((req) => (
                  <li
                    key={req.id}
                    className="flex items-center justify-between gap-3 rounded-md bg-green-50 dark:bg-green-900/20 px-3 py-2 text-sm"
                  >
                    <span className="font-medium capitalize">{req.match_type.replace(/_/g, " ")}</span>
                    <span className="text-xs text-muted-foreground">
                      {Math.round(req.confidence * 100)}% confidence
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Missing requirements */}
          <section className="rounded-lg border border-border p-5 space-y-3">
            <h2 className="font-semibold text-amber-700 dark:text-amber-400">
              Missing Requirements ({analysis.missing_requirements.length})
            </h2>
            {analysis.missing_requirements.length === 0 ? (
              <p className="text-sm text-muted-foreground">No missing requirements.</p>
            ) : (
              <ul className="space-y-2">
                {analysis.missing_requirements.map((req) => (
                  <li
                    key={req.id}
                    className="rounded-md bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm"
                  >
                    {req.suggested_action ? (
                      <span>{req.suggested_action}</span>
                    ) : (
                      <span className="text-muted-foreground">No suggested action</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Score breakdown & evidence map */}
          {(Object.keys(analysis.score_breakdown).length > 0 ||
            Object.keys(analysis.evidence_map).length > 0) && (
            <details className="rounded-lg border border-border">
              <summary className="cursor-pointer px-5 py-3 font-medium text-sm select-none">
                Raw analysis data
              </summary>
              <div className="border-t border-border px-5 py-4 space-y-4">
                {Object.keys(analysis.score_breakdown).length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Score breakdown
                    </p>
                    <pre className="overflow-x-auto rounded-md bg-muted px-4 py-3 text-xs">
                      {JSON.stringify(analysis.score_breakdown, null, 2)}
                    </pre>
                  </div>
                )}
                {Object.keys(analysis.evidence_map).length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Evidence map
                    </p>
                    <pre className="overflow-x-auto rounded-md bg-muted px-4 py-3 text-xs">
                      {JSON.stringify(analysis.evidence_map, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </details>
          )}
        </div>
      )}

      {/* Parsed but no analysis yet */}
      {job.parsed_at && !analysis && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center space-y-3">
          <p className="font-medium">No analysis yet</p>
          <p className="text-sm text-muted-foreground">
            Analysis is being computed or has not been run yet.
          </p>
          {parseError && (
            <p className="text-sm text-destructive">{parseError}</p>
          )}
          <button
            onClick={handleRunAnalysis}
            disabled={parsing}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {parsing ? "Running..." : "Run analysis"}
          </button>
        </div>
      )}
    </main>
  );
}
