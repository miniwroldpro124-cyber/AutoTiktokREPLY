#!/usr/bin/env python3
"""TikTok Auto Reply worker — HTTP API 24/7 cho panel Vercel.

- Chạy Playwright headless trong container, giữ session TikTok sống mãi
- Expose REST /api/* cho panel (status, config, watchlist, send, auth, logs)
- Auto-detect hội thoại ẩn (tab yêu cầu / API nội bộ / sidebar) → uid → rep
- Auto lấy avatar + nickname cho từng user, đẩy lên panel

Chạy:  python worker.py     (WORKER_PORT=8787, WORKER_API_KEY=...)
"""

import os
import re
import sys
import json
import time
import asyncio
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import tiktok_selfbot as bot

WORKDIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path):
    """Nạp file .env (KEY=VAL) vào os.environ — không đè env đã set sẵn."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k and k not in os.environ:
                    os.environ[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass


_load_dotenv(os.path.join(WORKDIR, ".env"))

HOST = os.environ.get("WORKER_HOST", "0.0.0.0")
PORT = int(os.environ.get("WORKER_PORT", "8787") or 8787)
API_KEY = os.environ.get("WORKER_API_KEY", "")
VERSION = "1.0.0"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# ============ log ring buffer ============
class LogHub:
    def __init__(self, cap=1500):
        self.lines = []
        self.cap = cap
        self.lk = threading.Lock()

    def add(self, line):
        line = ANSI_RE.sub("", str(line)).rstrip()
        if not line:
            return
        with self.lk:
            self.lines.append(line)
            if len(self.lines) > self.cap:
                del self.lines[: len(self.lines) - self.cap]

    def tail(self, n=500):
        with self.lk:
            return list(self.lines)[-max(1, min(int(n), self.cap)):]

    def clear(self):
        with self.lk:
            self.lines.clear()


LOGS = LogHub()


class Tee:
    def __init__(self, stream, hub):
        self.stream = stream
        self.hub = hub
        self.buf = ""

    def write(self, s):
        try:
            self.stream.write(s)
        except Exception:
            pass
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.hub.add(line)

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass

    def isatty(self):
        return False


# ============ bot runtime ============
class BotRuntime:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.cfg = bot.load_cfg()
        self.wl = bot.load_watchlist()
        self.tracker = bot.Tracker(
            int(self.cfg.get("auto_reply_cooldown_minutes", 20) or 20))
        self.stop = asyncio.Event()
        self.wlk = asyncio.Lock()
        self.plk = asyncio.Lock()
        self.last_msg_state = {}
        self.fail_logged = set()
        self.pw = self.browser = self.ctx = self.page = None
        self.started_at = time.time()
        self.boot = {"state": "starting", "error": ""}
        self.detect_state = {
            "last_run": 0, "found_total": 0, "last_users": [],
            "running": False,
        }
        self.hidden_seen = set()
        self.tasks = []

    # ---- thread bridges ----
    def submit(self, coro, timeout=120):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def spawn(self, coro):
        def _s():
            asyncio.ensure_future(coro)
        try:
            self.loop.call_soon_threadsafe(_s)
        except Exception:
            pass

    # ---- lifecycle ----
    def start(self):
        threading.Thread(target=self._run, daemon=True, name="bot-loop").start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._boot())
            self.loop.run_forever()
        except Exception as e:
            self.boot = {"state": "dead", "error": str(e)[:300]}
            LOGS.add("[FAIL] worker loop chết: " + str(e)[:200])
        finally:
            try:
                self.loop.close()
            except Exception:
                pass

    async def _boot(self):
        try:
            await self._open_session()
        except Exception as e:
            self.boot = {"state": "error", "error": str(e)[:300]}
            LOGS.add("[FAIL] mở session: " + str(e)[:200])
        self.tasks = [
            asyncio.create_task(self._reply_loop()),
            asyncio.create_task(self._send_loop()),
            asyncio.create_task(self._detect_loop()),
            asyncio.create_task(self._keepalive()),
        ]

    async def _open_session(self):
        self.boot = {"state": "starting", "error": ""}
        await self._close_session()
        bot.SELF_STATUS.update({
            "username": "", "nickname": "", "avatar": "",
            "live": False, "checked_at": 0,
        })
        self.pw, self.browser, self.ctx, self.page = \
            await bot.open_browser_and_page(self.cfg)
        try:
            await self.page.goto(
                "https://www.tiktok.com/?lang=" + bot.LANG,
                wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(6)
            await bot.refresh_self_status(self.page)
        except Exception:
            pass
        if (bot.SELF_STATUS.get("live") and bot.SELF_STATUS.get("username")
                and not bot.SELF_STATUS.get("avatar")):
            try:
                info = await bot.get_user_info(
                    self.page, bot.SELF_STATUS["username"])
                if info.get("avatar"):
                    bot.SELF_STATUS["avatar"] = info["avatar"]
            except Exception:
                pass
        self.boot = {"state": "ok", "error": ""}
        LOGS.add("[OK] session @" + str(bot.SELF_STATUS.get("username", "?")))

    async def _close_session(self):
        for obj in (self.ctx, self.browser):
            if obj is None:
                continue
            try:
                await obj.close()
            except Exception:
                pass
        if self.pw is not None:
            try:
                await self.pw.stop()
            except Exception:
                pass
        self.ctx = self.browser = self.pw = self.page = None

    async def restart_session(self):
        async with self.plk:
            await self._open_session()

    async def _keepalive(self):
        while not self.stop.is_set():
            await asyncio.sleep(60)
            if self.page is None or not bot.page_alive(self.page):
                if self.boot.get("state") == "ok":
                    LOGS.add("[WARN] session chết — tự mở lại")
                try:
                    await self._open_session()
                except Exception as e:
                    self.boot = {"state": "error", "error": str(e)[:300]}

    # ---- loops ----
    async def _reply_loop(self):
        LOGS.add("[INFO] auto-reply loop start")
        while not self.stop.is_set():
            page = self.page
            if page is None or not bot.page_alive(page):
                await asyncio.sleep(15)
                continue
            if not self.cfg.get("auto_reply_enabled"):
                await asyncio.sleep(5)
                continue
            if not bot.in_active_hours(self.cfg):
                await asyncio.sleep(30)
                continue
            try:
                async with self.plk:
                    if self.cfg.get("check_method", "inbox") == "inbox":
                        await bot.reply_inbox_method(
                            page, self.cfg, self.tracker,
                            self.last_msg_state, self.fail_logged)
                    else:
                        async with self.wlk:
                            wl_copy = list(self.wl)
                        await bot.auto_reply_watchlist(
                            page, self.cfg, self.tracker, self.stop,
                            wl_copy, self.last_msg_state, self.fail_logged)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if "closed" in str(e).lower():
                    break
                LOGS.add("[FAIL] reply: " + str(e)[:120])
            try:
                await asyncio.sleep(
                    int(self.cfg.get("poll_interval_seconds", 15) or 15))
            except asyncio.CancelledError:
                break

    async def _send_loop(self):
        while not self.stop.is_set():
            try:
                if not self.cfg.get("auto_send_enabled"):
                    await asyncio.sleep(10)
                    continue
                page = self.page
                if page is None or not bot.page_alive(page):
                    await asyncio.sleep(20)
                    continue
                try:
                    hh_s, mm_s = str(
                        self.cfg.get("auto_send_time", "00:00")).split(":")
                    hh, mm = int(hh_s), int(mm_s)
                except Exception:
                    hh, mm = 0, 0
                tz = int(self.cfg.get("auto_send_timezone_offset", 7) or 7)
                secs = bot.seconds_until_time(hh, mm, tz)
                LOGS.add("[auto-send] còn " + str(int(secs // 3600)) + "h"
                         + str(int((secs % 3600) // 60)) + "m → "
                         + str(hh).zfill(2) + ":" + str(mm).zfill(2))
                waited = 0.0
                while waited < secs and not self.stop.is_set():
                    chunk = min(60.0, secs - waited)
                    await asyncio.sleep(chunk)
                    waited += chunk
                if self.stop.is_set():
                    break
                async with self.wlk:
                    wl_copy = list(self.wl)
                async with self.plk:
                    await bot.do_auto_send(page, self.cfg, wl_copy)
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGS.add("[FAIL] auto-send: " + str(e)[:120])
                await asyncio.sleep(30)

    async def _detect_loop(self):
        while not self.stop.is_set():
            try:
                if not self.cfg.get("hidden_detect_enabled", True):
                    await asyncio.sleep(30)
                    continue
                page = self.page
                if page is None or not bot.page_alive(page):
                    await asyncio.sleep(30)
                    continue
                if not bot.in_active_hours(self.cfg):
                    await asyncio.sleep(60)
                    continue
                await self.run_detect()
                mins = max(2, int(
                    self.cfg.get("hidden_detect_interval_minutes", 10) or 10))
                await asyncio.sleep(mins * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGS.add("[FAIL] detect: " + str(e)[:120])
                await asyncio.sleep(60)

    async def run_detect(self):
        if self.detect_state.get("running"):
            return {"found": [], "added": [], "busy": True}
        self.detect_state["running"] = True
        try:
            async with self.plk:
                users = await bot.detect_hidden_conversations(self.page)
            fresh = [u for u in users if u not in self.hidden_seen]
            self.hidden_seen |= set(users)
            added = []
            if self.cfg.get("hidden_detect_auto_add", True):
                async with self.wlk:
                    for u in users:
                        if u not in self.wl:
                            self.wl.append(u)
                            added.append(u)
                    if added:
                        bot.save_watchlist(self.wl)
            for u in added:
                LOGS.add("     [DETECT] hội thoại ẩn @" + u + " → watchlist")
            if not users:
                LOGS.add("[INFO] detect: không thấy thread mới")
            self.detect_state.update({
                "last_run": time.time(),
                "found_total": self.detect_state.get("found_total", 0)
                + len(fresh),
                "last_users": users[:30],
                "running": False,
            })
            if added:
                self.spawn(self._resolve_users(added))
            return {"found": users, "added": added, "fresh": fresh}
        except Exception as e:
            self.detect_state["running"] = False
            LOGS.add("[FAIL] detect: " + str(e)[:120])
            return {"found": [], "added": [], "error": str(e)[:160]}

    async def _resolve_users(self, users):
        for u in users:
            try:
                async with self.plk:
                    info = await bot.get_user_info(self.page, u)
                if info.get("uid"):
                    LOGS.add("     [DETECT] @" + u + " → uid="
                             + str(info["uid"]) + " "
                             + str(info.get("nickname", "")))
                else:
                    LOGS.add("     [DETECT] @" + u + " → uid fail")
            except Exception as e:
                LOGS.add("     [DETECT] @" + u + " err " + str(e)[:60])
            await asyncio.sleep(1.5)


# ============ api ============
def api_status(rt):
    cfg = rt.cfg
    cache = bot.load_cache()
    av = bot.SELF_STATUS.get("avatar", "")
    if bot.SELF_STATUS.get("live") and bot.SELF_STATUS.get("username") \
            and not av:
        c = bot.get_cached(bot.SELF_STATUS["username"]) or {}
        av = c.get("avatar", "")
    return 200, {
        "live": bool(bot.SELF_STATUS.get("live")),
        "username": bot.SELF_STATUS.get("username", ""),
        "nickname": bot.SELF_STATUS.get("nickname", ""),
        "avatar": av,
        "watchlist": len(rt.wl),
        "uid_cache": len(cache),
        "config": cfg,
        "boot": rt.boot,
        "uptime_seconds": int(time.time() - rt.started_at),
        "bot_version": bot.VERSION,
        "worker_version": VERSION,
        "detect": {
            "enabled": bool(cfg.get("hidden_detect_enabled", True)),
            "interval_minutes": cfg.get("hidden_detect_interval_minutes", 10),
            "auto_add": bool(cfg.get("hidden_detect_auto_add", True)),
            "last_run": rt.detect_state.get("last_run", 0),
            "found_total": rt.detect_state.get("found_total", 0),
            "last_users": rt.detect_state.get("last_users", []),
            "running": bool(rt.detect_state.get("running")),
        },
    }


def api_config_put(rt, body):
    for k, v in (body or {}).items():
        rt.cfg[k] = v
    if "auto_reply_cooldown_minutes" in (body or {}):
        try:
            rt.tracker.cd = int(body["auto_reply_cooldown_minutes"]) * 60
        except Exception:
            pass
    bot.save_cfg(rt.cfg)
    return 200, {"config": rt.cfg, "saved": True}


def api_watchlist(rt, body):
    raw = (body or {}).get("users", "")
    if isinstance(raw, list):
        parsed = bot.parse_users(" ".join(str(x) for x in raw))
    else:
        parsed = bot.parse_users(raw)
    added = []
    for u in parsed:
        if u not in rt.wl:
            rt.wl.append(u)
            added.append(u)
    if added:
        bot.save_watchlist(rt.wl)
        rt.spawn(rt._resolve_users(added[:10]))
    return 200, {"added": added, "watchlist": list(rt.wl)}


def api_watchlist_users(rt):
    out = []
    for u in rt.wl:
        c = bot.get_cached(u) or {}
        out.append({
            "username": u,
            "uid": c.get("uid", ""),
            "nickname": c.get("nickname", ""),
            "avatar": c.get("avatar", ""),
        })
    return 200, {"users": out}


def api_watchlist_lookup(rt):
    missing = [u for u in rt.wl if not (bot.get_cached(u) or {}).get("uid")]
    if not missing:
        return 200, {"resolved": 0, "missing": 0, "queued": 0}

    async def _run():
        n = 0
        for u in missing:
            try:
                async with rt.plk:
                    info = await bot.get_user_info(rt.page, u)
                if info.get("uid"):
                    n += 1
                    LOGS.add("[OK] @" + u + " → uid=" + str(info["uid"]))
            except Exception as e:
                LOGS.add("[FAIL] @" + u + " " + str(e)[:60])
            await asyncio.sleep(1.2)
        LOGS.add("[OK] resolve xong " + str(n) + "/" + str(len(missing)))

    rt.spawn(_run())
    return 200, {"queued": len(missing), "missing": len(missing),
                 "message": "đang resolve " + str(len(missing)) + " user"}


def api_users(rt):
    cache = bot.load_cache()
    out = [{
        "username": u,
        "uid": v.get("uid", ""),
        "nickname": v.get("nickname", ""),
        "avatar": v.get("avatar", ""),
    } for u, v in sorted(cache.items())]
    return 200, {"users": out}


def api_send(rt, body):
    targets = (body or {}).get("targets", "")
    message = (body or {}).get("message") or rt.cfg.get(
        "send_message_content", "")
    try:
        delay = int((body or {}).get("delay_seconds") or 0)
    except Exception:
        delay = 0

    if isinstance(targets, str) and targets.strip() in ("*", "all", "ALL"):
        target_list = sorted(bot.load_cache().keys())
    else:
        target_list = targets

    old_delay = rt.cfg.get("send_delay_seconds", 8)
    if delay > 0:
        rt.cfg["send_delay_seconds"] = delay

    async def _run():
        try:
            async with rt.plk:
                res = await bot.send_many(
                    rt.page, rt.cfg, target_list, message)
            LOGS.add("[OK] send xong: " + str(len(res.get("ok") or []))
                     + " OK / " + str(len(res.get("fail") or [])) + " FAIL")
        finally:
            if delay > 0:
                rt.cfg["send_delay_seconds"] = old_delay

    rt.spawn(_run())
    n = len(target_list) if isinstance(target_list, list) \
        else len(bot.parse_users(target_list))
    return 200, {
        "queued": n,
        "message": "đã xếp hàng " + str(n) + " target — theo dõi Nhật ký",
    }


def api_auth_import(rt, body):
    raw = (body or {}).get("raw", "")
    try:
        cookies = bot.parse_token_input(raw)
    except ValueError as e:
        return 400, {"error": str(e)}
    try:
        bot.save_cookies(cookies)
    except Exception as e:
        return 500, {"error": "lưu cookie (mã hóa): " + str(e)[:120]}
    LOGS.add("[OK] nạp " + str(len(cookies))
             + " cookie đã mã hóa AES — làm lại session")
    rt.spawn(rt.restart_session())

    async def _wait_boot():
        await asyncio.sleep(8)
        LOGS.add("[INFO] session state: "
                 + str(rt.boot.get("state", "?")))

    rt.spawn(_wait_boot())
    code, st = api_status(rt)
    st["message"] = ("đã nạp " + str(len(cookies))
                     + " cookie — đang làm lại session, chờ ~15s rồi reload")
    return code, st


def api_auth_test(rt):
    page = rt.page
    if page is None or not bot.page_alive(page):
        return 503, {"error": "session chưa sẵn sàng", "live": False}
    try:
        rt.submit(bot.refresh_self_status(page), timeout=60)
    except Exception as e:
        return 500, {"error": str(e)[:160], "live": False}
    code, st = api_status(rt)
    return code, st


def api_lookup(rt, body):
    """Auto get userid = link: dán link/username → uid + nickname + avatar."""
    raw = str((body or {}).get("input", "") or "").strip()
    if not raw:
        return 400, {"error": "dán link hoặc username trước"}
    u = bot.parse_user(raw)
    if not u:
        return 400, {"error": "không nhận diện được user từ input này"}
    if rt.page is None or not bot.page_alive(rt.page):
        return 503, {"error": "session chưa sẵn sàng", "username": u}
    try:
        info = rt.submit(bot.get_user_info(rt.page, u), timeout=60)
    except Exception as e:
        return 500, {"error": str(e)[:160], "username": u}
    return 200, {
        "username": u,
        "uid": str(info.get("uid", "") or ""),
        "nickname": info.get("nickname", "") or "",
        "avatar": info.get("avatar", "") or "",
        "in_watchlist": u in rt.wl,
    }


def api_detect(rt, body):
    if rt.detect_state.get("running"):
        return 200, {"started": False, "busy": True,
                     "message": "đang quét — chờ vòng hiện tại"}
    rt.spawn(rt.run_detect())
    return 200, {"started": True,
                 "message": "bắt đầu quét hội thoại ẩn — xem Nhật ký"}


def route(method, path, query, body, rt):
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts or parts[0] != "api":
        return 404, {"error": "not found"}
    seg = parts[1:]
    if not seg:
        return 404, {"error": "not found"}
    head = seg[0]

    if head == "health":
        return 200, {"ok": True, "worker": VERSION,
                     "key": bool(API_KEY)}

    if head == "status" and method == "GET":
        return api_status(rt)

    if head == "config":
        if method == "GET":
            return 200, {"config": rt.cfg}
        if method == "PUT":
            return api_config_put(rt, body)
        return 405, {"error": "method"}

    if head == "watchlist":
        if len(seg) >= 2 and seg[1] == "lookup" and method == "POST":
            return api_watchlist_lookup(rt)
        if len(seg) >= 2:
            user = unquote(seg[1]).lower().lstrip("@")
            if method == "DELETE":
                if user in rt.wl:
                    rt.wl.remove(user)
                    bot.save_watchlist(rt.wl)
                    return 200, {"removed": user}
                return 404, {"error": "không có @" + user}
            return 404, {"error": "not found"}
        if method == "GET":
            return api_watchlist_users(rt)
        if method == "POST":
            return api_watchlist(rt, body)
        if method == "DELETE":
            rt.wl.clear()
            bot.save_watchlist(rt.wl)
            return 200, {"cleared": True}
        return 405, {"error": "method"}

    if head == "users":
        if len(seg) >= 2:
            user = unquote(seg[1]).lower().lstrip("@")
            if method == "DELETE":
                if bot.remove_cached(user):
                    return 200, {"removed": user}
                return 404, {"error": "không có @" + user}
            return 404, {"error": "not found"}
        if method == "GET":
            return api_users(rt)
        if method == "DELETE":
            bot.save_cache({})
            return 200, {"cleared": True}
        return 405, {"error": "method"}

    if head == "logs":
        if len(seg) >= 2 and seg[1] == "clear" and method == "POST":
            LOGS.clear()
            return 200, {"cleared": True}
        if method == "GET":
            try:
                n = int((query.get("limit") or ["500"])[0])
            except Exception:
                n = 500
            return 200, {"lines": LOGS.tail(n)}
        return 405, {"error": "method"}

    if head == "send" and method == "POST":
        return api_send(rt, body)

    if head == "auth":
        if len(seg) >= 2 and seg[1] == "import" and method == "POST":
            return api_auth_import(rt, body)
        if len(seg) >= 2 and seg[1] == "test" and method == "POST":
            return api_auth_test(rt)
        return 404, {"error": "not found"}

    if head == "lookup" and method == "POST":
        return api_lookup(rt, body)

    if head == "detect" and method == "POST":
        return api_detect(rt, body)

    return 404, {"error": "not found"}


# ============ http ============
class Handler(BaseHTTPRequestHandler):
    rt = None
    server_version = "tt-worker"

    def log_message(self, *a):
        pass

    def _key_ok(self):
        if not API_KEY:
            return True
        # healthcheck Docker/uptime gọi không mang key — chỉ trả ok/version
        if urlparse(self.path).path == "/api/health":
            return True
        return self.headers.get("x-api-key", "") == API_KEY

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers",
                         "content-type, x-api-key")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(min(n, 2_000_000))
        try:
            d = json.loads(raw.decode("utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _dispatch(self, method):
        if method == "OPTIONS":
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods",
                             "GET,POST,PUT,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers",
                             "content-type, x-api-key")
            self.end_headers()
            return
        if not self._key_ok():
            self._send(401, {"error": "sai WORKER_API_KEY"})
            return
        try:
            u = urlparse(self.path)
            q = parse_qs(u.query)
            body = self._body() if method in ("POST", "PUT") else {}
            code, obj = route(method, u.path, q, body, self.rt)
            self._send(code, obj)
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": str(e)[:300]})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")


def main():
    sys.stdout = Tee(sys.stdout, LOGS)
    sys.stderr = Tee(sys.stderr, LOGS)

    rt = BotRuntime()
    Handler.rt = rt
    rt.start()

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    LOGS.add("[OK] worker " + VERSION + " → http://" + HOST + ":"
             + str(PORT) + " (key: " + ("bật" if API_KEY else "tắt") + ")")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        rt.stop.set()
        srv.server_close()


if __name__ == "__main__":
    main()
