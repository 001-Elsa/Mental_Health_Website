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
  try {
    const response = await fetchWithTimeout("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    });
    if (!response.ok) {
      state.logout();
      return null;
    }
    const data = await response.json() as { token: string };
    state.setToken(data.token);
    return data.token;
  } catch {
    state.logout();
    return null;
  }
}

const DEFAULT_TIMEOUT_MS = 20_000;

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}) {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  const abortFromCaller = () => controller.abort();
  init.signal?.addEventListener("abort", abortFromCaller, { once: true });
  try {
    return await fetch(input, { ...init, signal: controller.signal, credentials: init.credentials ?? "same-origin" });
  } finally {
    globalThis.clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export async function bootstrapAuth(): Promise<void> {
  const token = await refreshAccessToken();
  if (!token) {
    useAuthStore.getState().setInitialized(true);
    return;
  }
  try {
    const user = await api<import("../types").User>("/api/users/me", {}, true);
    useAuthStore.getState().setAuth(token, user);
  } catch {
    useAuthStore.getState().logout();
  }
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
  const res = await fetchWithTimeout(path, { ...options, headers });
  if (res.status === 401 && options.auth !== false && !retried) {
    refreshPromise ??= refreshAccessToken().finally(() => { refreshPromise = null; });
    const refreshed = await refreshPromise;
    if (refreshed) return api<T>(path, options, true);
  }
  const text = await res.text();
  let data: any = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }
  if (!res.ok) {
    const fallback = res.status >= 500 ? "服务暂时不可用，请稍后重试" : `请求失败（HTTP ${res.status}）`;
    throw new ApiError(data?.detail || fallback, res.status);
  }
  return data as T;
}

export function toBody(data: unknown) {
  return JSON.stringify(data);
}
