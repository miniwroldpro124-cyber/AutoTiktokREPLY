"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, fmtUptime } from "../lib/api";
import { Card, Toggle, Btn, Seg, lineClass } from "../components/ui";
import Ava from "../components/Ava";
import { toast } from "../components/Toast";

const fmtTime = (ts) =>
  ts ? new Date(ts * 1000).toLocaleString("vi-VN") : "chưa";

export default function Dashboard() {
  const [st, setSt] = useState(null);
  const [logs, setLogs] = useState([]);
  const [wl, setWl] = useState([]);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await api.get("/status");
      setSt(d);
      setErr("");
    } catch (e) {
      setErr(e.message);
    }
    try {
      const w = await api.get("/watchlist");
      setWl(w.users || []);
    } catch {
      /* worker down — banner đã hiển thị */
    }
    try {
      const l = await api.get("/logs?limit=8");
      setLogs(l.lines || []);
    } catch {
      /* worker down — banner đã hiển thị */
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  const cfg = (st && st.config) || {};

  const patch = async (p) => {
    try {
      await api.put("/config", p);
      setSt((s) => (s ? { ...s, config: { ...s.config, ...p } } : s));
      toast("đã lưu");
    } catch (e) {
      toast(e.message, "err");
    }
  };

  const runDetect = async () => {
    try {
      const d = await api.post("/detect", {});
      toast(d.message || (d.started ? "bắt đầu quét" : "đang quét"));
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  };

  return (
    <>
      <div className="page-h">
        <h1>Tổng quan</h1>
        <p>Trạng thái bot, toggle nhanh, hoạt động gần nhất.</p>
      </div>

      {err && (
        <div className="banner">
          <b>Worker 24/7 chưa kết nối.</b> — {err}
          <br />
          Chạy worker (docker) rồi set <code>WORKER_URL</code> trong environment của
          Vercel (Settings → Environment Variables) và redeploy. Xem{" "}
          <code>site/README.md</code>.
        </div>
      )}

      <div className="grid c4">
        <Card className="stat">
          <div className="ava-row">
            <Ava
              src={st && st.avatar}
              name={(st && st.username) || "?"}
              size={44}
            />
            <div style={{ minWidth: 0 }}>
              <div className="v sm">
                {st && st.live ? "@" + (st.username || "?") : "OFFLINE"}
              </div>
              <div className="k">Tài khoản</div>
            </div>
          </div>
          <div className="sub">
            {st && st.live
              ? st.nickname || "đã login"
              : st
                ? st.boot && st.boot.state === "starting"
                  ? "đang khởi động session…"
                  : "chưa login"
                : "đang kết nối…"}
          </div>
        </Card>
        <Card className="stat">
          <div className="v">{st ? st.watchlist : "—"}</div>
          <div className="k">Watchlist</div>
          <div className="sub">user đang theo dõi</div>
        </Card>
        <Card className="stat">
          <div className="v">{st ? st.uid_cache : "—"}</div>
          <div className="k">UID cache</div>
          <div className="sub">đã resolve nickname/uid</div>
        </Card>
        <Card className="stat">
          <div className="v sm">{st ? fmtUptime(st.uptime_seconds) : "—"}</div>
          <div className="k">Uptime worker</div>
          <div className="sub">{st && st.bot_version ? "bot " + st.bot_version : "24/7"}</div>
        </Card>
      </div>

      <div className="grid c2">
        <Card title="Toggle nhanh">
          <div className="row">
            <div>
              <div className="t">Auto-reply</div>
              <div className="d">Trả lời tin nhắn tự động theo cooldown</div>
            </div>
            <Toggle
              on={!!cfg.auto_reply_enabled}
              onChange={(v) => patch({ auto_reply_enabled: v })}
            />
          </div>
          <div className="row">
            <div>
              <div className="t">Auto-send định kỳ</div>
              <div className="d">
                {cfg.auto_send_time || "00:00"} GMT+
                {cfg.auto_send_timezone_offset ?? 7} ·{" "}
                {Array.isArray(cfg.auto_send_targets)
                  ? cfg.auto_send_targets.length + " user"
                  : cfg.auto_send_targets || "cache"}
              </div>
            </div>
            <Toggle
              on={!!cfg.auto_send_enabled}
              onChange={(v) => patch({ auto_send_enabled: v })}
            />
          </div>
          <div className="row">
            <div>
              <div className="t">Verbose</div>
              <div className="d">Log chi tiết từng user trong watchlist</div>
            </div>
            <Toggle
              on={!!cfg.auto_reply_verbose}
              onChange={(v) => patch({ auto_reply_verbose: v })}
            />
          </div>
          <div className="row">
            <div>
              <div className="t">Phạm vi auto-reply</div>
              <div className="d">Tất cả mọi người = quét hộp thư, ai nhắn cũng rep</div>
            </div>
            <Seg
              value={cfg.check_method || "inbox"}
              onChange={(v) => patch({ check_method: v })}
              options={[
                { v: "inbox", l: "TẤT CẢ MỌI NGƯỜI" },
                { v: "watchlist", l: "CHỈ WATCHLIST" },
              ]}
            />
          </div>
        </Card>

        <Card title="Thiết lập đang chạy">
          <div className="kv"><span className="k">Cooldown rep / user</span><span className="v">{cfg.auto_reply_cooldown_minutes ?? "—"} phút</span></div>
          <div className="kv"><span className="k">Bỏ qua tin cũ hơn</span><span className="v">{cfg.auto_reply_max_message_age_minutes ?? "—"} phút</span></div>
          <div className="kv"><span className="k">Chu kỳ quét</span><span className="v">{cfg.poll_interval_seconds ?? "—"} giây</span></div>
          <div className="kv"><span className="k">Delay giữa 2 tin gửi</span><span className="v">{cfg.send_delay_seconds ?? "—"} giây</span></div>
          <div className="kv"><span className="k">Số mẫu auto-reply</span><span className="v">{(cfg.auto_reply_messages || []).length}</span></div>
          <div className="kv"><span className="k">Webhook</span><span className="v">{cfg.webhook_url ? "đã bật" : "tắt"}</span></div>
          <div className="actions mt">
            <Link href="/auto-reply"><Btn variant="primary">Sửa auto-reply</Btn></Link>
            <Link href="/settings"><Btn>Cài đặt</Btn></Link>
          </div>
        </Card>
      </div>

      <div className="grid c2">
        <Card
          title={"Watchlist (" + wl.length + ")"}
          right={<Link href="/watchlist"><Btn className="sm">mở trang</Btn></Link>}
        >
          {wl.length === 0 && (
            <div className="empty">trống — thêm user ở trang Watchlist</div>
          )}
          {wl.length > 0 && (
            <div className="detect-users" style={{ marginTop: 0 }}>
              {wl.slice(0, 20).map((u) => (
                <span className="chip" key={u.username}>
                  <Ava src={u.avatar} name={u.username} size={18} /> @{u.username}
                </span>
              ))}
              {wl.length > 20 && (
                <span className="chip">+{wl.length - 20} nữa</span>
              )}
            </div>
          )}
          <div className="hint">
            Tự tải khi vào trang — user từ detect hội thoại ẩn cũng nằm đây.
            Ấn “Gửi tin” ở trang Gửi tin để dùng chung danh sách này.
          </div>
        </Card>

        <Card
          title="Chuỗi tin nhắn đang dùng"
          right={<Link href="/send"><Btn className="sm">sửa ở Gửi tin</Btn></Link>}
        >
          <div className="logs" style={{ maxHeight: "180px", whiteSpace: "pre-wrap" }}>
            {cfg.send_message_content || "— trống —"}
          </div>
          <div className="hint">
            Biến <code>{"{nickname}"}</code> <code>{"{username}"}</code> tự thay
            khi gửi. Preview nguyên văn như trên — gửi lên TikTok cũng đúng từng
            dòng này.
          </div>
        </Card>
      </div>

      <Card
        title="Phát hiện hội thoại ẩn"
        right={
          <div className="actions">
            <Toggle
              on={!!(st && st.detect && st.detect.enabled)}
              onChange={(v) => patch({ hidden_detect_enabled: v })}
            />
            <Btn
              className="sm"
              variant="primary"
              onClick={runDetect}
              disabled={!st || !st.detect || st.detect.running}
            >
              {st && st.detect && st.detect.running ? "đang quét…" : "Quét ngay"}
            </Btn>
          </div>
        }
      >
        <div className="grid c4" style={{ marginBottom: 0 }}>
          <div className="kv">
            <span className="k">Tổng tìm thấy</span>
            <span className="v">{st && st.detect ? st.detect.found_total : 0}</span>
          </div>
          <div className="kv">
            <span className="k">Lần quét cuối</span>
            <span className="v">
              {st && st.detect ? fmtTime(st.detect.last_run) : "—"}
            </span>
          </div>
          <div className="kv">
            <span className="k">Chu kỳ</span>
            <span className="v">
              {st && st.detect ? st.detect.interval_minutes + " phút" : "—"}
            </span>
          </div>
          <div className="kv">
            <span className="k">Tự thêm watchlist</span>
            <span className="v">
              {st && st.detect && st.detect.auto_add ? "BẬT" : "TẮT"}
            </span>
          </div>
        </div>
        {st && st.detect && (st.detect.last_users || []).length > 0 && (
          <div className="detect-users">
            {st.detect.last_users.slice(0, 12).map((u) => (
              <span className="chip" key={u}>@{u}</span>
            ))}
          </div>
        )}
        <div className="hint">
          Quét tab “Yêu cầu tin nhắn” + API nội bộ + sidebar: thread không hiện
          trên PC nhưng vẫn có uid sẽ bị bắt, tự resolve uid/avatar và kéo vào
          auto-reply.
        </div>
      </Card>

      <Card
        title="Nhật ký gần nhất"
        right={<Link href="/logs"><Btn className="sm">mở toàn bộ</Btn></Link>}
      >
        <div className="logs">
          {logs.length === 0 && <span className="ln lg-dim">— trống —</span>}
          {logs.map((l, i) => (
            <span key={i} className={"ln " + lineClass(l)}>
              {l}
            </span>
          ))}
        </div>
      </Card>
    </>
  );
}
