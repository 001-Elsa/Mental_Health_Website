import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { GridComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import { ArrowRight, Bell, BookOpenText, Bot, CalendarDays, CheckCheck, HeartPulse, MessageCircleMore } from "lucide-react";
import { Link } from "react-router-dom";
import { analyticsApi, authApi, moodApi, recommendationsApi } from "../api/queries";
import { useAuthStore } from "../store/auth";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export default function DashboardPage() {
  const qc = useQueryClient();
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);

  const overview = useQuery({ queryKey: ["overview", "mine"], queryFn: analyticsApi.overview, enabled: Boolean(token) });
  const mood = useQuery({ queryKey: ["moodTrend", "mine"], queryFn: () => analyticsApi.moodTrend("mine"), enabled: Boolean(token) });
  const myMood = useQuery({ queryKey: ["myMood"], queryFn: moodApi.mine, enabled: Boolean(token) });
  const forecast = useQuery({ queryKey: ["moodForecast"], queryFn: analyticsApi.moodForecast, enabled: Boolean(token) });
  const riskStatus = useQuery({ queryKey: ["riskStatus"], queryFn: moodApi.riskStatus, enabled: Boolean(token) });
  const recommendations = useQuery({ queryKey: ["recommendations"], queryFn: recommendationsApi.articles, enabled: Boolean(token) });
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: authApi.notifications, enabled: Boolean(token) });
  const readNotification = useMutation({
    mutationFn: authApi.readNotification,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const readAllNotifications = useMutation({
    mutationFn: authApi.readAllNotifications,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const latestMood = myMood.data?.length ? myMood.data[myMood.data.length - 1].score : undefined;
  const chartDates = mood.data?.map((point) => point.date.slice(5)) ?? [];
  const chartScores = mood.data?.map((point) => point.avg_score ?? null) ?? [];
  const hasTrendData = chartScores.some((score) => score != null);
  const stats = [
    { label: "我的平均情绪", value: overview.data?.avg_mood_score ? `${overview.data.avg_mood_score}/10` : latestMood ? `${latestMood}/10` : "待记录", icon: HeartPulse, helper: "仅统计你的记录" },
    { label: "我的情绪记录", value: overview.data?.total_mood_logs ?? "--", icon: CalendarDays, helper: "个人可见范围" },
    { label: "我的 AI 倾听", value: overview.data?.total_consultations ?? "--", icon: MessageCircleMore, helper: "私密会话默认保护" },
    { label: "个性化推荐", value: recommendations.data?.items.length ?? "--", icon: BookOpenText, helper: token ? "基于你的状态" : "登录后生成" },
  ];

  if (!token) {
    return (
      <section className="page dashboard-page">
        <div className="welcome-band">
          <div>
            <span className="section-kicker">User mode</span>
            <h2>登录后进入你的个人心理支持空间</h2>
            <p>用户模式只展示你的情绪记录、AI 倾听、支持进展和个性化推荐；全站数据只在管理员模式中开放。</p>
          </div>
          <div className="welcome-actions">
            <Link className="primary-link" to="/consult"><Bot size={17} /> 先看看 AI 倾听</Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="page dashboard-page">
      <div className="welcome-band">
        <div>
          <span className="section-kicker">User mode</span>
          <h2>{user ? `${user.nickname}，今天感觉怎么样？` : "今天感觉怎么样？"}</h2>
          <p>这里是你的个人视角：记录、趋势、会话、通知和推荐都只围绕你自己展开。</p>
        </div>
        <div className="welcome-actions">
          <Link className="secondary-link" to="/mood">记录情绪 <ArrowRight size={16} /></Link>
          <Link className="primary-link" to="/consult"><Bot size={17} /> 开始倾听</Link>
        </div>
      </div>

      {riskStatus.data && riskStatus.data.level !== "low" && (
        <div className={`dashboard-risk-notice ${riskStatus.data.level}`}>
          <HeartPulse size={18} />
          <div>
            <strong>近期状态需要多一点支持</strong>
            <p>{riskStatus.data.reason}。{riskStatus.data.support_actions.join(" / ")}</p>
          </div>
        </div>
      )}

      {notifications.data?.items.length ? (
        <section className="notification-center">
          <div className="notification-heading">
            <span><Bell size={17} />支持进展 {notifications.data.unread_count > 0 && <strong>{notifications.data.unread_count}</strong>}</span>
            {notifications.data.unread_count > 0 && <button className="text-button" onClick={() => readAllNotifications.mutate()}><CheckCheck size={15} />全部已读</button>}
          </div>
          <div className="notification-list">
            {notifications.data.items.slice(0, 3).map((item) => (
              <button className={item.read_at ? "read" : ""} key={item.id} onClick={() => !item.read_at && readNotification.mutate(item.id)}>
                <span>{item.title}</span>
                <p>{item.content}</p>
                <small>{item.created_at.slice(0, 16).replace("T", " ")}</small>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <div className="stats-grid">
        {stats.map(({ label, value, icon: Icon, helper }) => (
          <div className="stat-card" key={label}>
            <div className="stat-label"><Icon size={18} /><span>{label}</span></div>
            <strong>{value}</strong>
            <small>{helper}</small>
          </div>
        ))}
      </div>

      <div className="dashboard-grid">
        <section className="workspace-section chart-section">
          <div className="section-heading trend-heading">
            <div><span className="section-kicker">My trend</span><h2>我的近期情绪趋势</h2></div>
          </div>
          {mood.isLoading ? (
            <div className="trend-chart-empty">正在加载趋势...</div>
          ) : hasTrendData ? (
            <ReactEChartsCore
              echarts={echarts}
              option={{
                color: ["#28766f"],
                tooltip: { trigger: "axis" },
                grid: { left: 34, right: 18, top: 24, bottom: 26 },
                xAxis: { type: "category", boundaryGap: false, data: chartDates, axisLine: { lineStyle: { color: "#d9dfdc" } }, axisLabel: { color: "#788581" } },
                yAxis: { type: "value", min: 0, max: 10, splitLine: { lineStyle: { color: "#edf0ee" } }, axisLabel: { color: "#788581" } },
                series: [{ type: "line", smooth: true, symbolSize: 7, connectNulls: true, data: chartScores, areaStyle: { color: "rgba(40, 118, 111, .09)" } }],
              }}
              style={{ height: 300 }}
            />
          ) : (
            <div className="trend-chart-empty">
              <HeartPulse size={24} />
              <strong>还没有个人情绪记录</strong>
              <span>记录一次情绪后，这里会显示你的变化。</span>
            </div>
          )}
        </section>

        <section className="workspace-section recommendations-section">
          <div className="section-heading"><div><span className="section-kicker">For you</span><h2>此刻适合阅读</h2></div><Link to="/articles">全部内容</Link></div>
          <div className="recommendation-list">
            {recommendations.data?.items.slice(0, 3).map(({ article, reason }) => (
              <Link to="/articles" className="recommendation-item" key={article.id}>
                <span>{article.category}</span>
                <strong>{article.title}</strong>
                <small>{reason}</small>
              </Link>
            ))}
            {!recommendations.data?.items.length && <p className="muted">记录一次情绪后，推荐会更贴近你。</p>}
          </div>
        </section>
      </div>

      <section className="workspace-section activity-strip">
        <div><span className="section-kicker">Personal boundary</span><h2>用户模式只显示个人数据</h2></div>
        <div className="activity-values">
          <span><strong>{overview.data?.total_mood_logs ?? 0}</strong>我的情绪记录</span>
          <span><strong>{overview.data?.total_consultations ?? 0}</strong>我的倾听会话</span>
          <span><strong>{notifications.data?.unread_count ?? 0}</strong>未读支持通知</span>
        </div>
        {forecast.data && forecast.data.trend !== "insufficient_data" && (
          <div className={`forecast-chip ${forecast.data.trend}`}>
            <span>未来 7 天趋势</span>
            <strong>{forecast.data.trend === "improving" ? "缓慢上升" : forecast.data.trend === "declining" ? "需要关注" : "相对稳定"}</strong>
            <small>基线置信度 {Math.round(forecast.data.confidence * 100)}%</small>
          </div>
        )}
      </section>
    </section>
  );
}
