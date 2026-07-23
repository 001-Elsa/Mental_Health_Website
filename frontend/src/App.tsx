import {
  BarChart3,
  BookOpenText,
  Bot,
  HeartHandshake,
  LayoutDashboard,
  MessageCircleMore,
  ShieldCheck,
} from "lucide-react";
import { lazy, Suspense, useEffect } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import AuthPanel from "./components/AuthPanel";
import { useAuthStore } from "./store/auth";
import { bootstrapAuth } from "./api/client";

const AdminPage = lazy(() => import("./pages/AdminPage"));
const ArticlesPage = lazy(() => import("./pages/ArticlesPage"));
const CommunityPage = lazy(() => import("./pages/CommunityPage"));
const ConsultPage = lazy(() => import("./pages/ConsultPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const MoodPage = lazy(() => import("./pages/MoodPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ShareEditorPage = lazy(() => import("./pages/ShareEditorPage"));

const userNav = [
  { label: "我的状态", path: "/dashboard", icon: LayoutDashboard },
  { label: "情绪记录", path: "/mood", icon: HeartHandshake },
  { label: "AI 倾听", path: "/consult", icon: Bot },
  { label: "心理内容", path: "/articles", icon: BookOpenText },
  { label: "同伴社区", path: "/community", icon: MessageCircleMore },
];

const pageTitles: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "用户模式", subtitle: "这里只展示你的记录、趋势、支持进展和个性化推荐" },
  "/mood": { title: "情绪记录", subtitle: "记录自己的状态变化，只有你和授权的安全流程可以使用这些数据" },
  "/consult": { title: "AI 倾听", subtitle: "围绕你的上下文提供支持，不向其他普通用户暴露私人会话" },
  "/articles": { title: "心理内容", subtitle: "阅读可信内容，也可以获得基于个人状态的推荐" },
  "/community": { title: "同伴社区", subtitle: "公开内容用于互助，私密内容只对自己可见" },
  "/community/new": { title: "发布同伴分享", subtitle: "选择公开或私密，并经过安全规则保护" },
  "/profile": { title: "个人中心", subtitle: "管理资料、发布记录与账号安全" },
  "/admin": { title: "后台管理员模式", subtitle: "管理员可以查看全站数据、风险队列、内容审核和审计记录" },
};

export default function App() {
  const location = useLocation();
  const role = useAuthStore((state) => state.user?.role);
  const initialized = useAuthStore((state) => state.initialized);
  useEffect(() => { void bootstrapAuth(); }, []);
  if (!initialized) return <div className="page-loading">正在恢复安全会话...</div>;
  const isAdmin = role === "admin";
  const meta = pageTitles[location.pathname] ?? pageTitles["/dashboard"];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon"><ShieldCheck size={21} /></span>
          <div>
            <strong>心晴 Campus</strong>
            <small>{isAdmin ? "后台管理员模式" : "用户模式"}</small>
          </div>
        </div>
        <nav aria-label="主要导航">
          {userNav.map(({ label, path, icon: Icon }) => (
            <NavLink key={path} to={path} aria-label={label} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
          {isAdmin && (
            <NavLink to="/admin" aria-label="后台管理员模式" className={({ isActive }) => (isActive ? "active" : "")}>
              <BarChart3 size={18} aria-hidden="true" />
              <span>后台管理</span>
            </NavLink>
          )}
        </nav>
        <p className="sidebar-foot">本平台提供心理支持与资源导航，不提供医疗诊断。紧急情况请联系专业机构或拨打 120 / 110。</p>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <h1>{meta.title}</h1>
            <p>{meta.subtitle}</p>
          </div>
          <AuthPanel />
        </header>
        <Suspense fallback={<div className="page-loading">正在加载页面...</div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/analytics" element={<Navigate to={isAdmin ? "/admin" : "/dashboard"} replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/articles" element={<ArticlesPage />} />
            <Route path="/records" element={<Navigate to="/articles?view=conversations" replace />} />
            <Route path="/mood" element={<MoodPage />} />
            <Route path="/community" element={<CommunityPage />} />
            <Route path="/community/new" element={<ShareEditorPage />} />
            <Route path="/consult" element={<ConsultPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/admin" element={isAdmin ? <AdminPage /> : <Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
