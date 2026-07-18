import { api, toBody } from "./client";
import type {
  ActivityPoint,
  AuditLog,
  AdminTrend,
  AdminUser,
  AdminOverview,
  Article,
  AuthPayload,
  ChatResponse,
  CommunityReport,
  Discussion,
  MoodLog,
  PublicConversation,
  PlazaMessage,
  Reply,
  RiskEvent,
  RiskAction,
  SensitiveWord,
  TrendPoint,
  User,
} from "../types";

export const authApi = {
  login: (payload: { nickname: string; password: string; remember_me?: boolean }) =>
    api<AuthPayload>("/api/auth/login", { method: "POST", body: toBody(payload), auth: false }),
  sendCode: (phone: string) =>
    api<{ ok: boolean; dev_code?: string; message: string }>("/api/auth/send-code", {
      method: "POST",
      body: toBody({ phone }),
      auth: false,
    }),
  register: (payload: { nickname: string; phone: string; code: string; password: string }) =>
    api<{ ok: boolean }>("/api/auth/register", { method: "POST", body: toBody(payload), auth: false }),
  me: () => api<User>("/api/users/me"),
  updateMe: (payload: { nickname: string; signature: string }) =>
    api<User>("/api/users/me", { method: "PATCH", body: toBody(payload) }),
  uploadProfileMedia: (kind: "avatar" | "background", file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api<{ url: string; kind: "avatar" | "background"; user: User }>(`/api/users/me/media?kind=${kind}`, { method: "POST", body: form });
  },
  changePassword: (payload: { current_password: string; new_password: string }) =>
    api<{ ok: boolean; message: string }>("/api/users/me/password", { method: "POST", body: toBody(payload) }),
  changePhone: (payload: { new_phone: string; code: string; current_password: string }) =>
    api<User>("/api/users/me/phone", { method: "POST", body: toBody(payload) }),
  sendEmailCode: (payload: { email: string; current_password: string }) =>
    api<{ ok: boolean; dev_code?: string; message: string }>("/api/users/me/email-code", { method: "POST", body: toBody(payload) }),
  bindEmail: (payload: { email: string; code: string; current_password: string }) =>
    api<User>("/api/users/me/email", { method: "POST", body: toBody(payload) }),
  profile: () => api<{
    summary: string;
    dominant_emotions: string[];
    recommendation_emotion: RecommendationEmotion | "";
    stressors: string[];
    coping_preferences: string[];
    updated_at: string | null;
  }>("/api/users/me/profile"),
  notifications: () => api<{
    unread_count: number;
    items: import("../types").Notification[];
  }>("/api/users/me/notifications"),
  readNotification: (id: number) => api<{ ok: boolean }>(`/api/users/me/notifications/${id}/read`, { method: "PATCH" }),
  readAllNotifications: () => api<{ ok: boolean; updated: number }>("/api/users/me/notifications/read-all", { method: "PATCH" }),
};

export const analyticsApi = {
  overview: () =>
    api<{ total_users: number; total_mood_logs: number; total_consultations: number; avg_mood_score: number }>(
      "/api/analytics/overview",
      { auth: false },
    ),
  moodTrend: (scope: "mine" | "all" = "all") =>
    api<TrendPoint[]>(`/api/analytics/mood-trend?days=14&scope=${scope}`, { auth: scope === "mine" }),
  consultationStats: () => api<TrendPoint[]>("/api/analytics/consultation-stats?days=14", { auth: false }),
  userActivity: () => api<ActivityPoint[]>("/api/analytics/user-activity?days=14", { auth: false }),
  moodForecast: () => api<{
    trend: "improving" | "declining" | "stable" | "insufficient_data";
    confidence: number;
    sample_size: number;
    points: Array<{ date: string; predicted_score: number }>;
    disclaimer?: string;
  }>("/api/analytics/mood-forecast?days=7"),
};

