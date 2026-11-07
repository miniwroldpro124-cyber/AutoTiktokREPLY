"use client";

import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { Card, Toggle, Btn, Seg, Field } from "../../components/ui";
import { toast } from "../../components/Toast";

const PLACEHOLDER =
  "{nickname} bận xíu, tí nhắn lại nha 💖 — mẫu {nickname}/{username} sẽ được thay thực tế khi gửi.";

export default function AutoReplyPage() {
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .get("/config")
      .then((d) => setCfg(d.config))
      .catch((e) => setErr(e.message));
  }, []);

  if (err) {
    return (
      <>
        <div className="page-h">
          <h1>Auto-Reply</h1>
        </div>
        <div className="banner"><b>Worker offline.</b> — {err}</div>
      </>
    );
  }
  if (!cfg) {
    return (
      <>
        <div className="page-h"><h1>Auto-Reply</h1></div>
        <div className="empty">đang tải cấu hình…</div>
      </>
    );
  }

  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

  const num = (k, min, max) => (e) => {
    const v = parseInt(e.target.value, 10);
    set(k, Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : min);
  };

  const numf = (k, min, max) => (e) => {
    const v = parseFloat(e.target.value);
    set(k, Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : min);
  };

  const rules = cfg.auto_reply_rules || [];
  const setRules = (arr) => set("auto_reply_rules", arr);
  const addRule = () => setRules([...rules, { contains: "", reply: "" }]);
  const delRule = (i) => setRules(rules.filter((_, j) => j !== i));
  const editRule = (i, k, v) =>
    setRules(rules.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        auto_reply_enabled: !!cfg.auto_reply_enabled,
        check_method: cfg.check_method,
        auto_reply_messages: (cfg.auto_reply_messages || []).filter((m) => m.trim()),
        auto_reply_cooldown_minutes: Number(cfg.auto_reply_cooldown_minutes) || 0,
        auto_reply_max_message_age_minutes:
          Number(cfg.auto_reply_max_message_age_minutes) || 0,
        poll_interval_seconds: Math.max(5, Number(cfg.poll_interval_seconds) || 15),
        send_delay_seconds: Math.max(2, Number(cfg.send_delay_seconds) || 8),
        auto_reply_verbose: !!cfg.auto_reply_verbose,
        auto_reply_typing_delay_seconds:
          Number(cfg.auto_reply_typing_delay_seconds) || 0,
        active_hours_enabled: !!cfg.active_hours_enabled,
        active_hours_start: cfg.active_hours_start || "07:00",
        active_hours_end: cfg.active_hours_end || "23:00",
        auto_reply_rules: rules.filter(
          (r) => (r.contains || "").trim() && (r.reply || "").trim()
        ),
      };
      await api.put("/config", payload);
      setCfg((c) => ({ ...c, ...payload }));
      toast("đã lưu cấu hình auto-reply");
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  };

  const msgs = cfg.auto_reply_messages || [];

  const editMsg = (i, v) =>
    set("auto_reply_messages", msgs.map((m, j) => (j === i ? v : m)));
  const addMsg = () => set("auto_reply_messages", [...msgs, ""]);
  const delMsg = (i) =>
    set("auto_reply_messages", msgs.filter((_, j) => j !== i));
  const moveMsg = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= msgs.length) return;
    const copy = [...msgs];
    [copy[i], copy[j]] = [copy[j], copy[i]];
    set("auto_reply_messages", copy);
  };

  return (
    <>
      <div className="page-h">
        <h1>Auto-Reply</h1>
        <p>Mẫu tin, cooldown, chu kỳ quét — tất cả áp dụng ngay khi lưu.</p>
      </div>

      <div className="grid c2">
        <Card title="Bật tắt">
          <div className="row">
            <div>
              <div className="t">Auto-reply</div>
              <div className="d">Tự trả lời tin nhắn mới từ người lạ</div>
            </div>
            <Toggle on={!!cfg.auto_reply_enabled} onChange={(v) => set("auto_reply_enabled", v)} />
          </div>
          <div className="row">
            <div>
              <div className="t">Phạm vi auto-reply</div>
              <div className="d">
                Tất cả mọi người = quét hộp thư, ai nhắn cũng rep · Watchlist =
                chỉ những user trong danh sách
              </div>
            </div>
            <Seg
              value={cfg.check_method || "inbox"}
              onChange={(v) => set("check_method", v)}
              options={[
                { v: "inbox", l: "TẤT CẢ MỌI NGƯỜI" },
                { v: "watchlist", l: "CHỈ WATCHLIST" },
              ]}
            />
          </div>
          <div className="row">
            <div>
              <div className="t">Verbose</div>
              <div className="d">In chi tiết: tin cũ, đọc lỗi, bỏ qua</div>
            </div>
            <Toggle on={!!cfg.auto_reply_verbose} onChange={(v) => set("auto_reply_verbose", v)} />
          </div>
        </Card>

        <Card title="Nhịp độ">
          <Field label="Cooldown mỗi user (phút)">
            <input
              className="inp"
              type="number"
              min="0"
              max="1440"
              value={cfg.auto_reply_cooldown_minutes ?? 0}
              onChange={num("auto_reply_cooldown_minutes", 0, 1440)}
            />
          </Field>
          <Field label="Bỏ qua tin cũ hơn (phút)" hint="0 = bỏ qua giới hạn tuổi tin">
            <input
              className="inp"
              type="number"
              min="0"
              max="1440"
              value={cfg.auto_reply_max_message_age_minutes ?? 10}
              onChange={num("auto_reply_max_message_age_minutes", 0, 1440)}
            />
          </Field>
          <Field label="Chu kỳ quét (giây)">
            <input
              className="inp"
              type="number"
              min="5"
              max="600"
              value={cfg.poll_interval_seconds ?? 15}
              onChange={num("poll_interval_seconds", 5, 600)}
            />
          </Field>
          <Field label="Delay giữa 2 tin gửi (giây)">
            <input
              className="inp"
              type="number"
              min="2"
              max="300"
              value={cfg.send_delay_seconds ?? 8}
              onChange={num("send_delay_seconds", 2, 300)}
            />
          </Field>
          <Field
            label="Delay gõ trước khi rep (giây)"
            hint="Giả lập gõ tay cho tự nhiên — 0 = gửi ngay"
          >
            <input
              className="inp"
              type="number"
              step="0.5"
              min="0"
              max="30"
              value={cfg.auto_reply_typing_delay_seconds ?? 2.5}
              onChange={numf("auto_reply_typing_delay_seconds", 0, 30)}
            />
          </Field>
        </Card>
      </div>

      <Card
        title={"Mẫu tin trả lời (" + msgs.length + ")"}
        right={
          <div className="actions">
            <Btn className="sm" onClick={addMsg}>+ thêm mẫu</Btn>
          </div>
        }
      >
        {msgs.length === 0 && <div className="empty">chưa có mẫu — bấm “+ thêm mẫu”</div>}
        {msgs.map((m, i) => (
          <div className="tmpl" key={i}>
            <div className="th">
              <span>mẫu #{i + 1}</span>
              <div className="actions">
                <Btn className="sm" onClick={() => moveMsg(i, -1)} disabled={i === 0}>↑</Btn>
                <Btn className="sm" onClick={() => moveMsg(i, 1)} disabled={i === msgs.length - 1}>↓</Btn>
                <Btn className="sm danger" onClick={() => delMsg(i)}>xóa</Btn>
              </div>
            </div>
            <textarea
              className="inp"
              rows={2}
              value={m}
              placeholder={PLACEHOLDER}
              onChange={(e) => editMsg(i, e.target.value)}
            />
          </div>
        ))}
        <div className="hint">
          Biến dùng được: <code>{"{nickname}"}</code>, <code>{"{username}"}</code>,{" "}
          <code>{"{@username}"}</code>. Bot chọn ngẫu nhiên 1 mẫu mỗi lần rep.
        </div>
      </Card>

      <div className="mt" />

      <Card
        title={"Quy tắc từ khóa (" + rules.length + ")"}
        right={<Btn className="sm" onClick={addRule}>+ thêm quy tắc</Btn>}
      >
        {rules.length === 0 && (
          <div className="empty">
            chưa có quy tắc — tin chứa từ khoá sẽ trả lời đúng mẫu chỉ định,
            còn lại random mẫu thường
          </div>
        )}
        {rules.map((r, i) => (
          <div className="tmpl" key={i}>
            <div className="th">
              <span>quy tắc #{i + 1}</span>
              <Btn className="sm danger" onClick={() => delRule(i)}>xóa</Btn>
            </div>
            <div className="grid c2" style={{ marginBottom: 0 }}>
              <Field label="Tin nhắn chứa">
                <input
                  className="inp"
                  value={r.contains || ""}
                  placeholder="giá, size, shop"
                  onChange={(e) => editRule(i, "contains", e.target.value)}
                />
              </Field>
              <Field label="Trả lời">
                <input
                  className="inp"
                  value={r.reply || ""}
                  placeholder="Để lại số zalo nha {nickname} 💖"
                  onChange={(e) => editRule(i, "reply", e.target.value)}
                />
              </Field>
            </div>
          </div>
        ))}
        <div className="hint">
          So sánh không phân biệt hoa/thường, chứa chuỗi là khớp. Quy tắc chạy
          trước mẫu thường.
        </div>
      </Card>

      <div className="mt" />

      <Card title="Giờ hoạt động">
        <div className="row">
          <div>
            <div className="t">Chỉ chạy trong khung giờ</div>
            <div className="d">
              Ngoài khung giờ bot nghỉ — không rep, không auto-send, không quét
              ẩn
            </div>
          </div>
          <Toggle
            on={!!cfg.active_hours_enabled}
            onChange={(v) => set("active_hours_enabled", v)}
          />
        </div>
        <div className="grid c2" style={{ marginBottom: 0 }}>
          <Field label="Từ giờ (HH:MM)">
            <input
              className="inp"
              value={cfg.active_hours_start || "07:00"}
              placeholder="07:00"
              onChange={(e) => set("active_hours_start", e.target.value)}
            />
          </Field>
          <Field label="Đến giờ (HH:MM)">
            <input
              className="inp"
              value={cfg.active_hours_end || "23:00"}
              placeholder="23:00"
              onChange={(e) => set("active_hours_end", e.target.value)}
            />
          </Field>
        </div>
        <div className="hint">Qua nửa đêm vẫn chạy (VD 22:00 → 02:00).</div>
      </Card>

      <div className="actions mt">
        <Btn variant="primary" onClick={save} disabled={saving}>
          {saving ? "đang lưu…" : "Lưu cấu hình"}
        </Btn>
      </div>
    </>
  );
}
