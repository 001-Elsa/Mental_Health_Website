import type { ReactNode } from "react";
import { useAuthStore } from "../store/auth";

export default function RequireLogin({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) {
    return <p className="notice">请先登录后再执行这个操作。测试账号：测试用户1 / 123456。</p>;
  }
  return <>{children}</>;
}