export const articlesApi = {
  list: (filters: { keyword?: string; period?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.keyword?.trim()) params.set("title", filters.keyword.trim());
    if (filters.period) params.set("period", filters.period);
    const query = params.toString();
    return api<Article[]>(`/api/articles/${query ? `?${query}` : ""}`, { auth: false });
  },
  create: (payload: Partial<Article>) => api<Article>("/api/articles/", { method: "POST", body: toBody(payload) }),
  update: (id: number, payload: Partial<Article>) => api<Article>(`/api/articles/${id}`, { method: "PATCH", body: toBody(payload) }),
  remove: (id: number) => api<{ ok: boolean }>(`/api/articles/${id}`, { method: "DELETE" }),
  comments: (id: number) => api<Array<{ id: number; user_id: number; content: string; created_at: string }>>(`/api/articles/${id}/comments`, { auth: false }),
  comment: (id: number, content: string) => api(`/api/articles/${id}/comments`, { method: "POST", body: toBody({ article_id: id, content }) }),
};

export const moodApi = {
  list: () => api<MoodLog[]>("/api/mood/", { auth: false }),
  mine: () => api<MoodLog[]>("/api/mood/mine"),
  riskStatus: () => api<{ level: import("../types").RiskLevel; score: number; reason: string; support_actions: string[] }>("/api/mood/risk-status"),
  create: (payload: { score: number; trigger: string; note: string; visibility: string }) =>
    api<MoodLog>("/api/mood/", { method: "POST", body: toBody(payload) }),
  bookmark: (id: number) => api<{ bookmarked: boolean; bookmark_count: number }>(`/api/mood/${id}/bookmark`, { method: "POST" }),
};

export const discussionsApi = {
  list: () => api<Discussion[]>("/api/discussions/", { auth: false }),
  create: (payload: { title: string; category: string; content: string; visibility: "公开" | "私人"; image_url?: string; audio_url?: string }) =>
    api<Discussion>("/api/discussions/", { method: "POST", body: toBody(payload) }),
  uploadMedia: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api<{ url: string; media_type: "image" | "audio" }>("/api/discussions/media", { method: "POST", body: form });
  },
  plaza: () => api<PlazaMessage[]>("/api/discussions/plaza", { auth: false }),
  sendToPlaza: (payload: { content: string; image_url?: string; audio_url?: string }) =>
    api<PlazaMessage>("/api/discussions/plaza", { method: "POST", body: toBody(payload) }),
  mine: () => api<Discussion[]>("/api/discussions/mine"),
  replies: (id: number) => api<Reply[]>(`/api/discussions/${id}/replies`, { auth: false }),
  reply: (id: number, content: string) => api<Reply>(`/api/discussions/${id}/replies`, { method: "POST", body: toBody({ discussion_id: id, content }) }),
  like: (id: number) => api<{ liked: boolean; like_count: number }>(`/api/discussions/${id}/like`, { method: "POST" }),
  report: (id: number, reason: string, detail = "") =>
    api<{ ok: boolean; report_id: number }>(`/api/discussions/${id}/reports`, {
      method: "POST",
      body: toBody({ reason, detail }),
    }),
};

export const contentApi = {
  publicConversations: (filters: { keyword?: string; period?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.keyword?.trim()) params.set("keyword", filters.keyword.trim());
    if (filters.period) params.set("period", filters.period);
    const query = params.toString();
    return api<PublicConversation[]>(`/api/content/public-conversations${query ? `?${query}` : ""}`, { auth: false });
  },
};

export const consultApi = {
  conversations: (query = "") => api<Array<{
    consultation_id: number;
    conversation_id: string;
    title: string;
    message_count: number;
    visibility: "公开" | "私人";
    pinned: boolean;
    emotion_tag: string;
    risk_level: import("../types").RiskLevel;
    started_at: string;
  }>>(`/api/consult/conversations${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`),
  updateConversation: (id: string, payload: { title?: string; pinned?: boolean }) =>
    api<{ conversation_id: string; title: string; pinned: boolean }>(`/api/consult/conversations/${id}`, {
      method: "PATCH",
      body: toBody(payload),
    }),
  setConversationVisibility: (id: string, visibility: "公开" | "私人") =>
    api<{ conversation_id: string; visibility: "公开" | "私人" }>(`/api/consult/conversations/${id}/visibility?visibility=${encodeURIComponent(visibility)}`, {
      method: "PATCH",
    }),
  removeConversation: (id: string) =>
    api<{ ok: boolean }>(`/api/consult/conversations/${id}`, { method: "DELETE" }),
  history: (id: string) => api<Array<{ role: "user" | "assistant"; content: string; created_at: string }>>(`/api/consult/history/${id}`),
  chat: (payload: { conversation_id: string; message: string; visibility: string; request_key?: string }) =>
    api<ChatResponse>("/api/consult/chat", {
      method: "POST",
      body: toBody({ ...payload, request_key: payload.request_key ?? crypto.randomUUID() }),
    }),
};

