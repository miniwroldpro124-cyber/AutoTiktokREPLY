"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { Card, Btn, Field } from "../../components/ui";
import Ava from "../../components/Ava";
import { toast } from "../../components/Toast";

export default function WatchlistPage() {
  const [users, setUsers] = useState(null);
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // tra cứu link → uid (item: auto get userid = link)
  const [lkInput, setLkInput] = useState("");
  const [lkBusy, setLkBusy] = useState(false);
  const [lkRes, setLkRes] = useState(null);
  const [lkErr, setLkErr] = useState("");

  const lookupLink = async () => {
    if (!lkInput.trim()) return;
    setLkBusy(true);
    setLkErr("");
    setLkRes(null);
    try {
      const d = await api.post("/lookup", { input: lkInput.trim() });
      setLkRes(d);
      toast(d.uid ? "@" + d.username + " → uid " + d.uid : "không lấy được uid");
    } catch (e) {
      setLkErr(e.message);
    } finally {
      setLkBusy(false);
    }
  };

  const load = useCallback(async () => {
    try {
      const d = await api.get("/watchlist");
      setUsers(d.users || []);
      setErr("");
    } catch (e) {
      setErr(e.message);
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const add = async () => {
    if (!raw.trim()) return;
    setBusy(true);
    try {
      const d = await api.post("/watchlist", { users: raw });
      toast("đã thêm " + ((d.added || []).length) + " user");
      setRaw("");
      await load();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (u) => {
    try {
      await api.del("/watchlist/" + encodeURIComponent(u));
      toast("đã xóa @" + u);
      await load();
    } catch (e) {
      toast(e.message, "err");
    }
  };

  const clear = async () => {
    if (!confirm("Xóa HẾT watchlist?")) return;
    try {
      await api.del("/watchlist");
      toast("đã xóa hết");
      await load();
    } catch (e) {
      toast(e.message, "err");
    }
  };

  const lookup = async () => {
    setBusy(true);
    try {
      const d = await api.post("/watchlist/lookup", {});
      if (d.queued) {
        toast("đang resolve " + d.queued + " user — tự cập nhật sau ~30s");
        setTimeout(load, 9000);
        setTimeout(load, 28000);
      } else {
        toast("tất cả đã có uid");
      }
      await load();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="page-h">
        <h1>Watchlist</h1>
        <p>Những user bot theo dõi và trả lời khi check method = WATCHLIST.</p>
      </div>

      {err && <div className="banner"><b>Worker offline.</b> — {err}</div>}

      <Card title="Tra cứu link → UID">
        <Field
          label="Dán link TikTok"
          hint="Link hồ sơ tiktok.com/@user, link ngắn vm/vt.tiktok.com, hoặc username — tự resolve uid + nickname + avatar."
        >
          <div className="actions" style={{ marginTop: 0 }}>
            <input
              className="inp mono"
              value={lkInput}
              placeholder="https://www.tiktok.com/@user  hoặc  https://vm.tiktok.com/xxxxx"
              onChange={(e) => setLkInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && lookupLink()}
            />
            <Btn variant="primary" onClick={lookupLink} disabled={lkBusy || !lkInput.trim()}>
              {lkBusy ? "đang tra…" : "Tra cứu UID"}
            </Btn>
          </div>
        </Field>
        {lkErr && <div className="hint" style={{ color: "var(--red)" }}>{lkErr}</div>}
        {lkRes && (
          <div className="li" style={{ marginTop: 8 }}>
            <Ava src={lkRes.avatar} name={lkRes.username} size={34} />
            <div className="grow">
              <div className="name">@{lkRes.username}</div>
              <div className="meta">
                {lkRes.uid ? "uid " + lkRes.uid : "uid chưa lấy được"}
                {lkRes.nickname ? " · " + lkRes.nickname : ""}
              </div>
            </div>
            {lkRes.uid ? (
              <span className="pill live">OK</span>
            ) : (
              <span className="pill warn">fail</span>
            )}
          </div>
        )}
        <div className="hint">
          Muốn thêm user này vào danh sách thì dán username vào ô bên dưới —
          bot tự resolve uid khi thêm.
        </div>
      </Card>

      <div className="mt" />

      <Card title="Thêm user">
        <Field
          label="Dán username"
          hint="Mỗi dòng một user, hoặc tách bằng dấu phẩy/chấm phẩy. Dán cả link tiktok.com/@user cũng được — bot tự parse."
        >
          <textarea
            className="inp"
            rows={4}
            value={raw}
            placeholder={"nguyenvana\n@thib, tiktok.com/@onkias\nuser.1110211_"}
            onChange={(e) => setRaw(e.target.value)}
          />
        </Field>
        <div className="actions">
          <Btn variant="primary" onClick={add} disabled={busy || !raw.trim()}>
            {busy ? "đang thêm…" : "Thêm vào watchlist"}
          </Btn>
          <Btn onClick={lookup} disabled={busy}>
            Resolve UID còn thiếu
          </Btn>
          {users && users.length > 0 && (
            <Btn variant="danger" onClick={clear}>Xóa hết</Btn>
          )}
        </div>
      </Card>

      <div className="mt" />

      <Card
        title={"Danh sách (" + (users ? users.length : "…" ) + ")"}
        right={<Btn className="sm" onClick={load}>refresh</Btn>}
      >
        {!users && <div className="empty">đang tải…</div>}
        {users && users.length === 0 && <div className="empty">watchlist trống</div>}
        {users &&
          users.map((u, i) => (
            <div className="li" key={u.username}>
              <Ava src={u.avatar} name={u.username} size={34} />
              <div className="num">{i + 1}</div>
              <div className="grow">
                <div className="name">@{u.username}</div>
                <div className="meta">
                  {u.uid ? "uid " + u.uid : "uid chưa resolve"}
                  {u.nickname ? " · " + u.nickname : ""}
                </div>
              </div>
              {!u.uid && <span className="pill warn">chờ uid</span>}
              <Btn className="sm danger" onClick={() => remove(u.username)}>
                xóa
              </Btn>
            </div>
          ))}
      </Card>
    </>
  );
}
