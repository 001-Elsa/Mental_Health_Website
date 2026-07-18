import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { authApi } from "../api/queries";
import { useAuthStore } from "../store/auth";

const loginSchema = z.object({
  nickname: z.string().min(1, "请输入昵称"),
  password: z.string().min(6, "密码至少 6 位"),
});

const registerSchema = loginSchema.extend({
  phone: z.string().regex(/^1[3-9]\d{9}$/, "请输入有效手机号"),
  code: z.string().min(4, "请输入验证码"),
});

type LoginForm = z.infer<typeof loginSchema>;
type RegisterForm = z.infer<typeof registerSchema>;

export default function AuthPanel() {
  const { user, setAuth } = useAuthStore();
  const [mode, setMode] = useState<"login" | "register" | null>(null);
  const [codeHint, setCodeHint] = useState("");

  const loginForm = useForm<LoginForm>({ resolver: zodResolver(loginSchema), defaultValues: { nickname: "测试用户1", password: "123456" } });
  const registerForm = useForm<RegisterForm>({ resolver: zodResolver(registerSchema) });

  const login = useMutation({
    mutationFn: authApi.login,
    onSuccess: (data) => {
      setAuth(data.token, data.user);
      setMode(null);
    },
  });

  const register = useMutation({
    mutationFn: authApi.register,
    onSuccess: () => setMode("login"),
  });

  const sendCode = useMutation({
    mutationFn: authApi.sendCode,
    onSuccess: (data) => setCodeHint(data.dev_code ? `本地验证码：${data.dev_code}` : data.message),
  });

  if (user) {
    return (
      <div className="auth-box">
        <Link to="/profile" className="account-entry" aria-label="打开个人信息">
          <span className="avatar">{user.avatar_url ? <img src={user.avatar_url} alt="" /> : user.nickname.slice(0, 1)}</span>
          <span className="user-name">{user.nickname}<small>{user.role === "admin" ? "管理员" : "学生"}</small></span>
        </Link>
      </div>
    );
  }

  return (
    <div className="auth-box">
      <button onClick={() => setMode("login")}>登录</button>
      <button className="ghost" onClick={() => setMode("register")}>注册</button>

      {mode && (
        <div className="modal-backdrop" onClick={() => setMode(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>{mode === "login" ? "登录" : "注册"}</h2>
              <button className="ghost" onClick={() => setMode(null)}>关闭</button>
            </div>
            {mode === "login" ? (
              <form onSubmit={loginForm.handleSubmit((values) => login.mutate(values))} className="form-grid">
                <input placeholder="昵称" {...loginForm.register("nickname")} />
                <input type="password" placeholder="密码" {...loginForm.register("password")} />
                <p className="error">{loginForm.formState.errors.nickname?.message || loginForm.formState.errors.password?.message || login.error?.message}</p>
                <button disabled={login.isPending}>登录</button>
              </form>
            ) : (
              <form onSubmit={registerForm.handleSubmit((values) => register.mutate(values))} className="form-grid">
                <input placeholder="昵称" {...registerForm.register("nickname")} />
                <input placeholder="手机号" {...registerForm.register("phone")} />
                <div className="inline">
                  <input placeholder="验证码" {...registerForm.register("code")} />
                  <button type="button" className="ghost" onClick={() => sendCode.mutate(registerForm.getValues("phone"))}>获取</button>
                </div>
                {codeHint && <p className="hint">{codeHint}</p>}
                <input type="password" placeholder="密码" {...registerForm.register("password")} />
                <p className="error">
                  {Object.values(registerForm.formState.errors)[0]?.message || register.error?.message}
                </p>
                <button disabled={register.isPending}>注册</button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
