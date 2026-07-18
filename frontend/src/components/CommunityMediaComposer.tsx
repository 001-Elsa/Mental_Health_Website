import { ImagePlus, LoaderCircle, Mic, Square, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { discussionsApi } from "../api/queries";

export type CommunityMediaValue = {
  text: string;
  imageUrl: string;
  audioUrl: string;
};

type Props = {
  value: CommunityMediaValue;
  onChange: (value: CommunityMediaValue) => void;
  placeholder?: string;
  maxLength?: number;
  compact?: boolean;
};

export default function CommunityMediaComposer({
  value,
  onChange,
  placeholder = "写下此刻想分享的内容",
  maxLength = 1000,
  compact = false,
}: Props) {
  const imageInput = useRef<HTMLInputElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [uploading, setUploading] = useState<"image" | "audio" | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => setRecordingSeconds((seconds) => seconds + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  useEffect(() => () => {
    if (recorder.current?.state === "recording") recorder.current.stop();
    recorder.current?.stream.getTracks().forEach((track) => track.stop());
  }, []);

  async function upload(file: File) {
    const kind = file.type.startsWith("image/") ? "image" : "audio";
    setUploading(kind);
    setError("");
    try {
      const result = await discussionsApi.uploadMedia(file);
      onChange({
        ...value,
        imageUrl: result.media_type === "image" ? result.url : value.imageUrl,
        audioUrl: result.media_type === "audio" ? result.url : value.audioUrl,
      });
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "媒体上传失败");
    } finally {
      setUploading(null);
    }
  }

  async function startRecording() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("当前浏览器不支持录音，请改用图片或文字分享。 ");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const nextRecorder = new MediaRecorder(stream);
      chunks.current = [];
      nextRecorder.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      nextRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const type = nextRecorder.mimeType || "audio/webm";
        const blob = new Blob(chunks.current, { type });
        if (blob.size) await upload(new File([blob], `voice-${Date.now()}.webm`, { type }));
      };
      recorder.current = nextRecorder;
      nextRecorder.start();
      setRecordingSeconds(0);
      setRecording(true);
    } catch {
      setError("未获得麦克风权限，无法开始录音。 ");
    }
  }

  function stopRecording() {
    if (recorder.current?.state === "recording") recorder.current.stop();
    setRecording(false);
  }

  return (
    <div className={`community-media-composer ${compact ? "compact" : ""}`}>
      <textarea
        value={value.text}
        onChange={(event) => onChange({ ...value, text: event.target.value })}
        placeholder={placeholder}
        maxLength={maxLength}
        aria-label="分享文字"
      />

      {(value.imageUrl || value.audioUrl) && (
        <div className="community-media-preview">
          {value.imageUrl && (
            <div className="media-preview-item image">
              <img src={value.imageUrl} alt="待发布图片预览" />
              <button type="button" className="icon-button subtle" title="移除图片" aria-label="移除图片" onClick={() => onChange({ ...value, imageUrl: "" })}><Trash2 size={15} /></button>
            </div>
          )}
          {value.audioUrl && (
            <div className="media-preview-item audio">
              <audio controls src={value.audioUrl}>你的浏览器不支持音频播放。</audio>
              <button type="button" className="icon-button subtle" title="移除语音" aria-label="移除语音" onClick={() => onChange({ ...value, audioUrl: "" })}><Trash2 size={15} /></button>
            </div>
          )}
        </div>
      )}

      <div className="community-media-toolbar">
        <input
          ref={imageInput}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            event.target.value = "";
          }}
        />
        <button type="button" className="icon-button subtle" title="添加图片" aria-label="添加图片" disabled={Boolean(uploading)} onClick={() => imageInput.current?.click()}>
          {uploading === "image" ? <LoaderCircle className="spin" size={17} /> : <ImagePlus size={17} />}
        </button>
        <button
          type="button"
          className={`icon-button subtle ${recording ? "recording" : ""}`}
          title={recording ? "结束录音" : "录制语音"}
          aria-label={recording ? "结束录音" : "录制语音"}
          disabled={Boolean(uploading)}
          onClick={recording ? stopRecording : () => void startRecording()}
        >
          {uploading === "audio" ? <LoaderCircle className="spin" size={17} /> : recording ? <Square size={15} /> : <Mic size={17} />}
        </button>
        {recording && <span className="recording-status">录音中 {recordingSeconds}s</span>}
        <span className="composer-count">{value.text.length}/{maxLength}</span>
      </div>
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}
