/**
 * Token storage and refresh utilities.
 * Access tokens are stored in localStorage. Refresh tokens live in an
 * httpOnly cookie and are never exposed to frontend JavaScript.
 */

const ACCESS_TOKEN_KEY = "cc_access_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export async function refreshAccessToken(): Promise<string | null> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${apiUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({}),
    });

    if (!res.ok) {
      clearTokens();
      return null;
    }

    const data = (await res.json()) as { access_token: string };
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}
