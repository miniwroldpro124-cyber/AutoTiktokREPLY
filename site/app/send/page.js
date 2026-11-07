"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../../lib/api";
import { Card, Btn, Field, Toggle, Seg } from "../../components/ui";
import Ava from "../../components/Ava";
import { toast } from "../../components/Toast";

function preview(tpl) {
  return (tpl || "")
    .replace(/\{nickname\}/g, "Nguyễn Văn A")
    .replace(/\{@username\}/g, "@user123")
    .replace(/\{username\}/g, "user123");
}

const TARGET_MODES = [
  { v: "watchlist", l: "WATCHLIST" },
  { v: "manual", l: "TAY" },
  { v: "cache", l: "ALL CACHE" },
];

export default function SendPage() {
  const [cfg, setCfg] = useState(null);
  const [targets, setTargets] = useState("");
  const [msg, setMsg] = useState("");
  const [delay, setDelay] = useState(8);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

  // watchlist chung
  const [wl, setWl] = useState([]);
  const [mode, setMode] = useState("watchlist");
  const [picked, setPicked] = useState({}); // username -> true

  // auto-send định kỳ (chuyển từ Cài đặt sang đây)
  const [asOn, setAsOn] = useState(false);
  const [asTime, setAsTime] = useState("00:00");
  const [asTz, setAsTz] = useState(7);
  const [asMsg, setAsMsg] = useState("");
  const [asTargets, setAsTargets] = useState("cache");
  const [asList, setAsList] = useState("");
  const [asSaving, setAsSaving] = useState(false);
  const [recipients, setRecipients] = useState(null); // preview người sẽ nhận

  useEffect(() => {
    api
      .get("/config")
      .then((d) => {
        const c = d.config || {};
        setCfg(c);
        setMsg(c.send_message_content || "");
        setDelay(Number(c.send_delay_seconds) || 8);
        setAsOn(!!c.auto_send_enabled);
        setAsTime(c.auto_send_time || "00:00");
        setAsTz(Number(c.auto_send_timezone_offset) || 7);
        setAsMsg(c.auto_send_message || "");
        const t = c.auto_send_targets;
        if (Array.isArray(t)) {
          setAsTargets("list");
          setAsList(t.join("\n"));
        } else {
          setAsTargets(t === "watchlist" ? "watchlist" : "cache");
          setAsList("");
        }
      })
      .catch((e) => setErr(e.message));
    api
      .get("/watchlist")
      .then((d) => {
        const users = d.users || [];
        setWl(users);
        const p = {};
        users.forEach((u) => (p[u.username] = true));
        setPicked(p); // mặc định: tick hết watchlist
      })
      .catch(() => {});
  }, []);

  // ---- preview người auto-send sẽ nhận (item 7) ----
  useEffect(() => {
    let dead = false;
    const run = async () => {
      try {
        if (asTargets === "watchlist") {
          if (!dead) setRecipients(wl);
          return;
        }
        if (asTargets === "list") {
          const names = asList
            .split(/[\s,;]+/)
            .map((s) => s.replace(/^@/, "").trim())
            .filter(Boolean);
          const d = await api.get("/users");
          const cache = d.users || [];
          const map = {};
          cache.forEach((u) => (map[u.username] = u));
          if (!dead)
            setRecipients(
              names.map(
                (n) =>
                  map[n] || { username: n, uid: "", nickname: "", avatar: "" }
              )
            );
          return;
        }
        const d = await api.get("/users");
        if (!dead) setRecipients(d.users || []);
      } catch {
        if (!dead) setRecipients([]);
      }
    };
    run();
    return () => {
      dead = true;
    };
  }, [asTargets, asList, wl]);

  const chosen = wl.filter((u) => picked[u.username]);

  const toggle = (name) =>
    setPicked((p) => ({ ...p, [name]: !p[name] }));

  const pickAll = (v) => {
    const p = {};
    wl.forEach((u) => (p[u.username] = v));
    setPicked(p);
  };

  const send = async (kind) => {
    let t = "";
    if (kind === "all") t = "*";
    else if (mode === "watchlist") t = chosen.map((u) => u.username).join("\n");
    else t = targets;
    if (!t.trim()) {
      toast(
        mode === "watchlist" ? "chưa tick user nào" : "nhập target trước",
        "err"
      );
      return;
    }
    if (!msg.trim()) {
      toast("nhập nội dung trước", "err");
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const d = await api.post("/send", {
        targets: t,
        message: msg,
        delay_seconds: Number(delay) || 8,
      });
      setResult(d);
      toast(d.message || ("đã xếp hàng " + (d.queued || 0) + " target"));
    } catch (e) {
      toast(e.message, "err");
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const saveAutoSend = async () => {
    setAsSaving(true);
    try {
      const payload = {
        auto_send_enabled: !!asOn,
        auto_send_time: asTime || "00:00",
        auto_send_timezone_offset: Number(asTz) || 7,
        auto_send_message: asMsg,
        auto_send_targets:
          asTargets === "list"
            ? asList
                .split(/[\s,;]+/)
                .map((s) => s.replace(/^@/, "").trim())
                .filter(Boolean)
            : asTargets,
      };
      await api.put("/config", payload);
      setCfg((c) => ({ ...(c || {}), ...payload }));
      toast("đã lưu auto-send");
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setAsSaving(false);
    }
  };

  return (
    <>
      <div className="page-h">
        <h1>Gửi tin</h1>
        <p>
          Gửi DM hàng loạt — nguồn target dùng chung với Watchlist, kèm auto-send
          định kỳ.
        </p>
      </div>

      {err && <div className="banner"><b>Lỗi:</b> {err}</div>}

      <div className="grid c2">
        <Card
          title="Target"
          right={
            <Seg value={mode} onChange={setMode} options={TARGET_MODES} />
          }
        >
          {mode === "watchlist" && (
            <>
              <div className="row" style={{ paddingTop: 0 }}>
                <div>
                  <div className="t">
                    Chọn từ watchlist ({chosen.length}/{wl.length})
                  </div>
                  <div className="d">
                    Tick user muốn gửi — danh sách lấy từ trang Watchlist
                  </div>
                </div>
                <div className="actions">
                  <Btn className="sm" onClick={() => pickAll(true)}>
                    chọn hết
                  </Btn>
                  <Btn className="sm" onClick={() => pickAll(false)}>
                    bỏ chọn
                  </Btn>
                </div>
              </div>
              {wl.length === 0 && (
                <div className="empty">
                  watchlist trống —{" "}
                  <Link href="/watchlist">thêm user</Link> trước
                </div>
              )}
              <div className="detect-users" style={{ marginTop: 0 }}>
                {wl.map((u) => (
                  <span
                    key={u.username}
                    className={"chip" + (picked[u.username] ? "" : " off")}
                    style={{ cursor: "pointer", opacity: picked[u.username] ? 1 : 0.45 }}
                    onClick={() => toggle(u.username)}
                  >
                    <Ava src={u.avatar} name={u.username} size={18} /> @{u.username}
                    {u.uid ? "" : " · chờ uid"}
                  </span>
                ))}
              </div>
            </>
          )}

          {mode === "manual" && (
            <Field
              label="Username"
              hint="Mỗi dòng một user, tách bằng phẩy. Link tiktok.com/@user và link ngắn vm/vt.tiktok.com tự parse + resolve uid."
            >
              <textarea
                className="inp"
                rows={6}
                value={targets}
                placeholder={"koquaivuive\nbomaylakeii, h.anh.nguyen64\nhttps://www.tiktok.com/@user"}
                onChange={(e) => setTargets(e.target.value)}
              />
            </Field>
          )}

          {mode === "cache" && (
            <Field
              label="Username"
              hint="Điền * để gửi toàn bộ UID cache. Cache = mọi user bot đã từng thấy (inbox, detect, watchlist)."
            >
              <textarea
                className="inp"
                rows={6}
                value={targets}
                placeholder={"*"}
                onChange={(e) => setTargets(e.target.value)}
              />
            </Field>
          )}

          <Field label="Delay giữa 2 tin (giây)">
            <input
              className="inp"
              type="number"
              min="2"
              max="300"
              value={delay}
              onChange={(e) => setDelay(e.target.value)}
            />
          </Field>

          <div className="actions">
            <Btn variant="pink" onClick={() => send(false)} disabled={busy}>
              {busy
                ? "đang gửi…"
                : mode === "watchlist"
                  ? "Gửi " + chosen.length + " user đã tick"
                  : "Gửi tin"}
            </Btn>
            <Btn onClick={() => send("all")} disabled={busy}>
              Gửi ALL cache
            </Btn>
          </div>
        </Card>

        <Card title="Nội dung">
          <Field label="Tin nhắn" hint="Biến: {nickname} {username} {@username}">
            <textarea
              className="inp"
              rows={10}
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
            />
          </Field>
          <span className="lab">Preview chuỗi</span>
          <div className="logs" style={{ maxHeight: "180px", whiteSpace: "pre-wrap" }}>
            {preview(msg) || "— trống —"}
          </div>
        </Card>
      </div>

      <div className="mt" />

      <Card
        title="Auto-send định kỳ"
        right={
          <div className="actions">
            <Toggle on={asOn} onChange={setAsOn} />
          </div>
        }
      >
        <div className="row" style={{ paddingTop: 0 }}>
          <div>
            <div className="t">Gửi tin theo lịch mỗi ngày</div>
            <div className="d">
              {asOn
                ? "đang bật — " + asTime + " GMT+" + asTz
                : "tắt — bật switch để gửi theo giờ"}
            </div>
          </div>
        </div>

        <div className="grid c2" style={{ marginBottom: 0 }}>
          <Field label="Giờ gửi (HH:MM)">
            <input
              className="inp"
              value={asTime}
              placeholder="00:00"
              onChange={(e) => setAsTime(e.target.value)}
            />
          </Field>
          <Field label="Timezone offset (GMT+)">
            <input
              className="inp"
              type="number"
              min="-12"
              max="14"
              value={asTz}
              onChange={(e) => setAsTz(e.target.value)}
            />
          </Field>
        </div>

        <Field
          label="Nội dung custom"
          hint="Để trống = dùng chuỗi gửi mặc định ở ô bên trên."
        >
          <textarea
            className="inp"
            rows={3}
            value={asMsg}
            onChange={(e) => setAsMsg(e.target.value)}
          />
        </Field>

        <Field label="Gửi cho ai">
          <Seg
            value={asTargets}
            onChange={setAsTargets}
            options={[
              { v: "watchlist", l: "WATCHLIST" },
              { v: "cache", l: "ALL CACHE" },
              { v: "list", l: "DANH SÁCH RIÊNG" },
            ]}
          />
        </Field>
        {asTargets === "list" && (
          <Field label="Danh sách riêng" hint="Mỗi dòng một username">
            <textarea
              className="inp"
              rows={3}
              value={asList}
              placeholder={"nguyenvana\nthib123"}
              onChange={(e) => setAsList(e.target.value)}
            />
          </Field>
        )}

        <span className="lab">
          Người sẽ nhận auto-send
          {recipients ? " (" + recipients.length + ")" : ""}
        </span>
        {!recipients && <div className="empty">đang tải…</div>}
        {recipients && recipients.length === 0 && (
          <div className="empty">danh sách trống</div>
        )}
        {recipients && recipients.length > 0 && (
          <div className="detect-users" style={{ marginTop: 0 }}>
            {recipients.slice(0, 30).map((u, i) => (
              <span className="chip" key={(u.username || "") + i}>
                <Ava src={u.avatar} name={u.username} size={18} /> @{u.username}
              </span>
            ))}
            {recipients.length > 30 && (
              <span className="chip">+{recipients.length - 30} nữa</span>
            )}
          </div>
        )}

        <div className="actions">
          <Btn variant="primary" onClick={saveAutoSend} disabled={asSaving}>
            {asSaving ? "đang lưu…" : "Lưu auto-send"}
          </Btn>
          <Link href="/logs">
            <Btn>Nhật ký</Btn>
          </Link>
        </div>
      </Card>

      {result && <div className="mt" />}
      {result && result.queued !== undefined && (
        <Card title="Đã xếp hàng">
          <div className="empty">
            {result.queued} target đang gửi lần lượt theo delay — mở Nhật ký
            để xem OK/FAIL từng user.
          </div>
          <div className="actions">
            <Link href="/logs">
              <Btn variant="primary">Mở nhật ký</Btn>
            </Link>
            <Btn onClick={() => setResult(null)}>đóng</Btn>
          </div>
        </Card>
      )}
      {result && (result.details || []).length > 0 && (
        <Card
          title={
            "Kết quả · " + (result.sent || 0) + " OK · " + (result.failed || 0) + " FAIL"
          }
        >
          {result.details.map((d, i) => (
            <div className="li" key={i}>
              <div className="grow">
                <div className="name">@{d.user}</div>
                <div className="meta">{d.note || (d.ok ? "đã gửi" : "thất bại")}</div>
              </div>
              <span className={"pill " + (d.ok ? "live" : "off")}>
                {d.ok ? "OK" : "FAIL"}
              </span>
            </div>
          ))}
        </Card>
      )}
    </>
  );
}
