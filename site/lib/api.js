"use client";

async function req(method, path, body) {
  const opt = { method, cache: "no-store" };
  if (body !== undefined) {
    opt.headers = { "Content-Type": "application/json" };
    opt.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch("/api/bot" + path, opt);
  } catch (e) {
    throw new Error("mất kết nối tới worker: " + e.message);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new Error((data && (data.error || data.detail)) || "HTTP " + res.status);
  }
  return data;
}

export const api = {
  get: (p) => req("GET", p),
  post: (p, b) => req("POST", p, b === undefined ? {} : b),
  put: (p, b) => req("PUT", p, b === undefined ? {} : b),
  del: (p) => req("DELETE", p),
};

export function fmtUptime(sec) {
  if (!sec && sec !== 0) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return h + "h " + m + "m";
  if (m > 0) return m + "m " + Math.floor(sec % 60) + "s";
  return Math.floor(sec) + "s";
}
