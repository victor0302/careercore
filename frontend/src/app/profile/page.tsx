"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiRequestError } from "@/lib/api";
import type {
  MasterProfile,
  WorkExperience,
  Project,
  Skill,
  Certification,
} from "@/types";

// ── Style constants ───────────────────────────────────────────────────────────

const INPUT =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";
const BTN_PRIMARY =
  "rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50";
const BTN_OUTLINE =
  "rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted/50";
const BTN_GHOST = "rounded-md px-3 py-1 text-sm hover:bg-muted/50";
const BTN_DESTRUCT = "rounded-md px-3 py-1 text-sm text-destructive hover:bg-destructive/10";

// ── Shared micro-components ───────────────────────────────────────────────────

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{message}</div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border p-8 text-center">
      <p className="text-muted-foreground text-sm">{label}</p>
    </div>
  );
}

// ── Tab types ─────────────────────────────────────────────────────────────────

type Tab = "experience" | "projects" | "skills" | "certifications";
const TABS: { id: Tab; label: string }[] = [
  { id: "experience", label: "Work Experience" },
  { id: "projects", label: "Projects" },
  { id: "skills", label: "Skills" },
  { id: "certifications", label: "Certifications" },
];

// ── BasicInfo section ─────────────────────────────────────────────────────────

