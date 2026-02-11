/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * API client — thin wrapper over fetch.
 *
 * Auth: X-Session-Token header (stored in localStorage).
 * Errors: standardized { message, requestId } shape.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// Warn if the API base URL was not set at build time (common Vercel misconfiguration)
if (typeof window !== "undefined" && BASE === "http://localhost:8000") {
  console.warn(
    "[Finitii] NEXT_PUBLIC_API_BASE_URL is not set — API calls will go to localhost:8000. " +
    "Set this env var in your Vercel project settings and redeploy."
  );
}

export interface ApiError {
  message: string;
  requestId: string | null;
  status: number;
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("session_token");
}

export function setToken(token: string) {
  localStorage.setItem("session_token", token);
  // Also set cookie for Next.js middleware auth redirect
  document.cookie = `session_token=${token}; path=/; SameSite=Lax`;
}

export function clearToken() {
  localStorage.removeItem("session_token");
  document.cookie = "session_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

export function hasToken(): boolean {
  return !!getToken();
}

async function request<T = any>(
  path: string,
  opts: RequestInit = {}
): Promise<{ data: T; requestId: string | null }> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  if (token) {
    headers["X-Session-Token"] = token;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...opts,
      headers,
    });
  } catch {
    // fetch throws TypeError on network failure (CORS block, DNS, offline, wrong URL)
    const hint = BASE.includes("localhost")
      ? " Check that NEXT_PUBLIC_API_BASE_URL is set to your backend URL."
      : "";
    const err: ApiError = {
      message: `Cannot reach the server.${hint}`,
      requestId: null,
      status: 0,
    };
    throw err;
  }

  const requestId =
    res.headers.get("x-request-id") || res.headers.get("X-Request-ID");

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      message = body.detail || body.message || message;
    } catch {
      // no JSON body
    }
    const err: ApiError = { message, requestId, status: res.status };
    throw err;
  }

  // 204 No Content
  if (res.status === 204) {
    return { data: null as T, requestId };
  }

  const data = await res.json();
  return { data, requestId };
}

export const api = {
  get: <T = any>(path: string) => request<T>(path, { method: "GET" }),
  post: <T = any>(path: string, body?: any) =>
    request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  put: <T = any>(path: string, body?: any) =>
    request<T>(path, {
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T = any>(path: string, body?: any) =>
    request<T>(path, {
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T = any>(path: string) => request<T>(path, { method: "DELETE" }),

  /** Raw fetch for file downloads. */
  raw: async (path: string) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["X-Session-Token"] = token;
    return fetch(`${BASE}${path}`, { headers });
  },
};

export function isApiError(e: unknown): e is ApiError {
  return (
    typeof e === "object" &&
    e !== null &&
    "message" in e &&
    "status" in e
  );
}
