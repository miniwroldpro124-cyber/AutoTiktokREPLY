"use client";

// Nhận diện mọi dạng dán vào: JSON cookie, document.cookie, EditThisCookie, token trần.
const IMPORTANT = [
  "sessionid",
  "sessionid_ss",
  "sid_tt",
  "uid_tt",
  "uid_tt_ss",
  "tt_csrf_token",
  "msToken",
];

function summarize(cookies) {
  const names = cookies.map((c) => c.name);
  return {
    ok: true,
    count: cookies.length,
    cookies,
    has_sessionid: names.includes("sessionid") || names.includes("sessionid_ss"),
    found: IMPORTANT.filter((n) => names.includes(n)),
    missing: IMPORTANT.filter((n) => !names.includes(n)),
  };
}

export function parseTokenInput(raw) {
  const s = (raw || "").trim();
  if (!s) return { ok: false, error: "chưa có dữ liệu — dán cookie/token vào trước" };

  if (s.startsWith("{") || s.startsWith("[")) {
    let d;
    try {
      d = JSON.parse(s);
    } catch {
      return { ok: false, error: "JSON lỗi cú pháp — kiểm tra lại dấu phẩy/ngoặc" };
    }
    const list = Array.isArray(d)
      ? d
      : Array.isArray(d.cookies)
        ? d.cookies
        : null;
    if (list) {
      const cookies = list
        .filter((c) => c && c.name != null && c.value != null)
        .map((c) => ({
          name: String(c.name),
          value: String(c.value),
          domain: c.domain || ".tiktok.com",
        }));
      if (!cookies.length) return { ok: false, error: "JSON không có field name/value" };
      return summarize(cookies);
    }
    if (d && typeof d === "object") {
      if (d.name && d.value) {
        return summarize([
          { name: String(d.name), value: String(d.value), domain: d.domain || ".tiktok.com" },
        ]);
      }
      const cookies = Object.entries(d)
        .filter(
          ([k, v]) =>
            !k.startsWith("_") &&
            (typeof v === "string" || typeof v === "number")
        )
        .map(([k, v]) => ({ name: k, value: String(v), domain: ".tiktok.com" }));
      if (cookies.length) return summarize(cookies);
    }
    return { ok: false, error: "không nhận diện được JSON này" };
  }

  // document.cookie / header Cookie: "a=b; c=d"
  if (s.includes("=") && /[;\s]/.test(s)) {
    const cookies = s
      .split(/;\s*/)
      .map((p) => p.trim())
      .filter((p) => p.includes("="))
      .map((p) => {
        const i = p.indexOf("=");
        return {
          name: p.slice(0, i).trim(),
          value: p.slice(i + 1).trim(),
          domain: ".tiktok.com",
        };
      })
      .filter((c) => c.name && c.value);
    if (cookies.length) return summarize(cookies);
  }

  // token trần (sessionid hoặc giá trị cookie đơn)
  if (/^[A-Za-z0-9._%+-]{16,}$/.test(s)) {
    return summarize([{ name: "sessionid", value: s, domain: ".tiktok.com" }]);
  }

  return {
    ok: false,
    error: "không nhận diện được — hỗ trợ: JSON cookie, document.cookie, token sessionid",
  };
}
