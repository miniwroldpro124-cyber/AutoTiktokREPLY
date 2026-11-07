import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const UP = (process.env.WORKER_URL || "").replace(/\/+$/, "");
const KEY = process.env.WORKER_API_KEY || "";

async function proxy(request, { params }) {
  if (!UP) {
    return NextResponse.json(
      { error: "WORKER_URL chưa được set trên Vercel (Settings → Environment Variables)" },
      { status: 502 }
    );
  }

  const slug = (params && params.slug ? params.slug : []).join("/");
  const target = UP + "/api/" + slug + (request.nextUrl.search || "");

  const init = {
    method: request.method,
    cache: "no-store",
    headers: {},
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
    init.headers["content-type"] =
      request.headers.get("content-type") || "application/json";
  }
  if (KEY) init.headers["x-api-key"] = KEY;

  try {
    const r = await fetch(target, init);
    const text = await r.text();
    const ct = r.headers.get("content-type") || "application/json";
    return new NextResponse(text, {
      status: r.status,
      headers: { "content-type": ct, "cache-control": "no-store" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: "worker không phản hồi: " + (e && e.message ? e.message : e) },
      { status: 502 }
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
