import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, Brain, Check, Clock3, Globe2, LockKeyhole, MessageSquarePlus, Pencil, Pin, PinOff, RefreshCw, Search, Send, ShieldCheck, Sparkles, Trash2, UserRound, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { authApi, consultApi } from "../api/queries";
import RequireLogin from "../components/RequireLogin";
import { useChatStore } from "../store/chat";
import type { ChatResponse, RiskLevel } from "../types";

const riskCopy: Record<RiskLevel, string> = {
  low: "当前对话未发现明显风险信号",
  medium: "检测到需要关注的情绪信号",
  high: "检测到较高风险，请优先联系现实中的支持者",
  critical: "检测到紧急风险，请立即寻求线下帮助",
};

type OptimisticMessage = {
  id: string;
  conversationId: string;
  content: string;
  visibility: string;
  requestKey: string;
  status: "sending" | "failed";
};

export default function ConsultPage() {
  return <RequireLogin><ConsultContent /></RequireLogin>;
}

function ConsultContent() {
  const qc = useQueryClient();
  const { conversationId, setConversationId, newConversation } = useChatStore();
  const [message, setMessage] = useState("");
  const [visibility, setVisibility] = useState("私人");
  const [optimisticMessage, setOptimisticMessage] = useState<OptimisticMessage | null>(null);
  const [lastAssessment, setLastAssessment] = useState<ChatResponse | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState("");
  const [deletingConversationId, setDeletingConversationId] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const conversations = useQuery({
    queryKey: ["conversations", debouncedSearch],
    queryFn: () => consultApi.conversations(debouncedSearch),
  });
  const profile = useQuery({ queryKey: ["my-profile"], queryFn: authApi.profile });
  const history = useQuery({
    queryKey: ["history", conversationId],
    queryFn: () => consultApi.history(conversationId),
    enabled: Boolean(conversationId),
  });
  const chat = useMutation({
    mutationFn: consultApi.chat,
    onSuccess: async (data, variables) => {
      setLastAssessment(data);
      try {
        await qc.invalidateQueries({ queryKey: ["history", variables.conversation_id] });
      } finally {
        setOptimisticMessage((current) => current?.requestKey === variables.request_key ? null : current);
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["conversations"] }),
        qc.invalidateQueries({ queryKey: ["public-conversations"] }),
        qc.invalidateQueries({ queryKey: ["my-profile"] }),
      ]);
    },
    onError: (_error, variables) => {
      setOptimisticMessage((current) => current && current.requestKey === variables.request_key ? { ...current, status: "failed" } : current);
    },
  });
  const updateConversation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { title?: string; pinned?: boolean } }) =>
      consultApi.updateConversation(id, payload),
    onSuccess: () => {
      setEditingConversationId(null);
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.invalidateQueries({ queryKey: ["public-conversations"] });
    },
  });
  const updateVisibility = useMutation({
    mutationFn: ({ id, visibility: nextVisibility }: { id: string; visibility: "公开" | "私人" }) =>
      consultApi.setConversationVisibility(id, nextVisibility),
    onSuccess: (data) => {
      if (data.conversation_id === conversationId) setVisibility(data.visibility);
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.invalidateQueries({ queryKey: ["public-conversations"] });
    },
  });
  const removeConversation = useMutation({
    mutationFn: consultApi.removeConversation,
    onSuccess: (_, deletedId) => {
      setDeletingConversationId(null);
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.invalidateQueries({ queryKey: ["public-conversations"] });
      qc.removeQueries({ queryKey: ["history", deletedId] });
      if (deletedId === conversationId) {
        newConversation();
        setLastAssessment(null);
      }
    },
  });

  useEffect(() => {
    if (!conversationId) newConversation();
  }, [conversationId, newConversation]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchQuery.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  useEffect(() => {
    const current = conversations.data?.find((item) => item.conversation_id === conversationId);
    if (current) setVisibility(current.visibility);
  }, [conversationId, conversations.data]);

  useEffect(() => {
    const container = messagesRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [history.data?.length, optimisticMessage, chat.isPending]);

  const rows = useMemo(() => history.data ?? [], [history.data]);
  const submit = () => {
    const content = message.trim();
    if (content && !chat.isPending) {
      const requestKey = crypto.randomUUID();
      setOptimisticMessage({
        id: requestKey,
        conversationId,
        content,
        visibility,
        requestKey,
        status: "sending",
      });
      setMessage("");
      chat.mutate({ conversation_id: conversationId, message: content, visibility, request_key: requestKey });
    }
  };

  const retryOptimisticMessage = () => {
    if (!optimisticMessage || chat.isPending) return;
    setOptimisticMessage({ ...optimisticMessage, status: "sending" });
    chat.mutate({
      conversation_id: optimisticMessage.conversationId,
      message: optimisticMessage.content,
      visibility: optimisticMessage.visibility,
      request_key: optimisticMessage.requestKey,
    });
  };

  const visibleOptimisticMessage = optimisticMessage?.conversationId === conversationId ? optimisticMessage : null;

  return (
    <section className="page consult-workspace">
      <aside className="conversation-sidebar">
        <div className="section-heading compact">
          <h2>最近对话</h2>
          <div className="conversation-header-actions">
            <button
              type="button"
              className={`icon-button subtle conversation-search-toggle ${searchOpen ? "active" : ""}`}
              title={searchOpen ? "收起搜索" : "搜索聊天记录"}
              aria-label={searchOpen ? "收起聊天记录搜索" : "搜索聊天记录"}
              aria-expanded={searchOpen}
              onClick={() => {
                setSearchOpen((open) => {
                  if (open) setSearchQuery("");
                  return !open;
                });
              }}
            >
              <Search size={18} />
            </button>
            <button type="button" className="icon-button" title="创建新对话" aria-label="创建新对话" onClick={() => { newConversation(); setVisibility("私人"); setLastAssessment(null); }}>
              <MessageSquarePlus size={18} />
            </button>
          </div>
        </div>
        {searchOpen && (
          <label className="conversation-search">
            <Search size={15} aria-hidden="true" />
            <input
              ref={searchInputRef}
              type="search"
              value={searchQuery}
              maxLength={100}
              aria-label="搜索我的聊天记录"
              placeholder="搜索聊天内容"
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            {searchQuery && (
              <button type="button" aria-label="清空搜索" title="清空搜索" onClick={() => setSearchQuery("")}>
                <X size={14} />
              </button>
            )}
          </label>
        )}
        <div className="conversation-list">
          {conversations.isLoading && <p className="empty-copy">正在搜索...</p>}
          {conversations.data?.map((item) => (
            <div
              key={item.conversation_id}
              className={`conversation-item ${item.conversation_id === conversationId ? "active" : ""} ${deletingConversationId === item.conversation_id ? "confirming" : ""}`}
            >
              {editingConversationId === item.conversation_id ? (
                <form
                  className="conversation-rename"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const title = conversationTitle.trim();
                    if (title) updateConversation.mutate({ id: item.conversation_id, payload: { title } });
                  }}
                >
                  <input
                    autoFocus
                    value={conversationTitle}
                    maxLength={80}
                    aria-label={`重命名对话 ${item.title}`}
                    onChange={(event) => setConversationTitle(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") setEditingConversationId(null);
                    }}
                  />
                  <button type="submit" disabled={!conversationTitle.trim() || updateConversation.isPending} title="保存名称" aria-label="保存对话名称"><Check size={14} /></button>
                  <button type="button" title="取消重命名" aria-label="取消重命名" onClick={() => setEditingConversationId(null)}><X size={14} /></button>
                </form>
              ) : (
                <>
                  <button
                    type="button"
                    className="conversation-open"
                    aria-label={`打开对话 ${item.title}`}
                    onClick={() => { setConversationId(item.conversation_id); setVisibility(item.visibility); setLastAssessment(null); }}
                  >
                    <span className="conversation-title">{item.title}</span>
                    <span className="conversation-meta">
                      <span>{item.emotion_tag || "未标记"} · {item.visibility === "公开" ? "公开" : "私密"}</span>
                      {item.risk_level !== "low" && <span className={`risk-dot ${item.risk_level}`} title={riskCopy[item.risk_level]} />}
                    </span>
                  </button>
                  <div className="conversation-actions" aria-label={`${item.title} 的操作`}>
                    <button
                      type="button"
                      className={item.visibility === "公开" ? "public" : ""}
                      aria-label={item.visibility === "公开" ? `设为私密 ${item.title}` : `设为公开 ${item.title}`}
                      title={item.visibility === "公开" ? "改为私密" : "改为公开"}
                      disabled={updateVisibility.isPending}
                      onClick={() => updateVisibility.mutate({ id: item.conversation_id, visibility: item.visibility === "公开" ? "私人" : "公开" })}
                    >{item.visibility === "公开" ? <Globe2 size={13} /> : <LockKeyhole size={13} />}</button>
                    <button
                      type="button"
                      className={item.pinned ? "pinned" : ""}
                      aria-label={item.pinned ? `取消置顶 ${item.title}` : `置顶 ${item.title}`}
                      aria-pressed={item.pinned}
                      title={item.pinned ? "取消置顶" : "置顶"}
                      disabled={updateConversation.isPending}
                      onClick={() => updateConversation.mutate({ id: item.conversation_id, payload: { pinned: !item.pinned } })}
                    >{item.pinned ? <PinOff size={13} /> : <Pin size={13} />}</button>
                    <button
                      type="button"
                      aria-label={`重命名 ${item.title}`}
                      title="重命名"
                      onClick={() => { setEditingConversationId(item.conversation_id); setConversationTitle(item.title); setDeletingConversationId(null); }}
                    ><Pencil size={13} /></button>
                    <button
                      type="button"
                      className="delete"
                      aria-label={`删除 ${item.title}`}
                      title="删除"
                      onClick={() => { setDeletingConversationId(item.conversation_id); setEditingConversationId(null); }}
                    ><Trash2 size={13} /></button>
                  </div>
                </>
              )}
              {deletingConversationId === item.conversation_id && (
                <div className="conversation-delete-confirm" role="alert">
                  <span>删除后无法恢复</span>
                  <button type="button" onClick={() => setDeletingConversationId(null)}>取消</button>
                  <button type="button" className="confirm" disabled={removeConversation.isPending} onClick={() => removeConversation.mutate(item.conversation_id)}>确认删除</button>
                </div>
              )}
            </div>
          ))}
          {!conversations.isLoading && !conversations.data?.length && (
            <p className="empty-copy">{debouncedSearch ? "没有找到相关对话" : "还没有对话记录"}</p>
          )}
        </div>
        {profile.data && (
          <div className="profile-summary"><Brain size={16} /><div><strong>支持画像</strong><p>{profile.data.summary}</p></div></div>
        )}
        <div className="privacy-note"><LockKeyhole size={16} /><span>默认仅自己可见，可在会话中调整</span></div>
      </aside>

      <div className="chat-surface">
        <div className="chat-toolbar">
          <div className="assistant-identity"><span className="assistant-icon"><Bot size={19} /></span><div><strong>心晴 AI</strong><small>倾听支持，不替代诊断</small></div></div>
          <label className="visibility-control"><span>可见范围</span><select value={visibility} disabled={updateVisibility.isPending} onChange={(event) => {
            const nextVisibility = event.target.value as "公开" | "私人";
            const current = conversations.data?.find((item) => item.conversation_id === conversationId);
            setVisibility(nextVisibility);
            if (current) updateVisibility.mutate({ id: conversationId, visibility: nextVisibility });
          }}><option>私人</option><option>公开</option></select></label>
        </div>

        {lastAssessment && lastAssessment.risk.level !== "low" && (
          <div className={`safety-banner ${lastAssessment.risk.level}`} role="alert">
            <AlertTriangle size={20} />
            <div><strong>{riskCopy[lastAssessment.risk.level]}</strong><p>{lastAssessment.support_actions.join(" · ")}</p></div>
            <span>{lastAssessment.risk.score}</span>
          </div>
        )}

        {lastAssessment?.recommended_exercises.length ? (
          <div className="exercise-strip">
            <span className="exercise-strip-title"><Sparkles size={15} /> 此刻可以试试</span>
            {lastAssessment.recommended_exercises.map((exercise) => (
              <button type="button" className="exercise-chip" title={exercise.steps} key={exercise.id}>
                <strong>{exercise.title}</strong><span><Clock3 size={12} /> {exercise.duration_minutes} 分钟</span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="messages" aria-live="polite" ref={messagesRef}>
          {rows.length === 0 && !visibleOptimisticMessage && (
            <div className="chat-empty">
              <ShieldCheck size={30} />
              <h2>这里可以慢慢说</h2>
              <p>可以从“最近让我最累的一件事”开始。对话会结合近期情绪记录提供支持。</p>
            </div>
          )}
          {rows.map((item, index) => (
            <div className={`message-row ${item.role}`} key={`${item.created_at}-${index}`}>
              <span className="message-avatar">{item.role === "user" ? <UserRound size={17} /> : <Bot size={17} />}</span>
              <div className="message">{item.content}</div>
            </div>
          ))}
          {visibleOptimisticMessage && (
            <div className={`message-row user optimistic ${visibleOptimisticMessage.status}`} key={visibleOptimisticMessage.id}>
              <span className="message-avatar"><UserRound size={17} /></span>
              <div className="optimistic-message-content">
                <div className="message">{visibleOptimisticMessage.content}</div>
                <div className="message-delivery" role={visibleOptimisticMessage.status === "failed" ? "alert" : "status"}>
                  {visibleOptimisticMessage.status === "sending" ? (
                    <span>消息已显示，AI 正在生成回应</span>
                  ) : (
                    <>
                      <span>发送失败</span>
                      <button type="button" title="重试发送" aria-label="重试发送" onClick={retryOptimisticMessage}><RefreshCw size={13} /></button>
                      <button type="button" title="移除失败消息" aria-label="移除失败消息" onClick={() => setOptimisticMessage(null)}><X size={13} /></button>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
          {chat.isPending && <div className="message-row assistant"><span className="message-avatar"><Bot size={17} /></span><div className="message typing">正在组织回应<span>...</span></div></div>}
        </div>

        <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); submit(); }}>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            maxLength={2000}
            placeholder="写下此刻最想说的话"
          />
          <div className="composer-actions"><span>{message.length}/2000</span><button className="send-button" disabled={chat.isPending || !message.trim()} aria-label="发送消息"><Send size={18} /></button></div>
        </form>
        {chat.error && <p className="form-error">{chat.error.message}</p>}
      </div>
    </section>
  );
}
