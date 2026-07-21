import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, BookOpenText, CalendarDays, ExternalLink, LoaderCircle, MessageSquareText, Search, Send, ShieldCheck, Sparkles, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";
import { articlesApi, contentApi, knowledgeApi, recommendationsApi } from "../api/queries";
import type { RecommendationEmotion } from "../api/queries";
import { useAuthStore } from "../store/auth";
import type { Article, KnowledgeSource } from "../types";

const schema = z.object({
  title: z.string().min(2, "请输入标题"),
  category: z.string().min(1, "请输入分类"),
  summary: z.string().min(10, "摘要至少 10 个字"),
  content: z.string().min(20, "正文至少 20 个字"),
  status: z.string(),
});

type FormValues = z.infer<typeof schema>;
type ContentView = "conversations" | "articles";
type SearchFilters = { keyword: string; period: string };

const initialFilters: Record<ContentView, SearchFilters> = {
  conversations: { keyword: "", period: "all" },
  articles: { keyword: "", period: "all" },
};

const periodOptions = [
  { value: "all", label: "全部时间" },
  { value: "7d", label: "最近 7 天" },
  { value: "30d", label: "最近 30 天" },
  { value: "90d", label: "最近 90 天" },
  { value: "365d", label: "最近一年" },
];

const recommendationEmotions: RecommendationEmotion[] = ["焦虑", "低落", "烦躁", "平稳", "愉悦"];

const sourceTypeCopy: Record<KnowledgeSource["source_type"], string> = {
  reviewed_knowledge: "审核知识库",
  own_history: "我的历史倾听",
  public_conversation: "匿名公开经验",
};

function displayDate(value: string | null | undefined) {
  if (!value) return "日期未知";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}

function SourceCard({ source, index }: { source: KnowledgeSource; index?: number }) {
  return (
    <span className={`knowledge-source-card ${source.source_type}`}>
      {index != null && <b>[{index + 1}]</b>}
      <strong>{source.title}</strong>
      <small>{sourceTypeCopy[source.source_type]} · {source.source || "平台资料"}</small>
    </span>
  );
}

