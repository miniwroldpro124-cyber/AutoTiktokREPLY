"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { Card, Btn, Seg, lineClass } from "../../components/ui";
import { toast } from "../../components/Toast";

const FILTERS = [
  { v: "all", l: "Tất cả" },
  { v: "ok", l: "Thành công" },
  { v: "fail", l: "Lỗi" },
  { v: "reply", l: "Rep" },
];

function match(line, f) {
  if (f === "all") return true;
  if (f === "ok") return /\[(OK|REPLY)\]/.test(line);
  if (f === "fail") return /\[(FAIL|ERR|WARN)\]/.test(line);
  if (f === "reply") return /\[(REPLY|📩)\]/.test(line);
  return true;
}

export default function LogsPage() {
  const [lines, setLines] = useState([]);
  const [auto, setAuto] = useState(true);
  const [filter, setFilter] = useState("all");
  const [err, setErr] = useState("");
  const boxRef = useRef(null);
  const stickRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const d = await api.get("/logs?limit=500");
      setLines(d.lines || []);
      setErr("");
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    if (!auto) return;
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load, auto]);

  useEffect(() => {
    const el = boxRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [lines]);

  const onScroll = () => {
    const el = boxRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  };

  const clear = async () => {
    try {
      await api.post("/logs/clear", {});
      toast("đã xóa log trên worker");
      await load();
    } catch (e) {
      toast(e.message, "err");
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      toast("đã copy " + lines.length + " dòng");
    } catch {
      toast("copy thất bại", "err");
    }
  };

  const shown = lines.filter((l) => match(l, filter));

  return (
    <>
      <div className="page-h">
        <h1>Nhật ký</h1>
        <p>Log trực tiếp từ worker 24/7 — tự làm mới mỗi 4 giây.</p>
      </div>

      {err && <div className="banner"><b>Worker offline.</b> — {err}</div>}

      <Card
        title={"Log (" + shown.length + "/" + lines.length + ")"}
        right={
          <div className="actions">
            <Seg value={filter} options={FILTERS} onChange={setFilter} />
            <Btn className="sm" onClick={() => setAuto(!auto)}>
              {auto ? "⏸ tắt tự làm mới" : "▶ tự làm mới"}
            </Btn>
            <Btn className="sm" onClick={copy}>copy</Btn>
            <Btn className="sm danger" onClick={clear}>xóa log</Btn>
          </div>
        }
      >
        <div className="logs" ref={boxRef} onScroll={onScroll}>
          {shown.length === 0 && <span className="ln lg-dim">— trống —</span>}
          {shown.map((l, i) => (
            <span key={i} className={"ln " + lineClass(l)}>{l}</span>
          ))}
        </div>
      </Card>
    </>
  );
}
