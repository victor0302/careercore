import { redirect } from "next/navigation";

/**
 * Root page — redirect to dashboard.
 * The dashboard will redirect to /auth/login if not authenticated.
 */
export default function RootPage() {
  redirect("/dashboard");
}
