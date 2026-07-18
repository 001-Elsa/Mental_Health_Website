export type User = {
  id: number;
  username?: string;
  nickname: string;
  phone?: string;
  email?: string;
  avatar_url?: string;
  background_url?: string;
  signature?: string;
  created_at?: string;
  role?: "student" | "admin";
};

export type AuthPayload = {
  token: string;
  user: User;
};

export type Article = {
  id: number;
  title: string;
  author: string;
  summary: string;
  cover_image: string;
  content: string;
  category: string;
  status: string;
  source_name: string;
  source_url: string;
  published_at: string | null;
  read_count: number;
  created_at: string;
};

export type PlazaMessage = {
  id: number;
  user_id: number;
  author_name: string;
  content: string;
  image_url: string;
  audio_url: string;
  status: "published" | "pending_review" | "hidden";
  created_at: string;
};

export type MoodLog = {
  id: number;
  user_id: number;
  score: number;
  trigger: string;
  note: string;
  visibility: string;
  bookmark_count: number;
  created_at: string;
  risk?: { level: RiskLevel; score: number; signals: string[] };
};

export type Discussion = {
  id: number;
  user_id: number;
  title: string;
  content: string;
  image_url: string;
  audio_url: string;
  category: string;
  reply_count: number;
  view_count: number;
  like_count: number;
  status: "published" | "pending_review" | "hidden";
  moderation_reason: string;
  visibility: "公开" | "私人";
  created_at: string;
};

export type Reply = {
  id: number;
  discussion_id: number;
  user_id: number;
  content: string;
  status: string;
  created_at: string;
};

export type PublicConversation = {
  id: number;
  title: string;
  summary: string;
  emotion_tag: string;
  created_at: string;
};

export type TrendPoint = {
  date: string;
  avg_score?: number | null;
  count: number;
  user_count?: number;
};

export type ActivityPoint = {
  date: string;
  active_users: number;
  new_users: number;
  diary_users: number;
  consultation_users: number;
};

export type RiskLevel = "low" | "medium" | "high" | "critical";

export type ChatResponse = {
  reply: string;
  message_count: number;
  emotion: string;
  risk: {
    level: RiskLevel;
    score: number;
    signals: string[];
    requires_intervention: boolean;
  };
  support_actions: string[];
  profile_summary: string;
  recommended_exercises: Exercise[];
};

export type Exercise = {
  id: number;
  title: string;
  category: string;
  description: string;
  steps: string;
  duration_minutes: number;
  reason?: string;
};

export type AdminOverview = {
  total_users: number;
  active_users_1d: number;
  active_users_7d: number;
  consultations_7d: number;
  pending_risks: number;
  critical_risks: number;
  overdue_risks: number;
  pending_reports: number;
  pending_content: number;
  avg_mood_7d: number;
  community_posts_7d: number;
};

export type RiskEvent = {
  id: number;
  user_id: number;
  nickname: string;
  consultation_id: number | null;
  conversation_id: string;
  level: RiskLevel;
  score: number;
  signals: string;
  excerpt: string;
  status: string;
  assigned_to: number | null;
  assignee_name: string;
  due_at: string | null;
  overdue: boolean;
  next_follow_up_at: string | null;
  version: number;
  event_type: "conversation" | "mood_trend";
  model_level: string;
  model_reason: string;
  created_at: string;
};

export type RiskAction = {
  id: number;
  action: string;
  from_status: string;
  to_status: string;
  note: string;
  actor_id: number | null;
  actor_name: string;
  created_at: string;
};

export type AuditLog = {
  id: number;
  actor_id: number;
  actor_name: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  request_id: string;
  created_at: string;
};

export type Notification = {
  id: number;
  notification_type: string;
  title: string;
  content: string;
  link: string;
  read_at: string | null;
  created_at: string;
};

export type CommunityReport = {
  id: number;
  reporter_id: number;
  target_type: string;
  target_id: number;
  reason: string;
  detail: string;
  status: string;
  created_at: string;
};

export type AdminTrend = {
  date: string;
  avg_mood: number | null;
  consultations: number;
  risk_events: number;
};

export type AdminUser = {
  id: number;
  nickname: string;
  phone: string;
  role: "student" | "admin";
  created_at: string;
};

export type SensitiveWord = {
  id: number;
  word: string;
  category: string;
  enabled: boolean;
  created_at: string;
};