export const recommendationsApi = {
  articles: () => api<{
    profile: { emotion: RecommendationEmotion; is_manual: boolean; recent_mood: number | null; summary: string; stressors: string[] };
    items: Array<{ article: Article; reason: string }>;
  }>("/api/recommendations/articles"),
  setPreference: (emotion: RecommendationEmotion) => api<{ emotion: RecommendationEmotion; is_manual: true }>("/api/recommendations/preference", {
    method: "PUT",
    body: toBody({ emotion }),
  }),
  exercises: () => api<{
    emotion: RecommendationEmotion;
    is_manual: boolean;
    items: import("../types").Exercise[];
  }>("/api/recommendations/exercises"),
};

export type RecommendationEmotion = "焦虑" | "低落" | "烦躁" | "平静" | "愉悦";

export const adminApi = {
  overview: () => api<AdminOverview>("/api/admin/overview"),
  trends: () => api<AdminTrend[]>("/api/admin/trends?days=14"),
  risks: () => api<RiskEvent[]>("/api/admin/risk-events?status=open"),
  handleRisk: (id: number, payload: {
    status: "assigned" | "contacted" | "follow_up" | "resolved" | "false_positive";
    expected_version: number;
    note?: string;
    assignee_id?: number;
    next_follow_up_at?: string;
  }) => api<{ ok: boolean; status: string; version: number }>(`/api/admin/risk-events/${id}`, { method: "PATCH", body: toBody(payload) }),
  riskTimeline: (id: number) => api<RiskAction[]>(`/api/admin/risk-events/${id}/timeline`),
  auditLogs: () => api<AuditLog[]>("/api/admin/audit-logs?limit=50"),
  reports: () => api<CommunityReport[]>("/api/admin/reports?status=pending"),
  handleReport: (id: number, action: string) =>
    api<{ ok: boolean }>(`/api/admin/reports/${id}`, { method: "PATCH", body: toBody({ action }) }),
  moderation: () => api<Discussion[]>("/api/admin/moderation"),
  moderate: (id: number, action: "approve" | "hide") =>
    api<{ ok: boolean }>(`/api/admin/moderation/${id}?action=${action}`, { method: "PATCH" }),
  users: () => api<AdminUser[]>("/api/admin/users"),
  updateRole: (id: number, role: "student" | "admin") =>
    api<{ ok: boolean }>(`/api/admin/users/${id}/role`, { method: "PATCH", body: toBody({ role }) }),
  words: () => api<SensitiveWord[]>("/api/admin/sensitive-words"),
  addWord: (word: string, category = "unsafe") =>
    api<SensitiveWord>("/api/admin/sensitive-words", { method: "POST", body: toBody({ word, category }) }),
  toggleWord: (id: number) => api<{ ok: boolean }>(`/api/admin/sensitive-words/${id}/toggle`, { method: "PATCH" }),
  removeWord: (id: number) => api<{ ok: boolean }>(`/api/admin/sensitive-words/${id}`, { method: "DELETE" }),
  articles: () => api<Article[]>("/api/admin/articles"),
  updateArticleStatus: (id: number, status: "已发布" | "草稿") =>
    api<{ ok: boolean }>(`/api/admin/articles/${id}/status`, { method: "PATCH", body: toBody({ status }) }),
};

export const knowledgeApi = {
  ask: (question: string) => api<{
    answer: string;
    citations: Array<{ id: string; title: string; source: string; score: number }>;
    personalization: { own_history: number; public_conversations: number };
  }>("/api/knowledge/ask", { method: "POST", body: toBody({ question }) }),
};
