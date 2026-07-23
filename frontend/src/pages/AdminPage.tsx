import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileText,
  FileWarning,
  Gauge,
  History,
  Settings2,
  ShieldAlert,
  Trash2,
  UserCog,
  Users,
} from "lucide-react";
import { adminApi } from "../api/queries";
import type { RiskLevel } from "../types";

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const riskLabels: Record<RiskLevel, string> = {
  low: "低风险",
  medium: "需关注",
  high: "高风险",
  critical: "紧急",
};

export default function AdminPage() {
  const [tab, setTab] = useState<"safety" | "operations">("safety");
  const [newWord, setNewWord] = useState("");
  const [selectedRiskId, setSelectedRiskId] = useState<number | null>(null);
  const [riskNote, setRiskNote] = useState("");
  const [followUpAt, setFollowUpAt] = useState("");
  const qc = useQueryClient();
  const overview = useQuery({ queryKey: ["admin-overview"], queryFn: adminApi.overview });
  const trends = useQuery({ queryKey: ["admin-trends"], queryFn: adminApi.trends, enabled: tab === "operations" });
  const risks = useQuery({ queryKey: ["admin-risks"], queryFn: adminApi.risks, enabled: tab === "safety" });
  const reports = useQuery({ queryKey: ["admin-reports"], queryFn: adminApi.reports, enabled: tab === "safety" });
  const moderation = useQuery({ queryKey: ["admin-moderation"], queryFn: adminApi.moderation, enabled: tab === "safety" });
  const users = useQuery({ queryKey: ["admin-users"], queryFn: adminApi.users, enabled: tab === "operations" });
  const words = useQuery({ queryKey: ["admin-words"], queryFn: adminApi.words, enabled: tab === "operations" });
  const articles = useQuery({ queryKey: ["admin-articles"], queryFn: adminApi.articles, enabled: tab === "operations" });
  const auditLogs = useQuery({ queryKey: ["admin-audit-logs"], queryFn: adminApi.auditLogs, enabled: tab === "operations" });
  const timeline = useQuery({
    queryKey: ["admin-risk-timeline", selectedRiskId],
    queryFn: () => adminApi.riskTimeline(selectedRiskId!),
    enabled: selectedRiskId != null,
  });
  const refreshAudit = () => qc.invalidateQueries({ queryKey: ["admin-audit-logs"] });

  const refreshSafety = () => {
    qc.invalidateQueries({ queryKey: ["admin-overview"] });
    qc.invalidateQueries({ queryKey: ["admin-risks"] });
    qc.invalidateQueries({ queryKey: ["admin-reports"] });
    qc.invalidateQueries({ queryKey: ["admin-moderation"] });
    qc.invalidateQueries({ queryKey: ["admin-audit-logs"] });
    if (selectedRiskId) qc.invalidateQueries({ queryKey: ["admin-risk-timeline", selectedRiskId] });
  };
  const handleRisk = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Parameters<typeof adminApi.handleRisk>[1] }) => adminApi.handleRisk(id, payload),
    onSuccess: refreshSafety,
  });
  const handleReport = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) => adminApi.handleReport(id, action),
    onSuccess: refreshSafety,
  });
  const moderate = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "approve" | "hide" }) => adminApi.moderate(id, action),
    onSuccess: refreshSafety,
  });
  const updateRole = useMutation({
    mutationFn: ({ id, role }: { id: number; role: "student" | "admin" }) => adminApi.updateRole(id, role),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-users"] }); refreshAudit(); },
  });
  const updateArticle = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "已发布" | "草稿" }) => adminApi.updateArticleStatus(id, status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-articles"] }); refreshAudit(); },
  });
  const addWord = useMutation({
    mutationFn: (word: string) => adminApi.addWord(word),
    onSuccess: () => {
      setNewWord("");
      qc.invalidateQueries({ queryKey: ["admin-words"] });
      refreshAudit();
    },
  });
  const toggleWord = useMutation({
    mutationFn: adminApi.toggleWord,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-words"] }); refreshAudit(); },
  });
  const removeWord = useMutation({
    mutationFn: adminApi.removeWord,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-words"] }); refreshAudit(); },
  });

  const stats = [
    { label: "平台用户", value: overview.data?.total_users ?? "--", detail: "累计注册", icon: Users },
    { label: "今日活跃", value: overview.data?.active_users_1d ?? "--", detail: `7 日活跃 ${overview.data?.active_users_7d ?? "--"}`, icon: Activity },
    { label: "平均情绪", value: overview.data?.avg_mood_7d ?? "--", detail: "近 7 日 / 10 分", icon: Gauge },
    { label: "开放风险案例", value: overview.data?.pending_risks ?? "--", detail: `紧急 ${overview.data?.critical_risks ?? 0} · 超时 ${overview.data?.overdue_risks ?? 0}`, icon: ShieldAlert, tone: "danger" },
  ];
  const selectedRisk = risks.data?.find((item) => item.id === selectedRiskId) ?? null;
  const runRiskAction = (status: "assigned" | "contacted" | "follow_up" | "resolved" | "false_positive") => {
    if (!selectedRisk) return;
    handleRisk.mutate({
      id: selectedRisk.id,
      payload: {
        status,
        expected_version: selectedRisk.version,
        note: riskNote,
        next_follow_up_at: status === "follow_up" && followUpAt ? new Date(followUpAt).toISOString() : undefined,
      },
    });
  };
  const trendData = trends.data ?? [];
  const chartOption = {
    animation: false,
    color: ["#21766d", "#5269a8", "#c15f59"],
    tooltip: { trigger: "axis" },
    legend: { top: 0, right: 0, textStyle: { color: "#67736f", fontSize: 11 } },
    grid: { top: 38, right: 34, bottom: 28, left: 34, containLabel: true },
    xAxis: { type: "category", data: trendData.map((item) => item.date.slice(5)), axisTick: { show: false }, axisLine: { lineStyle: { color: "#dce3df" } } },
    yAxis: [
      { type: "value", min: 0, max: 10, splitLine: { lineStyle: { color: "#edf0ee" } } },
      { type: "value", minInterval: 1, splitLine: { show: false } },
    ],
    series: [
      { name: "平均情绪", type: "line", smooth: true, connectNulls: true, symbolSize: 5, data: trendData.map((item) => item.avg_mood) },
      { name: "咨询量", type: "bar", yAxisIndex: 1, barMaxWidth: 16, data: trendData.map((item) => item.consultations) },
      { name: "风险事件", type: "line", yAxisIndex: 1, symbolSize: 5, data: trendData.map((item) => item.risk_events) },
    ],
  };

  return (
    <section className="page admin-page">
      <div className="stats-grid">
        {stats.map(({ label, value, detail, icon: Icon, tone }) => (
          <div className={`stat-card ${tone ?? ""}`} key={label}>
            <div className="stat-label"><Icon size={18} /><span>{label}</span></div>
            <strong>{value}</strong><small>{detail}</small>
          </div>
        ))}
      </div>

      <div className="admin-tabs" role="tablist" aria-label="后台视图">
        <button className={tab === "safety" ? "active" : ""} onClick={() => setTab("safety")}><ShieldAlert size={16} />安全处置</button>
        <button className={tab === "operations" ? "active" : ""} onClick={() => setTab("operations")}><Settings2 size={16} />运营管理</button>
      </div>

      {tab === "safety" ? (
        <>
          <section className="workspace-section">
            <div className="section-heading">
              <div><span className="section-kicker">Safety queue</span><h2>风险干预队列</h2></div>
              <span className="count-badge">{risks.data?.length ?? 0} 待处理</span>
            </div>
            <div className="data-table risk-table">
              <div className="data-row data-head"><span>风险</span><span>学生</span><span>识别依据</span><span>时间</span><span>处置</span></div>
              {risks.data?.map((item) => (
                <div className="data-row" key={item.id}>
                  <span><span className={`risk-badge ${item.level}`}>{riskLabels[item.level]} · {item.score}</span><small>{item.event_type === "mood_trend" ? "情绪趋势" : "咨询对话"}</small></span>
                  <span><strong>{item.nickname}</strong><small>用户 #{item.user_id}</small></span>
                  <span className="excerpt">{item.excerpt}<small>{item.signals}{item.model_reason ? ` · 模型复核：${item.model_reason}` : ""}</small></span>
                  <span className={item.overdue ? "deadline overdue" : "deadline"}>
                    {item.due_at ? `SLA ${item.due_at.slice(5, 16).replace("T", " ")}` : "未设置 SLA"}
                    <small>{item.assignee_name ? `${item.assignee_name} · ${item.status}` : `未分派 · ${item.status}`}</small>
                  </span>
                  <span className="row-actions">
                    {item.status === "pending" && <button className="secondary-button" onClick={() => handleRisk.mutate({ id: item.id, payload: { status: "assigned", expected_version: item.version } })}>领取</button>}
                    {item.status === "assigned" && <button className="secondary-button" onClick={() => handleRisk.mutate({ id: item.id, payload: { status: "contacted", expected_version: item.version } })}>已联系</button>}
                    <button className="icon-button" title="查看处置详情" aria-label="查看处置详情" onClick={() => { setSelectedRiskId(item.id); setRiskNote(""); }}><History size={17} /></button>
                  </span>
                </div>
              ))}
              {!risks.isLoading && !risks.data?.length && <div className="empty-state"><CheckCircle2 size={24} /><span>当前没有待处理风险事件</span></div>}
            </div>
            {selectedRisk && (
              <div className="case-workbench">
                <div className="case-workbench-head">
                  <div><span className={`risk-badge ${selectedRisk.level}`}>{riskLabels[selectedRisk.level]} · {selectedRisk.status}</span><strong>案例 #{selectedRisk.id} · {selectedRisk.nickname}</strong></div>
                  <span><Clock3 size={14} />{selectedRisk.due_at ? `SLA ${selectedRisk.due_at.slice(0, 16).replace("T", " ")}` : "未设置 SLA"}</span>
                </div>
                <div className="case-workbench-grid">
                  <div className="case-actions-panel">
                    <label>处置说明<textarea value={riskNote} onChange={(event) => setRiskNote(event.target.value)} maxLength={512} placeholder="记录联系结果、判断依据或后续安排" /></label>
                    <label>下次随访<input type="datetime-local" value={followUpAt} onChange={(event) => setFollowUpAt(event.target.value)} /></label>
                    <div className="row-actions">
                      {selectedRisk.status === "contacted" && <button className="secondary-button" disabled={!followUpAt} onClick={() => runRiskAction("follow_up")}>安排随访</button>}
                      {selectedRisk.status === "follow_up" && <button className="secondary-button" onClick={() => runRiskAction("contacted")}>完成随访</button>}
                      <button className="primary-button" disabled={riskNote.trim().length < 2} onClick={() => runRiskAction("resolved")}><CheckCircle2 size={15} />结案</button>
                      <button className="text-button" disabled={riskNote.trim().length < 2} onClick={() => runRiskAction("false_positive")}>标记误报</button>
                    </div>
                    {handleRisk.error && <p className="form-error">{handleRisk.error.message}</p>}
                  </div>
                  <div className="case-timeline">
                    <strong>处置时间线</strong>
                    {timeline.data?.map((action) => (
                      <div key={action.id}><span>{action.actor_name} · {action.action}</span><small>{action.created_at.slice(0, 16).replace("T", " ")}</small><p>{action.note || `${action.from_status} → ${action.to_status}`}</p></div>
                    ))}
                    {!timeline.data?.length && <p className="muted">暂无处置记录</p>}
                  </div>
                </div>
              </div>
            )}
          </section>

          <div className="admin-columns">
            <section className="workspace-section">
              <div className="section-heading"><div><span className="section-kicker">Reports</span><h2>社区举报</h2></div></div>
              <div className="queue-list">
                {reports.data?.map((item) => (
                  <article className="queue-item" key={item.id}>
                    <AlertTriangle size={18} />
                    <div><strong>{item.reason}</strong><p>{item.detail || `讨论 #${item.target_id}`}</p></div>
                    <div className="row-actions">
                      <button className="secondary-button" onClick={() => handleReport.mutate({ id: item.id, action: "dismiss" })}>驳回</button>
                      <button className="danger-button" onClick={() => handleReport.mutate({ id: item.id, action: "hide" })}>隐藏</button>
                    </div>
                  </article>
                ))}
                {!reports.data?.length && <p className="muted">暂无待处理举报</p>}
              </div>
            </section>

            <section className="workspace-section">
              <div className="section-heading"><div><span className="section-kicker">Moderation</span><h2>内容审核</h2></div></div>
              <div className="queue-list">
                {moderation.data?.map((item) => (
                  <article className="queue-item" key={item.id}>
                    <FileWarning size={18} />
                    <div><strong>{item.title}</strong><p>{item.moderation_reason}</p></div>
                    <div className="row-actions">
                      <button className="secondary-button" onClick={() => moderate.mutate({ id: item.id, action: "approve" })}>通过</button>
                      <button className="danger-button" onClick={() => moderate.mutate({ id: item.id, action: "hide" })}>隐藏</button>
                    </div>
                  </article>
                ))}
                {!moderation.data?.length && <p className="muted">暂无待审核内容</p>}
              </div>
            </section>
          </div>
        </>
      ) : (
        <>
          <section className="workspace-section operations-chart">
            <div className="section-heading"><div><span className="section-kicker">14-day trend</span><h2>平台运营趋势</h2></div><span className="count-badge">咨询 {overview.data?.consultations_7d ?? 0} · 发帖 {overview.data?.community_posts_7d ?? 0}</span></div>
            <ReactEChartsCore echarts={echarts} option={chartOption} style={{ height: 310 }} notMerge lazyUpdate />
          </section>

          <div className="operations-grid">
            <section className="workspace-section management-section">
              <div className="section-heading"><div><span className="section-kicker">RBAC</span><h2>用户与角色</h2></div><UserCog size={18} /></div>
              <div className="management-list">
                {users.data?.map((item) => (
                  <div className="management-row" key={item.id}>
                    <div><strong>{item.nickname || `用户 ${item.id}`}</strong><small>{item.phone || "未绑定手机"}</small></div>
                    <select aria-label={`设置 ${item.nickname} 的角色`} value={item.role} onChange={(event) => updateRole.mutate({ id: item.id, role: event.target.value as "student" | "admin" })}>
                      <option value="student">普通用户</option><option value="admin">管理员</option>
                    </select>
                  </div>
                ))}
              </div>
            </section>

            <section className="workspace-section management-section">
              <div className="section-heading"><div><span className="section-kicker">Publishing</span><h2>文章状态</h2></div><FileText size={18} /></div>
              <div className="management-list">
                {articles.data?.map((item) => (
                  <div className="management-row" key={item.id}>
                    <div><strong>{item.title}</strong><small>{item.category} · 阅读 {item.read_count}</small></div>
                    <select aria-label={`设置 ${item.title} 的状态`} value={item.status} onChange={(event) => updateArticle.mutate({ id: item.id, status: event.target.value as "已发布" | "草稿" })}>
                      <option value="已发布">已发布</option><option value="草稿">草稿</option>
                    </select>
                  </div>
                ))}
              </div>
            </section>

            <section className="workspace-section management-section sensitive-section">
              <div className="section-heading"><div><span className="section-kicker">Moderation rules</span><h2>敏感词规则</h2></div><ShieldAlert size={18} /></div>
              <form className="word-form" onSubmit={(event) => { event.preventDefault(); const word = newWord.trim(); if (word) addWord.mutate(word); }}>
                <input value={newWord} onChange={(event) => setNewWord(event.target.value)} maxLength={64} placeholder="添加敏感词" aria-label="新增敏感词" />
                <button type="submit" className="primary-button" disabled={!newWord.trim() || addWord.isPending}>添加</button>
              </form>
              <div className="word-list">
                {words.data?.map((item) => (
                  <div className="word-row" key={item.id}>
                    <button className={`status-toggle ${item.enabled ? "enabled" : ""}`} aria-pressed={item.enabled} onClick={() => toggleWord.mutate(item.id)}>{item.enabled ? "启用" : "停用"}</button>
                    <span>{item.word}</span><small>{item.category}</small>
                    <button className="icon-button" title="删除敏感词" aria-label={`删除敏感词 ${item.word}`} onClick={() => removeWord.mutate(item.id)}><Trash2 size={15} /></button>
                  </div>
                ))}
              </div>
            </section>
          </div>
          <section className="workspace-section audit-section">
            <div className="section-heading"><div><span className="section-kicker">Audit trail</span><h2>管理操作审计</h2></div><History size={18} /></div>
            <div className="audit-list">
              {auditLogs.data?.map((item) => (
                <div className="audit-row" key={item.id}>
                  <span>{item.actor_name}</span>
                  <strong>{item.action}</strong>
                  <span>{item.target_type} #{item.target_id}</span>
                  <small>{item.created_at.slice(0, 16).replace("T", " ")} · {item.request_id.slice(0, 12)}</small>
                </div>
              ))}
              {!auditLogs.data?.length && <p className="muted">尚无管理操作记录</p>}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
