/**
 * Typed fetch wrapper for the CareerCore API.
 *
 * - Attaches Authorization: Bearer header automatically.
 * - On 401, attempts a token refresh once and retries.
 * - Throws ApiRequestError on non-OK responses.
 */

import { clearTokens, getAccessToken, refreshAccessToken } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string
  ) {
    super(`API error ${status}: ${detail}`);
    this.name = "ApiRequestError";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipAuth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth = false, headers: extraHeaders = {}, ...rest } = options;

  const buildHeaders = (token: string | null): Record<string, string> => ({
    "Content-Type": "application/json",
    ...(token && !skipAuth ? { Authorization: `Bearer ${token}` } : {}),
    ...(extraHeaders as Record<string, string>),
  });

  const makeRequest = async (token: string | null): Promise<Response> => {
    return fetch(`${BASE_URL}${path}`, {
      ...rest,
      credentials: rest.credentials ?? "include",
      headers: buildHeaders(token),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let token = skipAuth ? null : getAccessToken();
  let res = await makeRequest(token);

  // Attempt token refresh on 401
  if (res.status === 401 && !skipAuth) {
    token = await refreshAccessToken();
    if (!token) {
      clearTokens();
      throw new ApiRequestError(401, "Session expired. Please log in again.");
    }
    res = await makeRequest(token);
  }

  if (!res.ok) {
    let detail = "Unknown error";
    try {
      const err = (await res.json()) as { detail?: string };
      detail = err.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiRequestError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

// ── Convenience methods ───────────────────────────────────────────────────────

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET" }),

  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),

  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),

  delete: <T = void>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