function BasicInfoSection() {
  const queryClient = useQueryClient();

  const { data: profile, isLoading } = useQuery({
    queryKey: ["profile"],
    queryFn: () => api.get<MasterProfile>("/api/v1/profile"),
  });

  const [displayName, setDisplayName] = useState("");
  const [currentTitle, setCurrentTitle] = useState("");
  const [targetDomain, setTargetDomain] = useState("");
  const [summaryNotes, setSummaryNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (profile) {
      setDisplayName(profile.display_name ?? "");
      setCurrentTitle(profile.current_title ?? "");
      setTargetDomain(profile.target_domain ?? "");
      setSummaryNotes(profile.summary_notes ?? "");
    }
  }, [profile]);

  const mutation = useMutation({
    mutationFn: (body: Record<string, string | null>) =>
      api.patch<MasterProfile>("/api/v1/profile", body),
    onSuccess: (data) => {
      queryClient.setQueryData(["profile"], data);
      setSaved(true);
      setError(null);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (err) => {
      setError(err instanceof ApiRequestError ? err.detail : "Failed to save profile.");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      display_name: displayName || null,
      current_title: currentTitle || null,
      target_domain: targetDomain || null,
      summary_notes: summaryNotes || null,
    });
  };

  if (isLoading) {
    return <p className="text-muted-foreground text-sm">Loading profile...</p>;
  }

  return (
    <section className="rounded-lg border border-border p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Basic Information</h2>
        {profile && (
          <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            {Math.round(profile.completeness_pct)}% complete
          </span>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorBanner message={error} />}
        {saved && (
          <div className="rounded-md bg-green-500/10 p-3 text-sm text-green-600">
            Profile saved.
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-sm font-medium">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className={INPUT}
              placeholder="Jane Doe"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Current Title</label>
            <input
              type="text"
              value={currentTitle}
              onChange={(e) => setCurrentTitle(e.target.value)}
              className={INPUT}
              placeholder="Software Engineer"
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <label className="text-sm font-medium">Target Domain</label>
            <input
              type="text"
              value={targetDomain}
              onChange={(e) => setTargetDomain(e.target.value)}
              className={INPUT}
              placeholder="Backend Engineering"
            />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium">Summary Notes</label>
          <textarea
            rows={4}
            value={summaryNotes}
            onChange={(e) => setSummaryNotes(e.target.value)}
            className={INPUT + " resize-none"}
            placeholder="Brief career summary or notes..."
          />
        </div>

        <div>
          <button type="submit" disabled={mutation.isPending} className={BTN_PRIMARY}>
            {mutation.isPending ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ── Work Experience section ───────────────────────────────────────────────────

type WEForm = {
  employer: string;
  role_title: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  description_raw: string;
};
const WE_EMPTY: WEForm = {
  employer: "",
  role_title: "",
  start_date: "",
  end_date: "",
  is_current: false,
  description_raw: "",
};

function WorkExperienceSection() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<WEForm>(WE_EMPTY);
  const [error, setError] = useState<string | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: ["profile", "experience"],
    queryFn: () => api.get<WorkExperience[]>("/api/v1/profile/experience"),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["profile", "experience"] });

  const toBody = (f: WEForm) => ({
    employer: f.employer,
    role_title: f.role_title,
    start_date: f.start_date,
    end_date: f.end_date || null,
    is_current: f.is_current,
    description_raw: f.description_raw || null,
  });

  const addMutation = useMutation({
    mutationFn: (f: WEForm) =>
      api.post<WorkExperience>("/api/v1/profile/experience", toBody(f)),
    onSuccess: () => {
      invalidate();
      setShowAdd(false);
      setForm(WE_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to add."),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, f }: { id: string; f: WEForm }) =>
      api.patch<WorkExperience>(`/api/v1/profile/experience/${id}`, toBody(f)),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
      setForm(WE_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to update."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/profile/experience/${id}`),
    onSuccess: () => invalidate(),
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to delete."),
  });

  const startEdit = (item: WorkExperience) => {
    setEditingId(item.id);
    setForm({
      employer: item.employer,
      role_title: item.role_title,
      start_date: item.start_date,
      end_date: item.end_date ?? "",
      is_current: item.is_current,
      description_raw: item.description_raw ?? "",
    });
    setShowAdd(false);
    setError(null);
  };

  const cancelForm = () => {
    setEditingId(null);
    setShowAdd(false);
    setForm(WE_EMPTY);
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingId) {
      editMutation.mutate({ id: editingId, f: form });
    } else {
      addMutation.mutate(form);
    }
  };

  const isPending = addMutation.isPending || editMutation.isPending;

  const renderForm = () => (
    <form onSubmit={handleSubmit} className="rounded-md border border-border p-4 space-y-3">
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="text-sm font-medium">Employer *</label>
          <input
            required
            type="text"
            value={form.employer}
            onChange={(e) => setForm({ ...form, employer: e.target.value })}
            className={INPUT}
            placeholder="Acme Corp"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Role Title *</label>
          <input
            required
            type="text"
            value={form.role_title}
            onChange={(e) => setForm({ ...form, role_title: e.target.value })}
            className={INPUT}
            placeholder="Software Engineer"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Start Date *</label>
          <input
            required
            type="date"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            className={INPUT}
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">End Date</label>
          <input
            type="date"
            value={form.end_date}
            disabled={form.is_current}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            className={INPUT + (form.is_current ? " opacity-50" : "")}
          />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          checked={form.is_current}
          onChange={(e) =>
            setForm({ ...form, is_current: e.target.checked, end_date: "" })
          }
        />
        Currently working here
      </label>
      <div className="space-y-1">
        <label className="text-sm font-medium">Description</label>
        <textarea
          rows={3}
          value={form.description_raw}
          onChange={(e) => setForm({ ...form, description_raw: e.target.value })}
          className={INPUT + " resize-none"}
          placeholder="Describe your responsibilities..."
        />
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={isPending} className={BTN_PRIMARY}>
          {isPending ? "Saving..." : editingId ? "Update" : "Add"}
        </button>
        <button type="button" onClick={cancelForm} className={BTN_OUTLINE}>
          Cancel
        </button>
      </div>
    </form>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Your work history</p>
        {!showAdd && !editingId && (
          <button
            onClick={() => {
              setShowAdd(true);
              setError(null);
            }}
            className={BTN_PRIMARY}
          >
            + Add Experience
          </button>
        )}
      </div>

      {showAdd && renderForm()}

      {isLoading && <p className="text-muted-foreground text-sm">Loading...</p>}
      {items && items.length === 0 && !showAdd && (
        <EmptyState label="No work experience added yet." />
      )}

      {items && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((item) =>
            editingId === item.id ? (
              <li key={item.id}>{renderForm()}</li>
            ) : (
              <li key={item.id} className="rounded-lg border border-border p-4 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{item.role_title}</p>
                    <p className="text-sm text-muted-foreground">{item.employer}</p>
                    <p className="text-xs text-muted-foreground">
                      {item.start_date} –{" "}
                      {item.is_current ? "Present" : (item.end_date ?? "—")}
                    </p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => startEdit(item)} className={BTN_GHOST}>
                      Edit
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(item.id)}
                      disabled={deleteMutation.isPending}
                      className={BTN_DESTRUCT}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {item.description_raw && (
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {item.description_raw}
                  </p>
                )}
              </li>
            )
          )}
        </ul>
      )}
    </div>
  );
}

// ── Projects section ──────────────────────────────────────────────────────────

type ProjForm = { name: string; description_raw: string; url: string };
const PROJ_EMPTY: ProjForm = { name: "", description_raw: "", url: "" };

function ProjectsSection() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ProjForm>(PROJ_EMPTY);
  const [error, setError] = useState<string | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: ["profile", "projects"],
    queryFn: () => api.get<Project[]>("/api/v1/profile/projects"),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["profile", "projects"] });

  const toBody = (f: ProjForm) => ({
    name: f.name,
    description_raw: f.description_raw || null,
    url: f.url || null,
  });

  const addMutation = useMutation({
    mutationFn: (f: ProjForm) =>
      api.post<Project>("/api/v1/profile/projects", toBody(f)),
    onSuccess: () => {
      invalidate();
      setShowAdd(false);
      setForm(PROJ_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to add."),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, f }: { id: string; f: ProjForm }) =>
      api.patch<Project>(`/api/v1/profile/projects/${id}`, toBody(f)),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
      setForm(PROJ_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to update."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/profile/projects/${id}`),
    onSuccess: () => invalidate(),
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to delete."),
  });

  const startEdit = (item: Project) => {
    setEditingId(item.id);
    setForm({
      name: item.name,
      description_raw: item.description_raw ?? "",
      url: item.url ?? "",
    });
    setShowAdd(false);
    setError(null);
  };

  const cancelForm = () => {
    setEditingId(null);
    setShowAdd(false);
    setForm(PROJ_EMPTY);
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingId) {
      editMutation.mutate({ id: editingId, f: form });
    } else {
      addMutation.mutate(form);
    }
  };

  const isPending = addMutation.isPending || editMutation.isPending;

  const renderForm = () => (
    <form onSubmit={handleSubmit} className="rounded-md border border-border p-4 space-y-3">
      {error && <ErrorBanner message={error} />}
      <div className="space-y-1">
        <label className="text-sm font-medium">Project Name *</label>
        <input
          required
          type="text"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className={INPUT}
          placeholder="My Awesome Project"
        />
      </div>
      <div className="space-y-1">
        <label className="text-sm font-medium">URL</label>
        <input
          type="url"
          value={form.url}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
          className={INPUT}
          placeholder="https://github.com/..."
        />
      </div>
      <div className="space-y-1">
        <label className="text-sm font-medium">Description</label>
        <textarea
          rows={3}
          value={form.description_raw}
          onChange={(e) => setForm({ ...form, description_raw: e.target.value })}
          className={INPUT + " resize-none"}
          placeholder="What did you build and why?"
        />
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={isPending} className={BTN_PRIMARY}>
          {isPending ? "Saving..." : editingId ? "Update" : "Add"}
        </button>
        <button type="button" onClick={cancelForm} className={BTN_OUTLINE}>
          Cancel
        </button>
      </div>
    </form>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Your projects and portfolio</p>
        {!showAdd && !editingId && (
          <button
            onClick={() => {
              setShowAdd(true);
              setError(null);
            }}
            className={BTN_PRIMARY}
          >
            + Add Project
          </button>
        )}
      </div>

      {showAdd && renderForm()}

      {isLoading && <p className="text-muted-foreground text-sm">Loading...</p>}
      {items && items.length === 0 && !showAdd && (
        <EmptyState label="No projects added yet." />
      )}

      {items && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((item) =>
            editingId === item.id ? (
              <li key={item.id}>{renderForm()}</li>
            ) : (
              <li key={item.id} className="rounded-lg border border-border p-4 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{item.name}</p>
                    {item.url && (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary hover:underline"
                      >
                        {item.url}
                      </a>
                    )}
                    {item.description_raw && (
                      <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                        {item.description_raw}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => startEdit(item)} className={BTN_GHOST}>
                      Edit
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(item.id)}
                      disabled={deleteMutation.isPending}
                      className={BTN_DESTRUCT}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </li>
            )
          )}
        </ul>
      )}
    </div>
  );
}