export default function ArticlesPage() {
  const qc = useQueryClient();
  const token = useAuthStore((state) => state.token);
  const role = useAuthStore((state) => state.user?.role);
  const [searchParams, setSearchParams] = useSearchParams();
  const view: ContentView = searchParams.get("view") === "conversations" ? "conversations" : "articles";
  const [selected, setSelected] = useState<Article | null>(null);
  const [question, setQuestion] = useState("");
  const [draftFilters, setDraftFilters] = useState(initialFilters);
  const [appliedFilters, setAppliedFilters] = useState(initialFilters);
  const currentDraft = draftFilters[view];
  const currentApplied = appliedFilters[view];

  const articles = useQuery({
    queryKey: ["articles", currentApplied.keyword, currentApplied.period],
    queryFn: () => articlesApi.list(currentApplied),
    enabled: view === "articles",
  });
  const conversations = useQuery({
    queryKey: ["public-conversations", currentApplied.keyword, currentApplied.period],
    queryFn: () => contentApi.publicConversations(currentApplied),
    enabled: view === "conversations",
  });
  const recommended = useQuery({ queryKey: ["recommendations"], queryFn: recommendationsApi.articles, enabled: Boolean(token) && view === "articles" });
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { status: "已发布" } });
  const save = useMutation({
    mutationFn: articlesApi.create,
    onSuccess: () => { form.reset({ status: "已发布" }); qc.invalidateQueries({ queryKey: ["articles"] }); },
  });
  const knowledge = useMutation({ mutationFn: knowledgeApi.ask });
  const saveRecommendationEmotion = useMutation({
    mutationFn: recommendationsApi.setPreference,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recommendations"] }),
  });
  const reasonById = useMemo(() => new Map(recommended.data?.items.map((item) => [item.article.id, item.reason]) ?? []), [recommended.data]);
  const displayedArticles = useMemo(() => {
    const rows = [...(articles.data ?? [])];
    const rankById = new Map(recommended.data?.items.map((item, index) => [item.article.id, index]) ?? []);
    return rows.sort((left, right) => (rankById.get(left.id) ?? Number.MAX_SAFE_INTEGER) - (rankById.get(right.id) ?? Number.MAX_SAFE_INTEGER));
  }, [articles.data, recommended.data]);

  const switchView = (nextView: ContentView) => {
    setSelected(null);
    setSearchParams(nextView === "articles" ? {} : { view: nextView });
  };

  const updateDraft = (change: Partial<SearchFilters>) => {
    setDraftFilters((current) => ({ ...current, [view]: { ...current[view], ...change } }));
  };

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setAppliedFilters((current) => ({ ...current, [view]: { ...currentDraft, keyword: currentDraft.keyword.trim() } }));
  };

  const resultCount = view === "articles" ? articles.data?.length : conversations.data?.length;
  const isLoading = view === "articles" ? articles.isLoading : conversations.isLoading;
  const sourceSummary = knowledge.data?.source_summary;

  return (
    <section className="page articles-page">
      <div className="content-view-tabs" role="tablist" aria-label="心理内容类型">
        <button type="button" role="tab" aria-selected={view === "conversations"} className={view === "conversations" ? "active" : ""} onClick={() => switchView("conversations")}>
          <MessageSquareText size={17} />公开倾听
        </button>
        <button type="button" role="tab" aria-selected={view === "articles"} className={view === "articles" ? "active" : ""} onClick={() => switchView("articles")}>
          <BookOpenText size={17} />心理文章
        </button>
      </div>

      <form className="content-search-panel" onSubmit={submitSearch}>
        <label className="content-keyword-field">
          <Search size={18} />
          <input
            value={currentDraft.keyword}
            onChange={(event) => updateDraft({ keyword: event.target.value })}
            placeholder={view === "conversations" ? "搜索公开对话标题" : "搜索心理文章标题"}
            aria-label={view === "conversations" ? "公开对话标题关键词" : "心理文章标题关键词"}
          />
        </label>
        <label className="content-period-field">
          <CalendarDays size={17} />
          <select value={currentDraft.period} onChange={(event) => updateDraft({ period: event.target.value })} aria-label="时间范围">
            {periodOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <button className="content-search-submit" type="submit"><Search size={16} />搜索</button>
      </form>

      <div className="content-results-heading">
        <div>
          <span className="section-kicker">{view === "conversations" ? "Public conversations" : "Reading library"}</span>
          <h2>{view === "conversations" ? "公开倾听记录" : "心理文章"}</h2>
        </div>
        <span className="count-badge">{isLoading ? "检索中" : `${resultCount ?? 0} 条结果`}</span>
      </div>

      {view === "conversations" ? (
        <>
          <div className="privacy-result-note"><ShieldCheck size={16} /><span>仅展示用户主动设为公开的倾听记录，私密对话不会进入搜索结果。</span></div>
          <div className="public-conversation-grid">
            {conversations.data?.map((item) => (
              <article className="public-conversation-card" key={item.id}>
                <div className="article-card-top"><span className="topic-tag">{item.emotion_tag || "倾听记录"}</span><span>{displayDate(item.created_at)}</span></div>
                <h3>{item.title || "未命名对话"}</h3>
                <p>{item.summary || "这段公开倾听暂时没有生成摘要。"}</p>
              </article>
            ))}
          </div>
          {!isLoading && !conversations.data?.length && <div className="content-empty"><MessageSquareText size={24} /><strong>没有找到匹配的公开对话</strong><span>可以调整关键词或时间范围。</span></div>}
        </>
      ) : (
        <>
          <section className="knowledge-band">
            <div>
              <span className="section-kicker">Grounded answer</span>
              <h2>可信心理知识问答</h2>
              <p>回答会区分审核知识库、你的历史倾听、匿名公开经验；资料不足时会明确拒答。</p>
            </div>
            <form onSubmit={(event) => { event.preventDefault(); if (question.trim()) knowledge.mutate(question.trim()); }}>
              <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：考试焦虑到睡不着可以怎么做？" disabled={knowledge.isPending} />
              <button className="icon-button" aria-label={knowledge.isPending ? "正在生成回答" : "提交问题"} disabled={knowledge.isPending}>{knowledge.isPending ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}</button>
            </form>
            {knowledge.isPending ? (
              <div className="knowledge-generating" role="status" aria-live="polite">
                <LoaderCircle className="spin" size={22} />
                <div><strong>正在生成有依据的回答</strong><span>正在匹配审核资料、你的相关记录和匿名公开经验。</span></div>
                <i /><i /><i />
              </div>
            ) : knowledge.data ? (
              <div className={`knowledge-answer ${knowledge.data.grounded ? "" : "refused"}`}>
                <div className="knowledge-source-summary">
                  <span>审核资料 {sourceSummary?.reviewed_knowledge ?? 0}</span>
                  <span>我的历史 {sourceSummary?.own_history ?? 0}</span>
                  <span>公开经验 {sourceSummary?.public_conversations ?? 0}</span>
                </div>
                {!knowledge.data.grounded && <strong className="knowledge-refusal">资料不足，已安全拒答</strong>}
                <p>{knowledge.data.answer.replace(/\*\*/g, "")}</p>
                {knowledge.data.citations.length > 0 && (
                  <div className="knowledge-source-list">
                    {knowledge.data.citations.map((citation, index) => <SourceCard key={citation.id} source={citation} index={index} />)}
                  </div>
                )}
                {knowledge.data.context_sources.length > 0 && (
                  <div className="knowledge-source-list context">
                    {knowledge.data.context_sources.map((source) => <SourceCard key={source.id} source={source} />)}
                  </div>
                )}
              </div>
            ) : null}
            {knowledge.error && <p className="form-error">{knowledge.error.message}</p>}
          </section>

          {token && recommended.data ? (
            <div className="recommendation-banner">
              <div className="recommendation-banner-title"><Sparkles size={18} /><strong>心理画像推荐</strong></div>
              <div className="profile-explain">
                <span>情绪主线：{recommended.data.profile.dominant_emotions.join("、") || recommended.data.profile.emotion}</span>
                <span>压力来源：{recommended.data.profile.stressors.join("、") || "尚未识别"}</span>
                <span>支持偏好：{recommended.data.profile.coping_preferences.join("、") || "尚未识别"}</span>
              </div>
              <label className="recommendation-state-control">
                <span className="sr-only">选择推荐状态</span>
                <select
                  aria-label="推荐状态"
                  value={saveRecommendationEmotion.isPending ? saveRecommendationEmotion.variables : recommended.data.profile.emotion}
                  disabled={saveRecommendationEmotion.isPending}
                  onChange={(event) => saveRecommendationEmotion.mutate(event.target.value as RecommendationEmotion)}
                >
                  {recommendationEmotions.map((emotion) => <option key={emotion} value={emotion}>{emotion}</option>)}
                </select>
              </label>
              <small role="status" aria-live="polite">
                {saveRecommendationEmotion.isPending ? "正在保存" : saveRecommendationEmotion.error ? saveRecommendationEmotion.error.message : recommended.data.profile.is_manual ? "已使用手动状态" : "自动画像推荐"}
              </small>
            </div>
          ) : null}

          <div className="article-grid">
            {displayedArticles.map((item) => (
              <article className="article-card" key={item.id}>
                <div className="article-card-top"><span className="topic-tag">{item.category || "心理科普"}</span>{reasonById.has(item.id) && <span className="recommended-mark"><Sparkles size={13} /> 推荐</span>}</div>
                <h2>{item.title}</h2>
                <p>{item.summary || item.content.slice(0, 100)}</p>
                <div className="article-meta"><span>{item.source_name || item.author || "校心理中心"}</span><span>{displayDate(item.source_url ? item.published_at : item.created_at)}</span></div>
                {item.source_url ? (
                  <a className="article-open-link" href={item.source_url} target="_blank" rel="noreferrer">阅读原文<ExternalLink size={14} /></a>
                ) : (
                  <button className="article-open-link" type="button" onClick={() => setSelected(item)}>查看内容<BookOpen size={14} /></button>
                )}
                {reasonById.get(item.id) && <small className="recommendation-reason">{reasonById.get(item.id)}</small>}
              </article>
            ))}
          </div>
          {!isLoading && !articles.data?.length && <div className="content-empty"><BookOpenText size={24} /><strong>没有找到匹配的心理文章</strong><span>可以调整关键词或时间范围。</span></div>}

          {role === "admin" && (
            <section className="workspace-section editor-section">
              <div className="section-heading"><div><span className="section-kicker">CMS</span><h2>发布心理内容</h2></div></div>
              <form className="editor-grid" onSubmit={form.handleSubmit((values) => save.mutate(values))}>
                <input placeholder="文章标题" {...form.register("title")} />
                <input placeholder="分类，如：压力管理" {...form.register("category")} />
                <input className="wide" placeholder="摘要" {...form.register("summary")} />
                <textarea className="wide" placeholder="正文" {...form.register("content")} />
                <select {...form.register("status")}><option>已发布</option><option>草稿</option></select>
                <button disabled={save.isPending}>发布内容</button>
                <p className="form-error wide">{Object.values(form.formState.errors)[0]?.message || save.error?.message}</p>
              </form>
            </section>
          )}
        </>
      )}

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <article className="article-modal" onClick={(event) => event.stopPropagation()}>
            <button className="icon-button modal-close" title="关闭" aria-label="关闭" onClick={() => setSelected(null)}><X size={19} /></button>
            <span className="topic-tag">{selected.category}</span><h1>{selected.title}</h1><p className="article-lead">{selected.summary}</p>
            <div className="article-byline"><BookOpen size={16} /> {selected.author || "校心理中心"} · {selected.read_count} 阅读</div>
            <div className="article-content">{selected.content}</div>
          </article>
        </div>
      )}
    </section>
  );
}
