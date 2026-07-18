import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Camera, FileText, Heart, ImagePlus, KeyRound, LogOut, Mail, MessageCircle, Phone, Save, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi, discussionsApi } from "../api/queries";
import RequireLogin from "../components/RequireLogin";
import { useAuthStore } from "../store/auth";
import type { User } from "../types";

type ProfileTab = "profile" | "posts" | "security";

const dateFormatter = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" });

function formatDate(value?: string) {
  if (!value) return "暂未记录";
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return dateFormatter.format(new Date(normalized));
}

export default function ProfilePage() {
  return <RequireLogin><ProfileContent /></RequireLogin>;
}

function ProfileContent() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const storedUser = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const logout = useAuthStore((state) => state.logout);
  const [tab, setTab] = useState<ProfileTab>("profile");
  const [feedback, setFeedback] = useState("");
  const avatarInput = useRef<HTMLInputElement>(null);
  const backgroundInput = useRef<HTMLInputElement>(null);
  const me = useQuery({ queryKey: ["me"], queryFn: authApi.me });
  const posts = useQuery({ queryKey: ["my-discussions"], queryFn: discussionsApi.mine });
  const user = me.data ?? storedUser;

  useEffect(() => {
    if (me.data) setUser(me.data);
  }, [me.data, setUser]);

  const upload = useMutation({
    mutationFn: ({ kind, file }: { kind: "avatar" | "background"; file: File }) => authApi.uploadProfileMedia(kind, file),
    onSuccess: (data) => {
      setUser(data.user);
      qc.setQueryData(["me"], data.user);
      setFeedback(data.kind === "avatar" ? "头像已更新。" : "背景图已更新。");
    },
  });

  const handleLogout = () => {
    logout();
    qc.clear();
    navigate("/dashboard", { replace: true });
  };

  if (!user) return <div className="page-loading">正在加载个人信息...</div>;

  return (
    <section className="page profile-page">
      <div className="profile-cover" style={user.background_url ? { backgroundImage: `url(${user.background_url})` } : undefined}>
        <input ref={backgroundInput} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate({ kind: "background", file }); event.target.value = ""; }} />
        <button type="button" className="profile-cover-action" disabled={upload.isPending} onClick={() => backgroundInput.current?.click()}><ImagePlus size={16} /> 更换背景</button>
      </div>

      <div className="profile-identity">
        <div className="profile-avatar-wrap">
          <span className="profile-avatar">{user.avatar_url ? <img src={user.avatar_url} alt={`${user.nickname}的头像`} /> : user.nickname.slice(0, 1)}</span>
          <input ref={avatarInput} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate({ kind: "avatar", file }); event.target.value = ""; }} />
          <button type="button" className="profile-avatar-action" title="更换头像" aria-label="更换头像" disabled={upload.isPending} onClick={() => avatarInput.current?.click()}><Camera size={16} /></button>
        </div>
        <div className="profile-name-block">
          <div><h2>{user.nickname}</h2><span>{user.role === "admin" ? "平台管理员" : "高校学生"}</span></div>
          <p>{user.signature || "还没有写个性签名"}</p>
        </div>
        <button type="button" className="profile-logout" onClick={handleLogout}><LogOut size={16} /> 退出登录</button>
      </div>

      {feedback && <div className="success-notice profile-feedback">{feedback}<button type="button" aria-label="关闭提示" onClick={() => setFeedback("")}>×</button></div>}
      {upload.error && <p className="form-error profile-upload-error">{upload.error.message}</p>}

      <div className="profile-workspace">
        <nav className="profile-tabs" aria-label="个人信息分类">
          <button type="button" className={tab === "profile" ? "active" : ""} onClick={() => setTab("profile")}><UserRound size={17} /><span>个人资料</span></button>
          <button type="button" className={tab === "posts" ? "active" : ""} onClick={() => setTab("posts")}><FileText size={17} /><span>发布历史</span><strong>{posts.data?.length ?? 0}</strong></button>
          <button type="button" className={tab === "security" ? "active" : ""} onClick={() => setTab("security")}><ShieldCheck size={17} /><span>账号安全</span></button>
        </nav>

        <div className="profile-content">
          {tab === "profile" && <ProfileDetails user={user} onSaved={(next) => { setUser(next); qc.setQueryData(["me"], next); setFeedback("个人资料已保存。"); }} />}
          {tab === "posts" && <PostHistory posts={posts.data ?? []} loading={posts.isLoading} />}
          {tab === "security" && <SecuritySettings user={user} onUserChanged={(next, message) => { setUser(next); qc.setQueryData(["me"], next); setFeedback(message); }} onPasswordChanged={handleLogout} />}
        </div>
      </div>
    </section>
  );
}

