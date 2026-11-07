import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const url = (process.env.WORKER_URL || "").trim();
  return NextResponse.json({ ok: true, worker: !!url, has_key: !!(process.env.WORKER_API_KEY || "").trim() });
}
