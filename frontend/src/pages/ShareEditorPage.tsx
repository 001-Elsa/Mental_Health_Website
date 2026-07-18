import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Send, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { discussionsApi } from "../api/queries";
import CommunityMediaComposer, { type CommunityMediaValue } from "../components/CommunityMediaComposer";
import RequireLogin from "../components/RequireLogin";

const categories = ["学习压力", "人际关系", "睡眠困扰", "自我成长", "经验分享"];
const emptyMedia: CommunityMediaValue = { text: "", imageUrl: "", audioUrl: "" };

export default function ShareEditorPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState(categories[0]);
  const [visibility, setVisibility] = useState<"公开" | "私人">("公开");
  const [media, setMedia] = useState(emptyMedia);
  const [error, setError] = useState("");
  const create = useMutation({
    mutationFn: discussionsApi.create,
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["discussions"] }),
        qc.invalidateQueries({ queryKey: ["my-discussions"] }),
      ]);
      navigate("/community", { replace: true });
    },
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (title.trim().length < 4) {
      setError("标题至少 4 个字");
      return;
    }
    if (!media.text.trim() && !media.imageUrl && !media.audioUrl) {
      setError("正文、图片或语音至少填写一项");
      return;
    }
    create.mutate({
      title: title.trim(),
      category,
      visibility,
      content: media.text.trim(),
      image_url: media.imageUrl,
      audio_url: media.audioUrl,
    });
  }

  return (
    <section className="page share-editor-page">
      <div className="share-editor-heading">
        <Link to="/community" className="icon-button subtle" title="返回同伴社区" aria-label="返回同伴社区"><ArrowLeft size={18} /></Link>
        <div><span className="section-kicker">New peer story</span><h2>发布同伴分享</h2><p>可以只写几句话，也可以附上一张图片或一段语音。</p></div>
        <span className="community-safety"><ShieldCheck size={16} /> 发布前自动安全审核</span>
      </div>
      <RequireLogin>
        <form className="share-editor-form" onSubmit={submit}>
          <div className="share-editor-fields">
            <label className="wide"><span>标题</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="用一句话概括这次分享" maxLength={80} /></label>
            <label><span>话题</span><select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label><span>可见范围</span><select value={visibility} onChange={(event) => setVisibility(event.target.value as "公开" | "私人")}><option>公开</option><option>私人</option></select></label>
          </div>
          <CommunityMediaComposer value={media} onChange={setMedia} placeholder="分享你的感受、经历，或曾经帮助过你的方法" maxLength={2000} />
          <div className="share-editor-submit">
            <p className="form-error">{error || create.error?.message}</p>
            <button type="submit" disabled={create.isPending}><Send size={17} /> {create.isPending ? "正在提交" : "发布分享"}</button>
          </div>
        </form>
      </RequireLogin>
    </section>
  );
}