function ProfileDetails({ user, onSaved }: { user: User; onSaved: (user: User) => void }) {
  const [nickname, setNickname] = useState(user.nickname);
  const [signature, setSignature] = useState(user.signature ?? "");
  const update = useMutation({ mutationFn: authApi.updateMe, onSuccess: onSaved });

  useEffect(() => {
    setNickname(user.nickname);
    setSignature(user.signature ?? "");
  }, [user.nickname, user.signature]);

  return (
    <div className="profile-panel-stack">
      <section className="profile-section">
        <div className="profile-section-heading"><div><span className="section-kicker">Public profile</span><h3>公开资料</h3></div><small>同伴社区会显示你的昵称和头像</small></div>
        <form className="profile-form" onSubmit={(event) => { event.preventDefault(); if (nickname.trim().length >= 2) update.mutate({ nickname: nickname.trim(), signature: signature.trim() }); }}>
          <label><span>昵称</span><input value={nickname} onChange={(event) => setNickname(event.target.value)} maxLength={20} /></label>
          <label className="wide"><span>个性签名</span><textarea value={signature} onChange={(event) => setSignature(event.target.value)} maxLength={120} placeholder="写一句想让别人了解你的话" /></label>
          <div className="profile-form-submit"><p className="form-error">{nickname.trim().length < 2 ? "昵称至少 2 个字" : update.error?.message}</p><span>{signature.length}/120</span><button disabled={update.isPending}><Save size={16} /> 保存资料</button></div>
        </form>
      </section>
      <section className="profile-section">
        <div className="profile-section-heading"><div><span className="section-kicker">Account</span><h3>账号信息</h3></div></div>
        <dl className="profile-facts">
          <div><dt><Phone size={15} /> 手机号</dt><dd>{user.phone || "未绑定"}</dd></div>
          <div><dt><Mail size={15} /> 邮箱</dt><dd>{user.email || "未绑定"}</dd></div>
          <div><dt><CalendarDays size={15} /> 加入时间</dt><dd>{formatDate(user.created_at)}</dd></div>
        </dl>
      </section>
    </div>
  );
}

function PostHistory({ posts, loading }: { posts: Awaited<ReturnType<typeof discussionsApi.mine>>; loading: boolean }) {
  if (loading) return <p className="empty-copy">正在加载发布历史...</p>;
  return (
    <section className="profile-section post-history-section">
      <div className="profile-section-heading"><div><span className="section-kicker">Peer stories</span><h3>同伴社区发布历史</h3></div><small>包含公开、私人和审核中的内容</small></div>
      <div className="profile-post-list">
        {posts.map((post) => (
          <article className="profile-post" key={post.id}>
            <header><span className="topic-tag">{post.category || "日常分享"}</span><time dateTime={post.created_at}>{formatDate(post.created_at)}</time></header>
            <h4>{post.title}</h4>
            {post.content && <p>{post.content}</p>}
            {post.image_url && <img src={post.image_url} alt="发布内容配图" loading="lazy" />}
            {post.audio_url && <audio controls preload="metadata" src={post.audio_url}>你的浏览器不支持音频播放。</audio>}
            <footer><span>{post.visibility} · {post.status === "published" ? "正常" : post.status === "pending_review" ? "待审核" : "已隐藏"}</span><span><Heart size={14} /> {post.like_count}</span><span><MessageCircle size={14} /> {post.reply_count}</span></footer>
          </article>
        ))}
        {!posts.length && <p className="empty-copy">还没有发布过同伴分享。</p>}
      </div>
    </section>
  );
}

