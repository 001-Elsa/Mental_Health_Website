import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { GridComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import { ArrowRight, Bell, BookOpenText, Bot, CalendarDays, CheckCheck, HeartPulse, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { analyticsApi, authApi, moodApi, recommendationsApi } from "../api/queries";
import { useAuthStore } from "../store/auth";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export default function DashboardPage() {
  const qc = useQueryClient();
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const [trendScope, setTrendScope] = useState<"mine" | "all">(token ? "mine" : "all");

  useEffect(() => {
    setTrendScope(token ? "mine" : "all");
  }, [token]);

  const overview = useQuery({ queryKey: ["overview"], queryFn: analyticsApi.overview });
  const mood = useQuery({
    queryKey: ["moodTrend", trendScope],
    queryFn: () => analyticsApi.moodTrend(trendScope),
    enabled: trendScope === "all" || Boolean(token),
  });
  const myMood = useQuery({ queryKey: ["myMood"], queryFn: moodApi.mine, enabled: Boolean(token) });
  const activity = useQuery({ queryKey: ["userActivity"], queryFn: analyticsApi.userActivity });
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

  const latestMood = (myMood.data?.length ? myMood.data[myMood.data.length - 1].score : undefined) ?? [...(mood.data ?? [])].reverse().find((point) => point.avg_score != null)?.avg_score;
  const chartDates = mood.data?.map((point) => point.date.slice(5)) ?? [];
  const chartScores = mood.data?.map((point) => point.avg_score ?? null) ?? [];
  const hasTrendData = chartScores.some((score) => score != null);
  const stats = [
    { label: "近期平均情绪", value: latestMood != null ? `${latestMood}/10` : "待记录", icon: HeartPulse, helper: "最近 14 天" },
    { label: "平台情绪记录", value: overview.data?.total_mood_logs ?? "--", icon: CalendarDays, helper: "匿名聚合" },
    { label: "支持内容", value: recommendations.data?.items.length ?? "--", icon: BookOpenText, helper: token ? "为你筛选" : "登录后推荐" },
    { label: "互助同学", value: overview.data?.total_users ?? "--", icon: Users, helper: "平台累计" },
  ];

  return (
    <section className="page dashboard-page">
      <div className="welcome-band">
        <div><span className="section-kicker">Daily check-in</span><h2>{user ? `${user.nickname}，今天感觉怎么样？` : "今天感觉怎么样？"}</h2><p>用一分钟记录状态，长期趋势比单次分数更重要。</p></div>
        <div className="welcome-actions"><Link className="secondary-link" to="/mood">记录情绪 <ArrowRight size={16} /></Link><Link className="primary-link" to="/consult"><Bot size={17} /> 开始倾听</Link></div>
      </div>

      {riskStatus.data && riskStatus.data.level !== "low" && (
        <div className={`dashboard-risk-notice ${riskStatus.data.level}`}>
          <HeartPulse size={18} /><div><strong>近期状态需要多一点支持</strong><p>{riskStatus.data.reason}。{riskStatus.data.support_actions.join(" · ")}</p></div>
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
                <span>{item.title}</span><p>{item.content}</p><small>{item.created_at.slice(0, 16).replace("T", " ")}</small>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <div className="stats-grid">
        {stats.map(({ label, value, icon: Icon, helper }) => (
          <div className="stat-card" key={label}>
            <div className="stat-label"><Icon size={18} /><span>{label}</span></div>
            <strong>{value}</strong><small>{helper}</small>
          </div>
        ))}
      </div>

      <div className="dashboard-grid">
        <section className="workspace-section chart-section">
          <div className="section-heading trend-heading">
            <div><span className="section-kicker">Trend</span><h2>近期情绪趋势</h2></div>
            <div className="trend-scope-switch" role="group" aria-label="情绪趋势数据范围">
              <button
                type="button"
                className={trendScope === "mine" ? "active" : ""}
                aria-pressed={trendScope === "mine"}
                disabled={!token}
                title={token ? "查看我的情绪记录" : "登录后查看个人趋势"}
                onClick={() => setTrendScope("mine")}
              >我的趋势</button>
              <button
                type="button"
                className={trendScope === "all" ? "active" : ""}
                aria-pressed={trendScope === "all"}
                onClick={() => setTrendScope("all")}
              >全部用户</button>
            </div>
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
              <strong>{trendScope === "mine" ? "还没有个人情绪记录" : "近 14 天暂无平台记录"}</strong>
              <span>{trendScope === "mine" ? "记录一次情绪后，这里会显示你的变化。" : "有新的公开或私人记录后，聚合趋势会出现在这里。"}</span>
            </div>
          )}
        </section>

        <section className="workspace-section recommendations-section">
          <div className="section-heading"><div><span className="section-kicker">For you</span><h2>此刻适合阅读</h2></div><Link to="/articles">全部内容</Link></div>
          {token ? (
            <div className="recommendation-list">
              {recommendations.data?.items.slice(0, 3).map(({ article, reason }) => (
                <Link to="/articles" className="recommendation-item" key={article.id}><span>{article.category}</span><strong>{article.title}</strong><small>{reason}</small></Link>
              ))}
              {!recommendations.data?.items.length && <p className="muted">记录一次情绪后，推荐会更贴近你。</p>}
            </div>
          ) : <div className="signed-out-prompt"><BookOpenText size={24} /><p>登录后结合你的近期状态生成推荐。</p></div>}
        </section>
      </div>

      <section className="workspace-section activity-strip">
        <div><span className="section-kicker">Community pulse</span><h2>近 14 天平台参与</h2></div>
        <div className="activity-values">
          <span><strong>{activity.data?.reduce((sum, point) => sum + point.diary_users, 0) ?? 0}</strong>情绪记录人次</span>
          <span><strong>{activity.data?.reduce((sum, point) => sum + point.consultation_users, 0) ?? 0}</strong>AI 倾听人次</span>
          <span><strong>{activity.data?.reduce((sum, point) => sum + point.new_users, 0) ?? 0}</strong>新加入同学</span>
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
