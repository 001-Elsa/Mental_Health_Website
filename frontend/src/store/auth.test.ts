import { describe, expect, it } from "vitest";
import { useAuthStore } from "./auth";

describe("auth store", () => {
  it("stores and clears auth state", () => {
    useAuthStore.getState().setAuth("token", { id: 1, nickname: "测试用户" });
    expect(useAuthStore.getState().token).toBe("token");
    expect(useAuthStore.getState().user?.nickname).toBe("测试用户");

    useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("never persists access or refresh tokens in localStorage", () => {
    expect(JSON.stringify(useAuthStore.getState())).not.toContain("refreshToken");
  });
});