function SecuritySettings({ user, onUserChanged, onPasswordChanged }: { user: User; onUserChanged: (user: User, message: string) => void; onPasswordChanged: () => void }) {
  const [phone, setPhone] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [phonePassword, setPhonePassword] = useState("");
  const [phoneHint, setPhoneHint] = useState("");
  const [email, setEmail] = useState(user.email ?? "");
  const [emailCode, setEmailCode] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailHint, setEmailHint] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const sendPhoneCode = useMutation({ mutationFn: authApi.sendCode, onSuccess: (data) => setPhoneHint(data.dev_code ? `本地验证码：${data.dev_code}` : data.message) });
  const changePhone = useMutation({ mutationFn: authApi.changePhone, onSuccess: (next) => { setPhone(""); setPhoneCode(""); setPhonePassword(""); setPhoneHint(""); onUserChanged(next, "手机号已更新。"); } });
  const sendEmailCode = useMutation({ mutationFn: authApi.sendEmailCode, onSuccess: (data) => setEmailHint(data.dev_code ? `本地验证码：${data.dev_code}` : data.message) });
  const bindEmail = useMutation({ mutationFn: authApi.bindEmail, onSuccess: (next) => { setEmailCode(""); setEmailPassword(""); setEmailHint(""); onUserChanged(next, "邮箱已验证并绑定。"); } });
  const changePassword = useMutation({ mutationFn: authApi.changePassword, onSuccess: onPasswordChanged });

  return (
    <div className="profile-panel-stack">
      <section className="profile-section security-section">
        <div className="profile-section-heading"><div><span className="section-kicker">Mobile</span><h3>更换手机号</h3></div><small>当前：{user.phone || "未绑定"}</small></div>
        <form className="security-form" onSubmit={(event) => { event.preventDefault(); changePhone.mutate({ new_phone: phone, code: phoneCode, current_password: phonePassword }); }}>
          <label><span>新手机号</span><input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="11 位手机号" maxLength={11} /></label>
          <label><span>短信验证码</span><div className="security-code-field"><input value={phoneCode} onChange={(event) => setPhoneCode(event.target.value)} maxLength={6} /><button type="button" className="secondary-button" disabled={!/^1[3-9]\d{9}$/.test(phone) || sendPhoneCode.isPending} onClick={() => sendPhoneCode.mutate(phone)}>获取验证码</button></div></label>
          <label><span>当前密码</span><input type="password" value={phonePassword} onChange={(event) => setPhonePassword(event.target.value)} autoComplete="current-password" /></label>
          <div className="security-submit"><p>{phoneHint}</p><span className="form-error">{sendPhoneCode.error?.message || changePhone.error?.message}</span><button disabled={!phone || !phoneCode || !phonePassword || changePhone.isPending}>确认更换</button></div>
        </form>
      </section>

      <section className="profile-section security-section">
        <div className="profile-section-heading"><div><span className="section-kicker">Email</span><h3>{user.email ? "更换绑定邮箱" : "绑定邮箱"}</h3></div><small>{user.email || "绑定后可作为安全联系方式"}</small></div>
        <form className="security-form" onSubmit={(event) => { event.preventDefault(); bindEmail.mutate({ email, code: emailCode, current_password: emailPassword }); }}>
          <label><span>邮箱地址</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" /></label>
          <label><span>邮箱验证码</span><div className="security-code-field"><input value={emailCode} onChange={(event) => setEmailCode(event.target.value)} maxLength={6} /><button type="button" className="secondary-button" disabled={!email || !emailPassword || sendEmailCode.isPending} onClick={() => sendEmailCode.mutate({ email, current_password: emailPassword })}>发送验证码</button></div></label>
          <label><span>当前密码</span><input type="password" value={emailPassword} onChange={(event) => setEmailPassword(event.target.value)} autoComplete="current-password" /></label>
          <div className="security-submit"><p>{emailHint}</p><span className="form-error">{sendEmailCode.error?.message || bindEmail.error?.message}</span><button disabled={!email || !emailCode || !emailPassword || bindEmail.isPending}>确认绑定</button></div>
        </form>
      </section>

      <section className="profile-section security-section password-section">
        <div className="profile-section-heading"><div><span className="section-kicker">Password</span><h3>修改密码</h3></div><small>修改成功后需要重新登录</small></div>
        <form className="security-form" onSubmit={(event) => { event.preventDefault(); if (newPassword === confirmPassword) changePassword.mutate({ current_password: currentPassword, new_password: newPassword }); }}>
          <label><span>当前密码</span><input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" /></label>
          <label><span>新密码</span><input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" placeholder="至少 8 位" /></label>
          <label><span>确认新密码</span><input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" /></label>
          <div className="security-submit"><p /><span className="form-error">{newPassword && confirmPassword && newPassword !== confirmPassword ? "两次输入的新密码不一致" : changePassword.error?.message}</span><button disabled={!currentPassword || newPassword.length < 8 || newPassword !== confirmPassword || changePassword.isPending}><KeyRound size={15} /> 更新密码</button></div>
        </form>
      </section>
    </div>
  );
}
