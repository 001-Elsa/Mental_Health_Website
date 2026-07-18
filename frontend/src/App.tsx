import {
  BarChart3,
  BookOpenText,
  Bot,
  HeartHandshake,
  LayoutDashboard,
  MessageCircleMore,
  ShieldCheck,
} from "lucide-react";
import { lazy, Suspense } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import AuthPanel from "./components/AuthPanel";
import { useAuthStore } from "./store/auth";

const AdminPage = lazy(() => import("./pages/AdminPage"));
const ArticlesPage = lazy(() => import("./pages/ArticlesPage"));
const CommunityPage = lazy(() => import("./pages/CommunityPage"));
const ConsultPage = lazy(() => import("./pages/ConsultPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const MoodPage = lazy(() => import("./pages/MoodPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ShareEditorPage = lazy(() => import("./pages/ShareEditorPage"));

const nav = [
  { label: "状态总览", path: "/dashboard", icon: LayoutDashboard },
  { label: "情绪记录", path: "/mood", icon: HeartHandshake },
  { label: "AI 倾听", path: "/consult", icon: Bot },
  { label: "心理内容", path: "/articles", icon: BookOpenText },
  { label: "同伴社区", path: "/community", icon: MessageCircleMore },
];

const pageTitles: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "今日心理状态", subtitle: "从记录开始，找到适合你的下一步" },
  "/mood": { title: "情绪记录", subtitle: "留住变化，也看见触发情绪的线索" },
  "/consult": { title: "AI 倾听", subtitle: "连续对话、情绪理解与安全支持" },
  "/articles": { title: "心理内容", subtitle: "检索公开倾听记录与可信心理文章" },
  "/community": { title: "同伴社区", subtitle: "善意表达，彼此支持" },
  "/community/new": { title: "发布同伴分享", subtitle: "用文字、图片或语音记录真实经验" },
  "/profile": { title: "个人信息", subtitle: "管理资料、发布记录与账号安全" },
  "/admin": { title: "运营工作台", subtitle: "风险处置、内容治理与平台指标" },
};

export default function App() {
  const location = useLocation();
  const role = useAuthStore((state) => state.user?.role);
  const meta = pageTitles[location.pathname] ?? pageTitles["/dashboard"];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon"><ShieldCheck size={21} /></span>
          <div>
            <strong>心晴 Campus</strong>
            <small>高校心理支持平台</small>
          </div>
        </div>
        <nav aria-label="主要导航">
          {nav.map(({ label, path, icon: Icon }) => (
            <NavLink key={path} to={path} aria-label={label} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
          {role === "admin" && (
            <NavLink to="/admin" aria-label="运营工作台" className={({ isActive }) => (isActive ? "active" : "")}>
              <BarChart3 size={18} aria-hidden="true" />
              <span>运营工作台</span>
            </NavLink>
          )}
        </nav>
        <p className="sidebar-foot">本平台不提供医疗诊断。紧急情况请联系专业机构或拨打 120 / 110。</p>
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
            <Route path="/analytics" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/articles" element={<ArticlesPage />} />
            <Route path="/records" element={<Navigate to="/articles?view=conversations" replace />} />
            <Route path="/mood" element={<MoodPage />} />
            <Route path="/community" element={<CommunityPage />} />
            <Route path="/community/new" element={<ShareEditorPage />} />
            <Route path="/consult" element={<ConsultPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/admin" element={role === "admin" ? <AdminPage /> : <Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
