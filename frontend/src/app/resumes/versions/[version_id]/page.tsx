"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ResumeVersionDetailRead } from "@/types";

export default function VersionDetailPage() {
  const params = useParams();
  const versionId = params.version_id as string;

  const { data: version, isLoading, error } = useQuery({
    queryKey: ["version", versionId],
    queryFn: () => api.get<ResumeVersionDetailRead>(`/api/v1/resumes/versions/${versionId}`),
    enabled: !!versionId,
    retry: false,
  });

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 space-y-8">
      <div>
        <a href="/resumes" className="text-sm text-muted-foreground hover:underline">
          ← Back to Resumes
        </a>
        <h1 className="mt-2 text-2xl font-bold">Version Detail</h1>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading version...</p>}

      {error && (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          Failed to load version.
        </div>
      )}

      {version && (
        <>
          <section className="rounded-lg border border-border p-5 space-y-2">
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <span className="text-muted-foreground">Job Title</span>
              <span>{version.job_title ?? "—"}</span>
              <span className="text-muted-foreground">Company</span>
              <span>{version.job_company ?? "—"}</span>
              <span className="text-muted-foreground">Fit Score</span>
              <span>
                {version.fit_score_at_gen != null
                  ? `${(version.fit_score_at_gen * 100).toFixed(0)}%`
                  : "—"}
              </span>
              <span className="text-muted-foreground">Created</span>
              <span>{new Date(version.created_at).toLocaleString()}</span>
            </div>
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold border-b border-border pb-2">
              Bullets ({version.bullets.length})
            </h2>
            {version.bullets.length === 0 && (
              <p className="text-sm text-muted-foreground">No bullets in this version.</p>
            )}
            <ul className="space-y-4">
              {version.bullets.map((bullet) => (
                <li key={bullet.id} className="rounded-lg border border-border p-4 space-y-2">
                  <p className="text-sm">{bullet.text}</p>
                  {bullet.confidence != null && (
                    <p className="text-xs text-muted-foreground">
                      Confidence: {(bullet.confidence * 100).toFixed(0)}%
                    </p>
                  )}
                  {bullet.evidence.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-medium text-muted-foreground">Evidence</p>
                      <ul className="space-y-0.5">
                        {bullet.evidence.map((ev, i) => (
                          <li key={i} className="text-xs text-muted-foreground">
                            <span className="font-medium">{ev.source_entity_type}</span>:{" "}
                            {ev.display_name}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
