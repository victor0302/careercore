"use client";

export default function ProfilePage() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">My Profile</h1>
        <p className="text-muted-foreground">
          Build and manage your master career data graph.
        </p>
      </div>

      {/* TODO Phase 1: Implement ProfileForm component */}
      <div className="rounded-lg border border-dashed border-border p-10 text-center">
        <p className="text-muted-foreground text-sm">
          Profile form coming in Sprint 2 — work experience, skills, projects, certifications.
        </p>
      </div>
    </main>
  );
}
