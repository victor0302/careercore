"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function DashboardPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading, user } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/auth/login");
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </main>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Welcome to CareerCore</h1>
        <p className="mt-1 text-muted-foreground">
          Signed in as <span className="font-medium">{user?.email}</span>
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <a
          href="/profile"
          className="rounded-lg border border-border p-6 hover:bg-muted/50 transition-colors"
        >
          <h2 className="font-semibold">My Profile</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Build your career evidence graph
          </p>
        </a>
        <a
          href="/jobs"
          className="rounded-lg border border-border p-6 hover:bg-muted/50 transition-colors"
        >
          <h2 className="font-semibold">Job Descriptions</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Paste JDs and get AI fit analysis
          </p>
        </a>
        <a
          href="/resumes"
          className="rounded-lg border border-border p-6 hover:bg-muted/50 transition-colors"
        >
          <h2 className="font-semibold">Resumes</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Generate evidence-backed resume bullets
          </p>
        </a>
      </div>
    </main>
  );
}
