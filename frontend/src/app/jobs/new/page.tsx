"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiRequestError } from "@/lib/api";
import type { JobDescription } from "@/types";

export default function NewJobPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [rawText, setRawText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      await api.post<JobDescription>("/api/v1/jobs", {
        title,
        company: company || null,
        raw_text: rawText,
      });
      router.push("/jobs");
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.detail);
      } else {
        setError("Failed to submit job description.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Add Job Description</h1>
        <p className="text-muted-foreground">Paste a full job posting to analyze your fit.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
        )}

        <div className="space-y-1">
          <label htmlFor="title" className="text-sm font-medium">
            Job Title *
          </label>
          <input
            id="title"
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="e.g. Senior Software Engineer"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="company" className="text-sm font-medium">
            Company
          </label>
          <input
            id="company"
            type="text"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="e.g. Acme Corp"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="rawText" className="text-sm font-medium">
            Job Description (full text) *
          </label>
          <textarea
            id="rawText"
            required
            rows={16}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring font-mono"
            placeholder="Paste the full job description here..."
          />
        </div>

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={isLoading}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {isLoading ? "Submitting..." : "Submit"}
          </button>
          <a
            href="/jobs"
            className="rounded-md border border-border px-5 py-2 text-sm font-medium hover:bg-muted/50"
          >
            Cancel
          </a>
        </div>
      </form>
    </main>
  );
}
