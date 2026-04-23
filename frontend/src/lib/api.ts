import { getAccessToken } from "@/lib/auth";

export class ApiRequestError extends Error {
  constructor(
    public readonly detail: string,
    public readonly status: number,
  ) {
    super(detail);
    this.name = "ApiRequestError";
  }
}

interface RequestOptions {
  skipAuth?: boolean;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (!options.skipAuth) {
    const token = getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const json = await res.json();
      if (typeof json.detail === "string") detail = json.detail;
    } catch {
      // ignore parse failure
    }
    throw new ApiRequestError(detail, res.status);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("POST", path, body, options),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PATCH", path, body, options),
  delete: (path: string, options?: RequestOptions) =>
    request<void>("DELETE", path, undefined, options),
};
