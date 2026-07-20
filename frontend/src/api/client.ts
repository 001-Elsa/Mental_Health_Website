import { useAuthStore } from "../store/auth";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type RequestOptions = RequestInit & { auth?: boolean };

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const state = useAuthStore.getState();
  if (!state.refreshToken) return null;
  const response = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: state.refreshToken }),
  });
  if (!response.ok) {
    state.logout();
    return null;
  }
  const data = await response.json() as { token: string; refresh_token: string };
  state.setTokens(data.token, data.refresh_token);
  return data.token;
}

export async function api<T>(path: string, options: RequestOptions = {}, retried = false): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (options.auth !== false && token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401 && options.auth !== false && !retried && useAuthStore.getState().refreshToken) {
    refreshPromise ??= refreshAccessToken().finally(() => { refreshPromise = null; });
    const refreshed = await refreshPromise;
    if (refreshed) return api<T>(path, options, true);
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new ApiError(data?.detail || "请求失败", res.status);
  }
  return data as T;
}

export function toBody(data: unknown) {
  return JSON.stringify(data);
}
