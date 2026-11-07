"use client";

import { useEffect, useState } from "react";

export function toast(msg, kind) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("app-toast", { detail: { msg, kind } }));
}

export default function ToastHost() {
  const [t, setT] = useState(null);

  useEffect(() => {
    let timer = null;
    const on = (e) => {
      setT(e.detail);
      clearTimeout(timer);
      timer = setTimeout(() => setT(null), 2800);
    };
    window.addEventListener("app-toast", on);
    return () => {
      window.removeEventListener("app-toast", on);
      clearTimeout(timer);
    };
  }, []);

  if (!t) return null;
  return <div className={"toast" + (t.kind === "err" ? " err" : "")}>{t.msg}</div>;
}
