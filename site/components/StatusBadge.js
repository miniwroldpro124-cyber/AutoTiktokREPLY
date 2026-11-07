"use client";

import { useEffect, useState } from "react";
import Ava from "./Ava";

export default function StatusBadge() {
  const [s, setS] = useState(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch("/api/bot/status", { cache: "no-store" });
        const d = await r.json();
        if (alive) setS(d);
      } catch {
        if (alive) setS({ error: true });
      }
    };
    tick();
    const id = setInterval(tick, 8000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (!s || s.error) return <span className="pill off">WORKER OFFLINE</span>;
  if (!s.live)
    return (
      <span className="pill warn">
        {s.boot && s.boot.state === "starting" ? "ĐANG KHỞI ĐỘNG…" : "CHƯA LOGIN"}
      </span>
    );
  return (
    <span className="pill live" style={{ paddingLeft: 4 }}>
      <Ava src={s.avatar} name={s.username} size={20} />
      @{s.username || "live"}
      {s.nickname ? " · " + s.nickname : ""}
    </span>
  );
}
