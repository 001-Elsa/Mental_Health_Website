import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Flag, Heart, MessageCircle, Radio, Send, ShieldCheck, SquarePen } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { discussionsApi } from "../api/queries";
import CommunityMediaComposer, { type CommunityMediaValue } from "../components/CommunityMediaComposer";
import RequireLogin from "../components/RequireLogin";
import { useAuthStore } from "../store/auth";
import type { Discussion, PlazaMessage } from "../types";

const emptyMedia: CommunityMediaValue = { text: "", imageUrl: "", audioUrl: "" };
const dateTime = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

function formatTime(value: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return dateTime.format(new Date(normalized));
}

export default function CommunityPage() {
  const qc = useQueryClient();
  const token = useAuthStore((state) => state.token);
  const [selected, setSelected] = useState<Discussion | null>(null);
  const [feedback, setFeedback] = useState("");
  const discussions = useQuery({ queryKey: ["discussions"], queryFn: discussionsApi.list });
  const replies = useQuery({
    queryKey: ["replies", selected?.id],
    queryFn: () => discussionsApi.replies(selected!.id),
    enabled: Boolean(selected),
  });
  const myDiscussions = useQuery({ queryKey: ["my-discussions"], queryFn: discussionsApi.mine, enabled: Boolean(token) });
  const reply = useMutation({
    mutationFn: (content: string) => discussionsApi.reply(selected!.id, content),
    onSuccess: (data) => {
      setFeedback(data.status === "pending_review" ? "回复已进入审核。" : "回复已发布。");
      qc.invalidateQueries({ queryKey: ["replies", selected?.id] });
      qc.invalidateQueries({ queryKey: ["discussions"] });
    },
  });
  const like = useMutation({
    mutationFn: discussionsApi.like,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["discussions"] }),
  });
  const report = useMutation({
    mutationFn: (id: number) => discussionsApi.report(id, "不友善或不安全内容"),
    onSuccess: () => setFeedback("举报已提交，管理员会尽快审核。"),
  });

  return (
    <section className="page community-layout">
      <div className="community-main">
        <div className="community-intro">
          <div><span className="section-kicker">Peer support</span><h2>最近的同伴分享</h2><p>表达感受、交换经验，也尊重每个人的边界。</p></div>
          <div className="community-intro-actions">
            <span className="community-safety"><ShieldCheck size={16} /> 内容安全审核已开启</span>
            <Link to="/community/new" className="community-publish-button"><SquarePen size={17} /> 发布分享</Link>
          </div>
        </div>
        {feedback && <div className="success-notice">{feedback}<button onClick={() => setFeedback("")} aria-label="关闭提示">×</button></div>}
        <div className="discussion-feed">
          {discussions.data?.map((item) => (
            <article className={`discussion-item ${selected?.id === item.id ? "selected" : ""}`} key={item.id}>
              <button className="discussion-body" onClick={() => setSelected(item)}>
                <div className="discussion-meta"><span className="topic-tag">{item.category || "日常分享"}</span><time dateTime={item.created_at}>{formatTime(item.created_at)}</time></div>
                <h3>{item.title}</h3>
                {item.content && <p>{item.content}</p>}
              </button>
              {(item.image_url || item.audio_url) && <CommunityMedia imageUrl={item.image_url} audioUrl={item.audio_url} />}
              <div className="discussion-actions">
                <button className="text-button" disabled={!token} onClick={() => like.mutate(item.id)}><Heart size={16} /> {item.like_count}</button>
                <button className="text-button" onClick={() => setSelected(item)}><MessageCircle size={16} /> {item.reply_count}</button>
                <button className="icon-button subtle" disabled={!token} title="举报内容" aria-label="举报内容" onClick={() => report.mutate(item.id)}><Flag size={16} /></button>
              </div>
            </article>
          ))}
          {!discussions.isLoading && !discussions.data?.length && <p className="empty-copy">还没有公开讨论，来发布第一条分享吧。</p>}
        </div>
      </div>

      <aside className="community-side">
        <RealtimePlaza onFeedback={setFeedback} />

        {token && (
          <section className="workspace-section my-posts-section">
            <h2>我的发布</h2>
            <div className="my-posts-list">
              {myDiscussions.data?.slice(0, 5).map((item) => (
                <button key={item.id} onClick={() => setSelected(item)}>
                  <strong>{item.title}</strong><span>{item.visibility} · {item.status === "published" ? "正常" : item.status === "pending_review" ? "待审核" : "已隐藏"}</span>
                </button>
              ))}
              {!myDiscussions.data?.length && <p className="muted">还没有发布记录</p>}
            </div>
          </section>
        )}

        <section className="workspace-section reply-section">
          <h2>{selected ? selected.title : "讨论回复"}</h2>
          {selected ? (
            <>
              <div className="reply-list">
                {replies.data?.map((item) => <div className="reply-item" key={item.id}><span>同学 #{item.user_id}</span><p>{item.content}</p></div>)}
                {!replies.data?.length && <p className="muted">还没有回复</p>}
              </div>
              <RequireLogin><ReplyBox onSubmit={(text) => reply.mutate(text)} /></RequireLogin>
            </>
          ) : <p className="muted">选择一条分享查看并参与讨论。</p>}
        </section>
      </aside>
    </section>
  );
}

function RealtimePlaza({ onFeedback }: { onFeedback: (message: string) => void }) {
  const qc = useQueryClient();
  const [media, setMedia] = useState<CommunityMediaValue>(emptyMedia);
  const feedRef = useRef<HTMLDivElement>(null);
  const messages = useQuery({ queryKey: ["plaza-messages"], queryFn: discussionsApi.plaza, refetchInterval: 5000 });
  const send = useMutation({
    mutationFn: discussionsApi.sendToPlaza,
    onSuccess: (message) => {
      setMedia(emptyMedia);
      if (message.status === "pending_review") onFeedback("这条广场消息已进入安全审核，通过后会公开显示。");
      qc.invalidateQueries({ queryKey: ["plaza-messages"] });
    },
  });

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/discussions/plaza/ws`);
    socket.onmessage = () => qc.invalidateQueries({ queryKey: ["plaza-messages"] });
    const heartbeat = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 20000);
    return () => {
      window.clearInterval(heartbeat);
      socket.close();
    };
  }, [qc]);

  useEffect(() => {
    const feed = feedRef.current;
    if (feed) feed.scrollTop = feed.scrollHeight;
  }, [messages.data?.length]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!media.text.trim() && !media.imageUrl && !media.audioUrl) return;
    send.mutate({ content: media.text.trim(), image_url: media.imageUrl, audio_url: media.audioUrl });
  }

  return (
    <section className="workspace-section realtime-plaza">
      <div className="plaza-heading"><div><span><Radio size={16} /> 实时交流广场</span><small>在线消息会自动出现</small></div><i aria-label="实时连接中" title="实时连接中" /></div>
      <div className="plaza-feed" ref={feedRef} aria-live="polite">
        {messages.data?.map((message) => <PlazaMessageItem key={message.id} message={message} />)}
        {!messages.isLoading && !messages.data?.length && <p className="empty-copy">这里还很安静，发出第一句问候吧。</p>}
      </div>
      <RequireLogin>
        <form className="plaza-composer" onSubmit={submit}>
          <CommunityMediaComposer compact value={media} onChange={setMedia} placeholder="发送文字、图片或语音" maxLength={1000} />
          <button className="icon-button plaza-send" aria-label="发送到实时广场" title="发送" disabled={send.isPending}><Send size={17} /></button>
          {send.error && <p className="form-error">{send.error.message}</p>}
        </form>
      </RequireLogin>
    </section>
  );
}

function PlazaMessageItem({ message }: { message: PlazaMessage }) {
  return (
    <article className="plaza-message">
      <header><strong>{message.author_name}</strong><time dateTime={message.created_at}>{formatTime(message.created_at)}</time></header>
      {message.content && <p>{message.content}</p>}
      <CommunityMedia imageUrl={message.image_url} audioUrl={message.audio_url} compact />
    </article>
  );
}

function CommunityMedia({ imageUrl, audioUrl, compact = false }: { imageUrl: string; audioUrl: string; compact?: boolean }) {
  if (!imageUrl && !audioUrl) return null;
  return (
    <div className={`published-community-media ${compact ? "compact" : ""}`}>
      {imageUrl && <img src={imageUrl} alt="用户分享的图片" loading="lazy" />}
      {audioUrl && <audio controls preload="metadata" src={audioUrl}>你的浏览器不支持音频播放。</audio>}
    </div>
  );
}

function ReplyBox({ onSubmit }: { onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <form className="reply-composer" onSubmit={(event) => { event.preventDefault(); if (text.trim()) { onSubmit(text.trim()); setText(""); } }}>
      <input value={text} onChange={(event) => setText(event.target.value)} placeholder="写下支持或经验" maxLength={500} />
      <button className="icon-button" aria-label="发送回复"><Send size={17} /></button>
    </form>
  );
}