// ── Skills section ────────────────────────────────────────────────────────────

type SkillForm = {
  name: string;
  category: string;
  proficiency_level: string;
  years_of_experience: string;
};
const SKILL_EMPTY: SkillForm = {
  name: "",
  category: "",
  proficiency_level: "",
  years_of_experience: "",
};

function SkillsSection() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<SkillForm>(SKILL_EMPTY);
  const [error, setError] = useState<string | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: ["profile", "skills"],
    queryFn: () => api.get<Skill[]>("/api/v1/profile/skills"),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["profile", "skills"] });

  const toBody = (f: SkillForm) => ({
    name: f.name,
    category: f.category || null,
    proficiency_level: f.proficiency_level || null,
    years_of_experience: f.years_of_experience ? parseFloat(f.years_of_experience) : null,
  });

  const addMutation = useMutation({
    mutationFn: (f: SkillForm) =>
      api.post<Skill>("/api/v1/profile/skills", toBody(f)),
    onSuccess: () => {
      invalidate();
      setShowAdd(false);
      setForm(SKILL_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to add."),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, f }: { id: string; f: SkillForm }) =>
      api.patch<Skill>(`/api/v1/profile/skills/${id}`, toBody(f)),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
      setForm(SKILL_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to update."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/profile/skills/${id}`),
    onSuccess: () => invalidate(),
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to delete."),
  });

  const startEdit = (item: Skill) => {
    setEditingId(item.id);
    setForm({
      name: item.name,
      category: item.category ?? "",
      proficiency_level: item.proficiency_level ?? "",
      years_of_experience:
        item.years_of_experience != null ? String(item.years_of_experience) : "",
    });
    setShowAdd(false);
    setError(null);
  };

  const cancelForm = () => {
    setEditingId(null);
    setShowAdd(false);
    setForm(SKILL_EMPTY);
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingId) {
      editMutation.mutate({ id: editingId, f: form });
    } else {
      addMutation.mutate(form);
    }
  };

  const isPending = addMutation.isPending || editMutation.isPending;

  const renderForm = () => (
    <form onSubmit={handleSubmit} className="rounded-md border border-border p-4 space-y-3">
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="text-sm font-medium">Skill Name *</label>
          <input
            required
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className={INPUT}
            placeholder="TypeScript"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Category</label>
          <input
            type="text"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            className={INPUT}
            placeholder="Programming Language"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Proficiency Level</label>
          <input
            type="text"
            value={form.proficiency_level}
            onChange={(e) => setForm({ ...form, proficiency_level: e.target.value })}
            className={INPUT}
            placeholder="Advanced"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Years of Experience</label>
          <input
            type="number"
            min="0"
            step="0.5"
            value={form.years_of_experience}
            onChange={(e) => setForm({ ...form, years_of_experience: e.target.value })}
            className={INPUT}
            placeholder="3"
          />
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={isPending} className={BTN_PRIMARY}>
          {isPending ? "Saving..." : editingId ? "Update" : "Add"}
        </button>
        <button type="button" onClick={cancelForm} className={BTN_OUTLINE}>
          Cancel
        </button>
      </div>
    </form>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Your technical and soft skills</p>
        {!showAdd && !editingId && (
          <button
            onClick={() => {
              setShowAdd(true);
              setError(null);
            }}
            className={BTN_PRIMARY}
          >
            + Add Skill
          </button>
        )}
      </div>

      {showAdd && renderForm()}

      {isLoading && <p className="text-muted-foreground text-sm">Loading...</p>}
      {items && items.length === 0 && !showAdd && (
        <EmptyState label="No skills added yet." />
      )}

      {items && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((item) =>
            editingId === item.id ? (
              <li key={item.id}>{renderForm()}</li>
            ) : (
              <li key={item.id} className="rounded-lg border border-border px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="font-medium">{item.name}</span>
                    {item.category && (
                      <span className="text-xs text-muted-foreground">{item.category}</span>
                    )}
                    {item.proficiency_level && (
                      <span className="text-xs text-muted-foreground">
                        · {item.proficiency_level}
                      </span>
                    )}
                    {item.years_of_experience != null && (
                      <span className="text-xs text-muted-foreground">
                        · {item.years_of_experience}y
                      </span>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => startEdit(item)} className={BTN_GHOST}>
                      Edit
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(item.id)}
                      disabled={deleteMutation.isPending}
                      className={BTN_DESTRUCT}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </li>
            )
          )}
        </ul>
      )}
    </div>
  );
}

