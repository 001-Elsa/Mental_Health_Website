import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";
import { useAuthStore } from "../store/auth";

describe("API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null, initialized: true });
  });

  it("preserves the HTTP status when a proxy returns a non-JSON error page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 })));
    await expect(api("/api/example", { auth: false })).rejects.toMatchObject({
      status: 502,
      message: "服务暂时不可用，请稍后重试",
    });
  });

  it("uses a structured API error detail when available", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "参数错误" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    })));
    await expect(api("/api/example", { auth: false })).rejects.toMatchObject({ status: 422, message: "参数错误" });
  });

  it("refreshes through the HttpOnly cookie and retries once after a 401", async () => {
    useAuthStore.setState({ token: "expired" });
    const mockedFetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ token: "new-access" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", mockedFetch);

    await expect(api<{ ok: boolean }>("/api/protected")).resolves.toEqual({ ok: true });
    expect(useAuthStore.getState().token).toBe("new-access");
    expect(mockedFetch).toHaveBeenNthCalledWith(2, "/api/auth/refresh", expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
    }));
  });
});
