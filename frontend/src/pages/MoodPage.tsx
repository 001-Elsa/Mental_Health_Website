import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { moodApi } from "../api/queries";
import RequireLogin from "../components/RequireLogin";

const schema = z.object({
  score: z.coerce.number().min(1).max(10),
  trigger: z.string().optional(),
  note: z.string().min(1, "请写下日志内容"),
  visibility: z.string(),
});

type MoodForm = z.infer<typeof schema>;

export default function MoodPage() {
  const qc = useQueryClient();
  const [riskNotice, setRiskNotice] = useState<string[]>([]);
  const logs = useQuery({ queryKey: ["mood"], queryFn: moodApi.list });
  const form = useForm<MoodForm>({ resolver: zodResolver(schema), defaultValues: { score: 7, visibility: "公开" } });
  const create = useMutation({
    mutationFn: moodApi.create,
    onSuccess: (data) => {
      form.reset({ score: 7, visibility: "公开" });
      qc.invalidateQueries({ queryKey: ["mood"] });
      qc.invalidateQueries({ queryKey: ["myMood"] });
      qc.invalidateQueries({ queryKey: ["moodForecast"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["riskStatus"] });
      setRiskNotice(data.risk && data.risk.level !== "low" ? data.risk.signals : []);
    },
  });
  const bookmark = useMutation({
    mutationFn: moodApi.bookmark,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mood"] }),
  });

  return (
    <section className="page">
      {riskNotice.length > 0 && (
        <div className="safety-banner medium" role="alert">
          <AlertTriangle size={20} /><div><strong>近期情绪变化值得关注</strong><p>{riskNotice.join(" · ")}。建议联系可信任的人或预约学校心理中心。</p></div>
        </div>
      )}
      <div className="panel">
        <h2>记录今天的情绪</h2>
        <RequireLogin>
          <form className="form-grid three" onSubmit={form.handleSubmit((values) => create.mutate({ ...values, trigger: values.trigger || "" }))}>
            <input type="number" min="1" max="10" {...form.register("score")} />
            <input placeholder="触发因素" {...form.register("trigger")} />
            <select {...form.register("visibility")}><option>公开</option><option>私人</option></select>
            <textarea placeholder="此刻发生了什么？" {...form.register("note")} />
            <p className="error">{form.formState.errors.note?.message || create.error?.message}</p>
            <button>保存日志</button>
          </form>
        </RequireLogin>
      </div>
      <div className="list">
        {logs.data?.map((item) => (
          <article className="card" key={item.id}>
            <div className="card-head">
              <strong>{item.score} / 10 分</strong>
              <small>用户 #{item.user_id} · {item.created_at.slice(0, 10)}</small>
            </div>
            <p>{item.note}</p>
            <span className="tag">{item.trigger || "未记录触发因素"}</span>
            <RequireLogin>
              <button className="ghost" onClick={() => bookmark.mutate(item.id)}>收藏 {item.bookmark_count}</button>
            </RequireLogin>
          </article>
        ))}
      </div>
    </section>
  );
}