// ── Certifications section ────────────────────────────────────────────────────

type CertForm = {
  name: string;
  issuer: string;
  issued_date: string;
  expiry_date: string;
  credential_id: string;
  credential_url: string;
};
const CERT_EMPTY: CertForm = {
  name: "",
  issuer: "",
  issued_date: "",
  expiry_date: "",
  credential_id: "",
  credential_url: "",
};

function CertificationsSection() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<CertForm>(CERT_EMPTY);
  const [error, setError] = useState<string | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: ["profile", "certifications"],
    queryFn: () => api.get<Certification[]>("/api/v1/profile/certifications"),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["profile", "certifications"] });

  const toBody = (f: CertForm) => ({
    name: f.name,
    issuer: f.issuer || null,
    issued_date: f.issued_date || null,
    expiry_date: f.expiry_date || null,
    credential_id: f.credential_id || null,
    credential_url: f.credential_url || null,
  });

  const addMutation = useMutation({
    mutationFn: (f: CertForm) =>
      api.post<Certification>("/api/v1/profile/certifications", toBody(f)),
    onSuccess: () => {
      invalidate();
      setShowAdd(false);
      setForm(CERT_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to add."),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, f }: { id: string; f: CertForm }) =>
      api.patch<Certification>(`/api/v1/profile/certifications/${id}`, toBody(f)),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
      setForm(CERT_EMPTY);
      setError(null);
    },
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to update."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/profile/certifications/${id}`),
    onSuccess: () => invalidate(),
    onError: (err) =>
      setError(err instanceof ApiRequestError ? err.detail : "Failed to delete."),
  });

  const startEdit = (item: Certification) => {
    setEditingId(item.id);
    setForm({
      name: item.name,
      issuer: item.issuer ?? "",
      issued_date: item.issued_date ?? "",
      expiry_date: item.expiry_date ?? "",
      credential_id: item.credential_id ?? "",
      credential_url: item.credential_url ?? "",
    });
    setShowAdd(false);
    setError(null);
  };

  const cancelForm = () => {
    setEditingId(null);
    setShowAdd(false);
    setForm(CERT_EMPTY);
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingId) {
      editMutation.mutate({ id: editingId, f: form });
    } else {
      addMutation.mutate(form);
    }
  };

  const isPending = addMutation.isPending || editMutation.isPending;

  const renderForm = () => (
    <form onSubmit={handleSubmit} className="rounded-md border border-border p-4 space-y-3">
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1 sm:col-span-2">
          <label className="text-sm font-medium">Certification Name *</label>
          <input
            required
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className={INPUT}
            placeholder="AWS Solutions Architect"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Issuer</label>
          <input
            type="text"
            value={form.issuer}
            onChange={(e) => setForm({ ...form, issuer: e.target.value })}
            className={INPUT}
            placeholder="Amazon Web Services"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Credential ID</label>
          <input
            type="text"
            value={form.credential_id}
            onChange={(e) => setForm({ ...form, credential_id: e.target.value })}
            className={INPUT}
            placeholder="ABC-123456"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Issued Date</label>
          <input
            type="date"
            value={form.issued_date}
            onChange={(e) => setForm({ ...form, issued_date: e.target.value })}
            className={INPUT}
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Expiry Date</label>
          <input
            type="date"
            value={form.expiry_date}
            onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
            className={INPUT}
          />
        </div>
        <div className="space-y-1 sm:col-span-2">
          <label className="text-sm font-medium">Credential URL</label>
          <input
            type="url"
            value={form.credential_url}
            onChange={(e) => setForm({ ...form, credential_url: e.target.value })}
            className={INPUT}
            placeholder="https://..."
          />
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={isPending} className={BTN_PRIMARY}>
          {isPending ? "Saving..." : editingId ? "Update" : "Add"}
        </button>
        <button type="button" onClick={cancelForm} className={BTN_OUTLINE}>
          Cancel
        </button>
      </div>
    </form>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Your credentials and certifications</p>
        {!showAdd && !editingId && (
          <button
            onClick={() => {
              setShowAdd(true);
              setError(null);
            }}
            className={BTN_PRIMARY}
          >
            + Add Certification
          </button>
        )}
      </div>

      {showAdd && renderForm()}

      {isLoading && <p className="text-muted-foreground text-sm">Loading...</p>}
      {items && items.length === 0 && !showAdd && (
        <EmptyState label="No certifications added yet." />
      )}

      {items && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((item) =>
            editingId === item.id ? (
              <li key={item.id}>{renderForm()}</li>
            ) : (
              <li key={item.id} className="rounded-lg border border-border p-4 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{item.name}</p>
                    {item.issuer && (
                      <p className="text-sm text-muted-foreground">{item.issuer}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {item.issued_date ?? "—"}
                      {item.expiry_date ? ` – ${item.expiry_date}` : ""}
                    </p>
                    {item.credential_url && (
                      <a
                        href={item.credential_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary hover:underline"
                      >
                        View credential
                      </a>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => startEdit(item)} className={BTN_GHOST}>
                      Edit
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(item.id)}
                      disabled={deleteMutation.isPending}
                      className={BTN_DESTRUCT}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </li>
            )
          )}
        </ul>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const [activeTab, setActiveTab] = useState<Tab>("experience");

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">My Profile</h1>
        <p className="text-muted-foreground">
          Build and manage your master career data graph.
        </p>
      </div>

      <BasicInfoSection />

      <section className="space-y-4">
        <div className="flex gap-1 border-b border-border">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div>
          {activeTab === "experience" && <WorkExperienceSection />}
          {activeTab === "projects" && <ProjectsSection />}
          {activeTab === "skills" && <SkillsSection />}
          {activeTab === "certifications" && <CertificationsSection />}
        </div>
      </section>
    </main>
  );
}
