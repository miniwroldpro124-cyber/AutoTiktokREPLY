"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { parseTokenInput } from "../../lib/token";
import { Card, Toggle, Btn, Field } from "../../components/ui";
import Ava from "../../components/Ava";
import { toast } from "../../components/Toast";

export default function SettingsPage() {
  const [cfg, setCfg] = useState(null);
  const [raw, setRaw] = useState("");
  const [parsed, setParsed] = useState(null);
  const [acc, setAcc] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [fileName, setFileName] = useState("");
  const fileRef = useRef(null);

  useEffect(() => {
    api
      .get("/config")
      .then((d) => setCfg(d.config))
      .catch((e) => setErr(e.message));
    api
      .get("/status")
      .then(setAcc)
      .catch(() => {});
  }, []);

  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

  const onRaw = (v) => {
    setRaw(v);
    setParsed(v.trim() ? parseTokenInput(v) : null);
  };

  const onFile = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      onRaw(String(rd.result || ""));
      setFileName(f.name);
      toast("đã đọc " + f.name);
    };
    rd.onerror = () => toast("đọc file lỗi", "err");
    rd.readAsText(f);
    e.target.value = "";
  };

  const importToken = async () => {
    const p = parseTokenInput(raw);
    if (!p.ok) {
      toast(p.error, "err");
      return;
    }
    setBusy(true);
    try {
      const d = await api.post("/auth/import", { raw });
      toast(d.message || "đã nhập token — đang làm lại session");
      setRaw("");
      setParsed(null);
      let tries = 0;
      const poll = setInterval(async () => {
        tries += 1;
        try {
          const s = await api.get("/status");
          setAcc(s);
          if (s.live || tries >= 8) clearInterval(poll);
        } catch {
          if (tries >= 8) clearInterval(poll);
        }
      }, 5000);
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  };

  const testLogin = async () => {
    setBusy(true);
    try {
      const d = await api.post("/auth/test", {});
      setAcc(d);
      toast(d.live ? "login OK @" + d.username : "chưa login — token hết hạn?");
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    try {
      const payload = {
        webhook_url: cfg.webhook_url || "",
        headless: !!cfg.headless,
        browser_channel: cfg.browser_channel || "",
        user_agent: cfg.user_agent || "",
        hidden_detect_enabled: cfg.hidden_detect_enabled !== false,
        hidden_detect_auto_add: cfg.hidden_detect_auto_add !== false,
        hidden_detect_interval_minutes: Math.max(
          2,
          Number(cfg.hidden_detect_interval_minutes) || 10
        ),
      };
      await api.put("/config", payload);
      toast("đã lưu cài đặt");
    } catch (e) {
      toast(e.message, "err");
    }
  };

  if (err) {
    return (
      <>
        <div className="page-h"><h1>Cài đặt</h1></div>
        <div className="banner"><b>Worker offline.</b> — {err}</div>
      </>
    );
  }
  if (!cfg) {
    return (
      <>
        <div className="page-h"><h1>Cài đặt</h1></div>
        <div className="empty">đang tải…</div>
      </>
    );
  }

  return (
    <>
      <div className="page-h">
        <h1>Cài đặt</h1>
        <p>Token login TikTok, webhook, trình duyệt, auto-send.</p>
      </div>

      <div className="grid c2">
        <Card
          title="Token / Cookie TikTok"
          right={
            acc ? (
              <span className={"pill " + (acc.live ? "live" : "off")}>
                {acc.live ? "@" + acc.username : "CHƯA LOGIN"}
              </span>
            ) : null
          }
        >
          <Field
            label="Dán cookie hoặc token"
            hint="Nhận mọi định dạng: JSON từ EditThisCookie, chuỗi document.cookie, hoặc chỉ giá trị sessionid. Token hết hạn thì dán lại là bot tự nạp lại session. Cookie được mã hóa AES (cookies.enc) lưu trên worker — không bao giờ nằm plaintext trên đĩa."
          >
            <textarea
              className="inp mono"
              rows={7}
              value={raw}
              placeholder={'sessionid=xxxx; sessionid_ss=xxxx; uid_tt=xxxx\nhoặc\n[{"name":"sessionid","value":"..."}]'}
              onChange={(e) => onRaw(e.target.value)}
            />
          </Field>

          <input
            ref={fileRef}
            type="file"
            accept=".json,.txt,application/json,text/plain"
            aria-label="Tải file cookie"
            style={{
              position: "absolute",
              width: 1,
              height: 1,
              opacity: 0,
              pointerEvents: "none",
            }}
            onChange={onFile}
          />
          <div className="actions" style={{ marginTop: 0 }}>
            <Btn onClick={() => fileRef.current && fileRef.current.click()}>
              Tải file cookie (.json)
            </Btn>
            {fileName && (
              <span className="hint" style={{ alignSelf: "center" }}>
                {fileName}
              </span>
            )}
          </div>

          {parsed && parsed.ok && (
            <div className="mt" style={{ marginTop: 0 }}>
              <div className="kv">
                <span className="k">Nhận diện</span>
                <span className="v">{parsed.count} cookie</span>
              </div>
              <div className="chips" style={{ marginTop: 10 }}>
                {parsed.found.map((n) => (
                  <span className="chip" key={n}>{n}</span>
                ))}
                {parsed.missing.map((n) => (
                  <span className="chip miss" key={n}>thiếu {n}</span>
                ))}
              </div>
              {!parsed.has_sessionid && (
                <div className="hint" style={{ color: "var(--yellow)" }}>
                  Không thấy sessionid — nhiều khả năng không login được.
                </div>
              )}
            </div>
          )}
          {parsed && !parsed.ok && (
            <div className="hint" style={{ color: "var(--red)" }}>{parsed.error}</div>
          )}

          <div className="actions mt">
            <Btn variant="primary" onClick={importToken} disabled={busy || !raw.trim()}>
              {busy ? "đang xử lý…" : "Nhập vào worker"}
            </Btn>
            <Btn onClick={testLogin} disabled={busy}>Kiểm tra login</Btn>
          </div>

          {acc && (
            <div className="mt">
              <div className="ava-row" style={{ marginBottom: 10 }}>
                <Ava src={acc.avatar} name={acc.username || "?"} size={44} />
                <div>
                  <div style={{ fontWeight: 700 }}>
                    {acc.live ? "@" + acc.username : "chưa login"}
                  </div>
                  <div className="hint" style={{ marginTop: 2 }}>
                    {acc.nickname || (acc.live ? "session sống" : "dán token ở trên")}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>

        <Card title="Trình duyệt & thông báo">
          <div className="row">
            <div>
              <div className="t">Headless</div>
              <div className="d">Ẩn cửa sổ Chrome trên worker</div>
            </div>
            <Toggle on={!!cfg.headless} onChange={(v) => set("headless", v)} />
          </div>
          <Field label="Browser channel" hint="chrome / msedge / bỏ trống = chromium bundled">
            <input
              className="inp"
              value={cfg.browser_channel || ""}
              placeholder="chrome"
              onChange={(e) => set("browser_channel", e.target.value)}
            />
          </Field>
          <Field label="User-Agent">
            <input
              className="inp mono"
              value={cfg.user_agent || ""}
              onChange={(e) => set("user_agent", e.target.value)}
            />
          </Field>
          <Field label="Discord webhook" hint="Nhận thông báo khi có tin mới / đã rep / đã gửi">
            <input
              className="inp mono"
              value={cfg.webhook_url || ""}
              placeholder="https://discord.com/api/webhooks/..."
              onChange={(e) => set("webhook_url", e.target.value)}
            />
          </Field>
        </Card>
      </div>

      <div className="mt" />

      <Card title="Phát hiện hội thoại ẩn">
        <div className="row">
          <div>
            <div className="t">Tự quét định kỳ</div>
            <div className="d">
              Quét tab “Yêu cầu tin nhắn” + API nội bộ + sidebar — thread không
              hiện trên PC nhưng vẫn có uid sẽ bị bắt
            </div>
          </div>
          <Toggle
            on={cfg.hidden_detect_enabled !== false}
            onChange={(v) => set("hidden_detect_enabled", v)}
          />
        </div>
        <div className="row">
          <div>
            <div className="t">Tự thêm vào watchlist</div>
            <div className="d">
              User mới tìm thấy bị kéo vào watchlist, resolve uid + avatar, auto-reply luôn
            </div>
          </div>
          <Toggle
            on={cfg.hidden_detect_auto_add !== false}
            onChange={(v) => set("hidden_detect_auto_add", v)}
          />
        </div>
        <Field label="Chu kỳ quét (phút)">
          <input
            className="inp"
            type="number"
            min="2"
            max="1440"
            value={cfg.hidden_detect_interval_minutes ?? 10}
            onChange={(e) =>
              set(
                "hidden_detect_interval_minutes",
                Math.max(2, parseInt(e.target.value, 10) || 10)
              )
            }
          />
        </Field>
      </Card>

      <div className="hint" style={{ marginTop: 12 }}>
        Auto-send định kỳ đã chuyển sang trang <b>Gửi tin</b> — cấu hình giờ
        gửi, nội dung và danh sách người nhận ở đó.
      </div>
    </>
  );
}
