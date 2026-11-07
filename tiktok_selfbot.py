#!/usr/bin/env python3
"""
NguyenHuuMinhTien Auto tiktok reply ver 3.2.7

- Send DM
- Auto-reply (watchlist + inbox) tuần tự, delay tải đầy đủ
- Tự chấp nhận message request
- Gửi reply đa phương thức, có xác nhận đã gửi
- Bỏ qua tin nhắn cũ quá N phút (mặc định 10)
- Auto-send định kỳ (GMT+7)
- Daemon mode
- Cache watchlist
"""

import os
import sys
import re
import json
import time
import asyncio
import random
import argparse
import threading
from datetime import datetime, timedelta, timezone

import requests
from playwright.async_api import async_playwright

VERSION = "3.3.0"
TOOL_NAME = "NguyenHuuMinhTien Auto tiktok reply ver " + VERSION

if os.name == "nt":
    os.system("chcp 65001 > nul 2>&1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.system("")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("BOT_DATA_DIR", SCRIPT_DIR)
if not os.path.isdir(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        DATA_DIR = SCRIPT_DIR
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
COOKIES_FILE = os.path.join(DATA_DIR, "cookies.json")   # legacy plaintext — chỉ để migrate
COOKIES_ENC = os.path.join(DATA_DIR, "cookies.enc")     # cookie mã hóa AES (Fernet)
SECRET_FILE = os.path.join(DATA_DIR, "secret.key")      # khóa mã hóa — tự sinh, không up repo
UID_CACHE_FILE = os.path.join(DATA_DIR, "uids.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")
LANG = "vi-VN"

SELF_STATUS = {
    "username": "",
    "nickname": "",
    "avatar": "",
    "live": False,
    "checked_at": 0,
}


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"


def col(t, clr):
    return clr + str(t) + C.RESET


def ok(m):
    print("  " + col("[OK]", C.GREEN) + " " + str(m))


def er(m):
    print("  " + col("[FAIL]", C.RED) + " " + str(m))


def in4(m):
    print("  " + col("[INFO]", C.CYAN) + " " + str(m))


def wn(m):
    print("  " + col("[WARN]", C.YELLOW) + " " + str(m))


def step(m):
    print("     " + col("->", C.GRAY) + " " + str(m))


def log_once(fail_logged, key, msg, clr=C.RED):
    if key in fail_logged:
        return
    fail_logged.add(key)
    print("     " + col("[FAIL]", clr) + " " + msg)


def msg_age_minutes(time_hint):
    if not time_hint:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", str(time_hint))
    if not m:
        return None
    try:
        hh = int(m.group(1)) % 24
        mm = int(m.group(2))
    except Exception:
        return None
    now = time.localtime()
    cur = now.tm_hour * 60 + now.tm_min
    val = hh * 60 + mm
    diff = cur - val
    if diff < 0:
        diff += 24 * 60
    return diff


# ============ uid cache ============
def load_cache():
    if not os.path.isfile(UID_CACHE_FILE):
        return {}
    try:
        with open(UID_CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        out = {}
        for k, v in d.items():
            if isinstance(v, str):
                out[k] = {"uid": v, "nickname": "", "avatar": ""}
            elif isinstance(v, dict):
                out[k] = {
                    "uid": v.get("uid", ""),
                    "nickname": v.get("nickname", ""),
                    "avatar": v.get("avatar", ""),
                }
        return out
    except Exception:
        return {}


def save_cache(c):
    try:
        with open(UID_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def cache_uid(u, uid, nn="", avatar=""):
    c = load_cache()
    old = c.get(u.lower()) or {}
    c[u.lower()] = {
        "uid": str(uid),
        "nickname": nn if nn else old.get("nickname", ""),
        "avatar": avatar if avatar else old.get("avatar", ""),
    }
    save_cache(c)


def get_cached(u):
    return load_cache().get(u.lower())


def remove_cached(u):
    c = load_cache()
    k = u.lower()
    if k in c:
        del c[k]
        save_cache(c)
        return True
    return False


# ============ watchlist cache ============
def load_watchlist():
    if not os.path.isfile(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                out = []
                seen = set()
                for x in data:
                    u = parse_user(str(x))
                    if u and u not in seen:
                        seen.add(u)
                        out.append(u)
                return out
    except Exception:
        pass
    return []


def save_watchlist(wl):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(list(wl), f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ============ config ============
DEFAULT_CFG = {
    "webhook_url": "",
    "auto_reply_enabled": True,
    "auto_reply_messages": [
        "Từ từ, Tiến bận rồi nó về nhắn nha 💖",
        "Tiến đang bận xíu, tí nữa nhắn lại nha 💌",
        "Đợi Tiến xíu nhé, đang bận chút việc 💖",
    ],
    "auto_reply_cooldown_minutes": 20,
    "auto_reply_max_message_age_minutes": 10,
    "auto_reply_verbose": False,
    "auto_reply_typing_delay_seconds": 2.5,
    "auto_reply_rules": [],
    "active_hours_enabled": False,
    "active_hours_start": "07:00",
    "active_hours_end": "23:00",
    "hidden_detect_enabled": True,
    "hidden_detect_interval_minutes": 10,
    "hidden_detect_auto_add": True,
    "check_method": "inbox",
    "poll_interval_seconds": 15,
    "send_message_content": (
        "🌸 REP CHUỖI TỰ ĐỘNG 🌸\n"
        "───────────\n"
        "\n"
        "Chào {nickname} 👋\n"
        "Chúc bạn một ngày tốt lành 💖\n"
        "\n"
        "📌 Made by: Nguyễn Hữu Minh Tiến"
    ),
    "send_delay_seconds": 8,
    "headless": False,
    "browser_channel": "chrome",
    "auto_send_enabled": False,
    "auto_send_targets": "cache",
    "auto_send_time": "00:00",
    "auto_send_timezone_offset": 7,
    "auto_send_message": "",
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def load_cfg():
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        for k, v in DEFAULT_CFG.items():
            cfg.setdefault(k, v)
        return cfg
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CFG, f, indent=2, ensure_ascii=False)
    in4("tạo config: " + CONFIG_FILE)
    return dict(DEFAULT_CFG)


def save_cfg(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ============ parse ============
USERNAME_RE = re.compile(r"tiktok\.com/@([A-Za-z0-9._]+)", re.I)
SHORT_LINK_RE = re.compile(
    r"https?://(?:www\.)?(?:vm|vt)\.tiktok\.com/[A-Za-z0-9]+", re.I)


def resolve_short_link(url, timeout=8):
    """Link ngắn vm/vt.tiktok.com → URL đầy đủ sau redirect."""
    try:
        r = requests.get(str(url).strip(), allow_redirects=True,
                         timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0"})
        return r.url or ""
    except Exception:
        return ""


def parse_user(raw):
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    # link ngắn / link dạng /t/ /z/ → bắn redirect lấy /@user
    if re.search(r"tiktok\.com/(?:t|z)/", s, re.I) or SHORT_LINK_RE.search(s):
        full = resolve_short_link(s)
        m = USERNAME_RE.search(full) if full else None
        if m:
            return m.group(1)
        if re.match(r"https?://", s, re.I):
            return ""  # không resolve được → bỏ, không bịa username
    m = USERNAME_RE.search(s)
    if m:
        return m.group(1)
    m = re.search(r"@([A-Za-z0-9._]+)", s)
    if m:
        return m.group(1)
    s = s.lstrip("@").strip()
    if re.fullmatch(r"\d{10,}", s):
        return ""
    if re.match(r"https?://", s, re.I):
        return ""  # URL lạ không chứa /@user → bỏ
    s = re.split(r"[/?#\s]", s, maxsplit=1)[0]
    return re.sub(r"[^A-Za-z0-9._]", "", s)


def parse_users(raw):
    if not raw:
        return []
    out = []
    seen = set()
    for t in re.split(r"[\s,;]+", str(raw).strip()):
        u = parse_user(t)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def render_msg(tpl, user="", nick=""):
    un = (user or "").strip()
    nn = (nick or "").strip() or ("@" + un if un else "bạn")
    o = tpl
    o = o.replace("{nickname}", nn)
    o = o.replace("{@username}", "@" + un if un else "")
    o = o.replace("{username}", un)
    o = re.sub(r"\s*\(\s*@?\s*\)\s*", " ", o)
    return o


def choose_reply(cfg, text, user="", nick=""):
    """Rule từ khóa trước, sau đó random mẫu thường."""
    t = (text or "").strip().lower()
    for r in cfg.get("auto_reply_rules") or []:
        if not isinstance(r, dict):
            continue
        c = str(r.get("contains", "")).strip().lower()
        if c and c in t:
            return render_msg(str(r.get("reply", "")), user, nick), "rule:" + c
    msgs = [str(m) for m in (cfg.get("auto_reply_messages") or [])
            if str(m).strip()]
    if not msgs:
        return "Từ từ, Tiến bận rồi 💖", "default"
    return render_msg(random.choice(msgs), user, nick), "random"


def in_active_hours(cfg):
    if not cfg.get("active_hours_enabled"):
        return True
    try:
        sh, sm = [int(x) for x in
                  str(cfg.get("active_hours_start", "07:00")).split(":")]
        eh, em = [int(x) for x in
                  str(cfg.get("active_hours_end", "23:00")).split(":")]
    except Exception:
        return True
    cur = datetime.now().hour * 60 + datetime.now().minute
    start = (sh % 24) * 60 + (sm % 60)
    end = (eh % 24) * 60 + (em % 60)
    if start <= end:
        return start <= cur <= end
    return cur >= start or cur <= end


IMPORTANT_COOKIES = ["sessionid", "sessionid_ss", "sid_tt", "uid_tt",
                     "uid_tt_ss", "tt_csrf_token", "msToken"]


def parse_token_input(raw):
    """JSON cookie / document.cookie / token trần -> list cookie chuẩn."""
    s = str(raw or "").strip()
    if not s:
        raise ValueError("không có dữ liệu")

    def finish(items):
        out = parse_cookies_data(items)
        if not out:
            raise ValueError("không có cookie name/value")
        return out

    if s[0] in "[{":
        try:
            d = json.loads(s)
        except Exception as e:
            raise ValueError("JSON lỗi cú pháp: " + str(e)[:60])
        if isinstance(d, list):
            return finish(d)
        if isinstance(d, dict) and isinstance(d.get("cookies"), list):
            return finish(d["cookies"])
        if isinstance(d, dict) and "name" in d and "value" in d:
            return finish([d])
        if isinstance(d, dict):
            items = [{"name": k, "value": str(v)}
                     for k, v in d.items()
                     if not str(k).startswith("_")
                     and isinstance(v, (str, int, float))]
            if items:
                return finish(items)
        raise ValueError("không nhận diện được JSON")

    if "=" in s and re.search(r"[;\s]", s):
        items = []
        for part in re.split(r";\s*", s):
            part = part.strip()
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k.strip() and v.strip():
                items.append({"name": k.strip(), "value": v.strip()})
        if items:
            return finish(items)

    if re.fullmatch(r"[A-Za-z0-9._%+-]{16,}", s):
        return finish([{"name": "sessionid", "value": s}])

    raise ValueError("không nhận diện được định dạng cookie/token")


# ============ cookies ============
SAMEMAP = {
    "no_restriction": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
    "": "Lax",
}


def norm_ck(name, value, domain=".tiktok.com", path="/",
            secure=None, http_only=None,
            same_site=None, expires=None):
    ck = {
        "name": str(name),
        "value": str(value),
        "domain": domain or ".tiktok.com",
        "path": path or "/",
    }
    if secure is not None:
        ck["secure"] = bool(secure)
    if http_only is not None:
        ck["httpOnly"] = bool(http_only)
    if same_site is not None:
        ck["sameSite"] = SAMEMAP.get(str(same_site).lower(), "Lax")
    if expires is not None:
        try:
            e = float(expires)
            if e > 0:
                ck["expires"] = e
        except Exception:
            pass
    return ck


def parse_cookies_data(data):
    flat = []

    def push(e):
        if not isinstance(e, dict):
            return
        if "name" not in e or "value" not in e:
            return
        flat.append(norm_ck(
            e["name"], e["value"],
            e.get("domain", ".tiktok.com"),
            e.get("path", "/"),
            e.get("secure"),
            e.get("httpOnly", e.get("http_only")),
            e.get("sameSite", e.get("same_site")),
            e.get("expires", e.get("expirationDate")),
        ))

    if isinstance(data, dict) and "name" in data:
        push(data)
    elif isinstance(data, list):
        for x in data:
            push(x)
    elif isinstance(data, dict) and isinstance(data.get("cookies"), dict):
        for n, v in data["cookies"].items():
            if isinstance(v, dict) and "value" in v:
                flat.append(norm_ck(
                    n, v["value"],
                    v.get("domain", ".tiktok.com"),
                    v.get("path", "/"),
                    v.get("secure"),
                    v.get("httpOnly"),
                    v.get("sameSite"),
                    v.get("expires"),
                ))
            elif isinstance(v, (str, int, float)):
                flat.append(norm_ck(n, v))
    elif isinstance(data, dict):
        items = []
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if isinstance(v, (str, int, float)):
                items.append({"name": k, "value": str(v)})
        if items:
            return parse_cookies_data(items)
    return flat


def _fernet():
    """Khóa mã hóa cookie — secret.key tự sinh 32 bytes lần đầu, lưu local."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError(
            "thiếu cryptography — chạy: pip install -r requirements.txt")
    key = None
    try:
        with open(SECRET_FILE, "rb") as f:
            key = f.read().strip()
    except OSError:
        pass
    if not key or len(key) != 44:  # Fernet key = 44 ký tự urlsafe-base64
        key = Fernet.generate_key()
        with open(SECRET_FILE, "wb") as f:
            f.write(key)
        try:
            if os.name != "nt":
                os.chmod(SECRET_FILE, 0o600)
        except OSError:
            pass
    return Fernet(key)


def save_cookies(cookies):
    """Lưu cookie đã mã hóa AES (Fernet) — plaintext không bao giờ đụng đĩa."""
    blob = _fernet().encrypt(
        json.dumps(cookies, ensure_ascii=False).encode("utf-8"))
    tmp = COOKIES_ENC + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, COOKIES_ENC)
    try:
        if os.path.isfile(COOKIES_FILE):
            os.remove(COOKIES_FILE)
    except OSError:
        pass
    return COOKIES_ENC


def load_cookies():
    if os.path.isfile(COOKIES_ENC):
        with open(COOKIES_ENC, "rb") as f:
            raw = f.read()
        try:
            data = json.loads(_fernet().decrypt(raw).decode("utf-8"))
        except Exception as e:
            raise ValueError("cookies.enc hỏng hoặc sai khóa: "
                             + str(e)[:80])
        return parse_cookies_data(data)
    if os.path.isfile(COOKIES_FILE):
        # migrate: bản plaintext cũ → mã hóa rồi xóa bản gốc
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        save_cookies(data)
        return parse_cookies_data(data)
    raise FileNotFoundError("chưa có token — dán cookie ở trang Cài đặt")


def cookies_to_playwright(cookie_data):
    out = []
    for ck in cookie_data:
        pc = {
            "name": ck["name"],
            "value": ck["value"],
            "domain": ck.get("domain", ".tiktok.com"),
            "path": ck.get("path", "/"),
        }
        for k in ("secure", "httpOnly", "sameSite", "expires"):
            if k in ck:
                pc[k] = ck[k]
        out.append(pc)
    return out


async def add_cookies_to_ctx(ctx, cookie_data):
    ok_n = 0
    for pc in cookies_to_playwright(cookie_data):
        try:
            await ctx.add_cookies([pc])
            ok_n += 1
        except Exception:
            pass
    return ok_n


def send_webhook(cfg, content):
    url = (cfg.get("webhook_url") or "").strip()
    if not url:
        return
    try:
        requests.post(
            url,
            json={"content": content, "username": TOOL_NAME},
            timeout=10,
        )
    except Exception:
        pass


def page_alive(page):
    try:
        return not page.is_closed()
    except Exception:
        return False


# ============ self account ============
async def get_self(page):
    if not page_alive(page):
        return None

    # hydration: chờ link Hồ sơ hoặc nút đăng nhập xuất hiện (tối đa 8s)
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            if await page.query_selector(
                    "a[data-e2e='nav-profile'], "
                    "button[data-e2e='top-login-button']"):
                break
        except Exception:
            break
        await asyncio.sleep(0.5)

    try:
        login_btn = await page.query_selector(
            "button[data-e2e='top-login-button'], "
            "button:has-text('Log in'), "
            "button:has-text('Đăng nhập')"
        )
        if login_btn and await login_btn.is_visible():
            return None
    except Exception:
        pass

    # Link "Hồ sơ" trong side-nav chỉ mình mình trỏ tới — đây là nguồn self
    # đáng tin duy nhất trong DOM. Không dùng a[href*='/@'] chung chung:
    # nó bắt nhầm video/suggested account.
    for sel in ("a[data-e2e='nav-profile']",
                "a[data-e2e='profile-icon']",
                "nav a[data-e2e='profile-icon']"):
        try:
            el = await page.query_selector(sel)
        except Exception:
            continue
        if not el:
            continue
        try:
            href = await el.get_attribute("href") or ""
        except Exception:
            continue
        if "/video/" in href or "/photo/" in href:
            continue
        m = re.search(r"/@([A-Za-z0-9._]+)", href)
        if not m:
            continue
        avatar = ""
        try:
            img = await el.query_selector("img")
            if img:
                avatar = await img.get_attribute("src") or ""
        except Exception:
            pass
        return {"uniqueId": m.group(1), "nickname": "", "id": "",
                "avatar": avatar}

    for key in ("webapp.user-detail", "webapp.user-detail-foryou"):
        try:
            r = await page.evaluate("""
                (k) => {
                    const s = window.__UNIVERSAL_DATA_FOR_REHYDRATION__;
                    const ud = s && s.__DEFAULT_SCOPE__
                        ? s.__DEFAULT_SCOPE__[k]
                        : null;
                    if (ud && ud.userInfo && ud.userInfo.user) {
                        return {
                            uniqueId: ud.userInfo.user.uniqueId,
                            nickname: ud.userInfo.user.nickname,
                            id: ud.userInfo.user.id,
                            avatar: ud.userInfo.user.avatarThumb
                                || ud.userInfo.user.avatarUrl || '',
                        };
                    }
                    return null;
                }
            """, key)
            if r:
                return r
        except Exception:
            pass

    try:
        r = await page.evaluate(r"""
            () => {
                const el = document.getElementById(
                    '__UNIVERSAL_DATA_FOR_REHYDRATION__'
                );
                if (!el) return null;
                try {
                    const data = JSON.parse(el.textContent);
                    const sc = data.__DEFAULT_SCOPE__;
                    if (!sc) return null;
                    const keys = ['webapp.user-detail',
                                  'webapp.user-detail-foryou'];
                    for (const k of keys) {
                        const ud = sc[k];
                        if (ud && ud.userInfo && ud.userInfo.user) {
                            return {
                                uniqueId: ud.userInfo.user.uniqueId,
                                nickname: ud.userInfo.user.nickname,
                                id: ud.userInfo.user.id,
                                avatar: ud.userInfo.user.avatarThumb
                                    || ud.userInfo.user.avatarUrl || '',
                            };
                        }
                    }
                } catch (e) {}
                return null;
            }
        """)
        if r:
            return r
    except Exception:
        pass

    return None


async def refresh_self_status(page):
    def _blank():
        SELF_STATUS["username"] = ""
        SELF_STATUS["nickname"] = ""
        SELF_STATUS["avatar"] = ""
        SELF_STATUS["live"] = False

    try:
        me = await get_self(page)
        if me and me.get("uniqueId"):
            SELF_STATUS["username"] = me.get("uniqueId", "")
            SELF_STATUS["nickname"] = me.get("nickname", "") or ""
            SELF_STATUS["avatar"] = me.get("avatar", "") or ""
            SELF_STATUS["live"] = True
        else:
            _blank()
    except Exception:
        _blank()
    SELF_STATUS["checked_at"] = time.time()


# ============ get_user_info ============
async def _api_user_info(page, username):
    try:
        return await page.evaluate("""async (username) => {
            try {
                const res = await fetch(`/api/user/detail/?uniqueId=${username}`);
                if (!res.ok) return null;
                const data = await res.json();
                if (data && data.userInfo && data.userInfo.user) {
                    const u = data.userInfo.user;
                    return {
                        uid: u.id,
                        nickname: u.nickname || '',
                        avatar: u.avatarThumb || u.avatarUrl || u.avatarLarger || ''
                    };
                }
            } catch(e) {}
            return null;
        }""", username)
    except Exception:
        return None


async def get_user_info(page, username):
    cached = get_cached(username)
    if cached and cached.get("uid"):
        return cached

    if not page_alive(page):
        return {"uid": "", "nickname": ""}

    on_tt = False
    try:
        on_tt = "tiktok.com" in (page.url or "")
    except Exception:
        pass

    if on_tt:
        info = await _api_user_info(page, username)
        if info and info.get("uid"):
            cache_uid(username, info["uid"], info.get("nickname", ""), info.get("avatar", ""))
            return info

    url = "https://www.tiktok.com/@" + username + "?lang=" + LANG
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return {"uid": "", "nickname": ""}

    await asyncio.sleep(3)

    info = await _api_user_info(page, username)
    if info and info.get("uid"):
        cache_uid(username, info["uid"], info.get("nickname", ""), info.get("avatar", ""))
        return info

    info = None
    try:
        info = await page.evaluate(r"""
            () => {
                const el = document.getElementById(
                    '__UNIVERSAL_DATA_FOR_REHYDRATION__'
                );
                let sc = null;
                if (el) {
                    try {
                        sc = JSON.parse(el.textContent).__DEFAULT_SCOPE__;
                    } catch (e) {}
                }
                if (!sc) {
                    const s = window.__UNIVERSAL_DATA_FOR_REHYDRATION__;
                    sc = s && s.__DEFAULT_SCOPE__;
                }
                const ud = sc && sc['webapp.user-detail'];
                if (ud && ud.userInfo && ud.userInfo.user) {
                    return {
                        uid: ud.userInfo.user.id,
                        nickname: ud.userInfo.user.nickname || '',
                        avatar: ud.userInfo.user.avatarThumb
                            || ud.userInfo.user.avatarUrl || '',
                    };
                }
                return null;
            }
        """)
    except Exception:
        info = None

    if not info or not info.get("uid"):
        try:
            html = await page.content()
            m = re.search(r'"user":\s*\{\s*"id":\s*"(\d+)"', html)
            if not m:
                m = re.search(r'"id":\s*"(\d+)"', html)
            if m:
                info = {"uid": m.group(1), "nickname": ""}
        except Exception:
            pass

    if info and info.get("uid"):
        cache_uid(username, info["uid"], info.get("nickname", ""), info.get("avatar", ""))
        return info

    return {"uid": "", "nickname": ""}


# ============ box helpers ============
BOX_SEL = [
    "div[contenteditable='true'][data-e2e='message-input']",
    "div[contenteditable='true'][role='textbox']",
    "div[contenteditable='true'][data-e2e*='message']",
    "textarea[data-e2e*='message']",
    "textarea[placeholder*='Nhập' i]",
    "textarea[placeholder*='tin nhắn' i]",
    "div[contenteditable='true']",
]


async def find_box(page, to=8000):
    if not page_alive(page):
        return None
    per = max(500, to // len(BOX_SEL))
    for s in BOX_SEL:
        try:
            loc = page.locator(s).first
            await loc.wait_for(state="visible", timeout=per)
            de = await loc.get_attribute("data-e2e") or ""
            if "search" in de.lower():
                continue
            return loc
        except Exception:
            continue
    return None


async def type_box(page, box, msg):
    if not page_alive(page):
        return False
    try:
        await box.click(timeout=3000)
        await asyncio.sleep(0.15)
        await box.fill("")
        await box.fill(msg)
        return True
    except Exception:
        pass
    try:
        await box.click(timeout=3000)
        await asyncio.sleep(0.2)
        try:
            await box.press("Control+A")
            await box.press("Delete")
        except Exception:
            pass
        await box.press_sequentially(msg, delay=15)
        return True
    except Exception:
        pass
    try:
        await box.evaluate("""(el, t) => {
            el.focus();
            el.innerHTML = '';
            el.appendChild(document.createTextNode(t));
            el.dispatchEvent(new InputEvent('input', {
                bubbles: true, cancelable: true,
                inputType: 'insertText', data: t
            }));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""", msg)
        return True
    except Exception:
        return False


async def press_enter(page, box):
    if not page_alive(page):
        return False
    try:
        await box.press("Enter")
        return True
    except Exception:
        pass
    try:
        await page.keyboard.press("Enter")
        return True
    except Exception:
        pass
    try:
        btn = page.locator(
            "[data-e2e='message-send-button'], "
            "button[aria-label*='Send' i], "
            "button[aria-label*='Gửi' i]"
        ).first
        if await btn.count() > 0:
            await btn.click(timeout=2000)
            return True
    except Exception:
        pass
    return False


SEND_BTN_SEL = (
    "[data-e2e='message-send-button'], "
    "button[aria-label*='Send' i], "
    "button[aria-label*='Gửi' i]"
)


async def accept_message_request(page):
    if not page_alive(page):
        return False
    sels = [
        "button:has-text('Chấp nhận')",
        "button:has-text('Accept')",
        "button:has-text('Cho phép')",
        "button:has-text('Allow')",
        "[data-e2e='accept-request-button']",
        "div[role='button']:has-text('Chấp nhận')",
        "div[role='button']:has-text('Accept')",
    ]
    for s in sels:
        try:
            loc = page.locator(s).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=3000)
                await asyncio.sleep(2)
                return True
        except Exception:
            continue
    return False


async def verify_sent(page, reply_text):
    await asyncio.sleep(1.5)
    msg = await read_last_chat_message(page)
    if not msg:
        return False
    if not msg.get("is_self"):
        return False
    want = (reply_text or "").strip()[:25]
    got = (msg.get("text") or "").strip()
    if not want:
        return False
    return got.startswith(want)


async def send_reply(page, box, reply_text):
    if not page_alive(page) or not box:
        return False, ""

    if await type_box(page, box, reply_text):
        if await press_enter(page, box):
            if await verify_sent(page, reply_text):
                return True, "fill+enter"

    try:
        await box.click(timeout=3000)
        await asyncio.sleep(0.2)
        try:
            await box.press("Control+A")
            await box.press("Delete")
        except Exception:
            pass
        await box.press_sequentially(reply_text, delay=20)
        if await press_enter(page, box):
            if await verify_sent(page, reply_text):
                return True, "typing+enter"
    except Exception:
        pass

    if await type_box(page, box, reply_text):
        try:
            btn = page.locator(SEND_BTN_SEL).first
            if await btn.count() > 0:
                await btn.click(timeout=3000)
                if await verify_sent(page, reply_text):
                    return True, "fill+button"
        except Exception:
            pass

    try:
        await box.evaluate("""(el, t) => {
            el.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, t);
            el.dispatchEvent(new InputEvent('input', {
                bubbles: true, cancelable: true,
                inputType: 'insertText', data: t
            }));
        }""", reply_text)
        if await press_enter(page, box):
            if await verify_sent(page, reply_text):
                return True, "exec+enter"
    except Exception:
        pass

    return False, ""


async def close_modals(page):
    if not page_alive(page):
        return
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.15)
    except Exception:
        pass
    try:
        await page.evaluate("""() => {
            const sel = '.TUXModal-overlay, '
                + '[class*="Modal-overlay"], '
                + '[class*="backdrop"]';
            document.querySelectorAll(sel).forEach(function (el) {
                el.remove();
            });
            document.body.style.overflow = '';
        }""")
    except Exception:
        pass


# ============ message readers ============
async def read_last_chat_message(page):
    if not page_alive(page):
        return None

    box = await find_box(page, 5000)
    if not box:
        return None

    try:
        bb = await box.bounding_box()
    except Exception:
        return None
    if not bb:
        return None

    try:
        data = await page.evaluate("""(rect) => {
            const inputTop = rect.y;
            const paneL = rect.x - 60;
            const paneR = rect.x + rect.width + 60;
            const paneRight = rect.x + rect.width;
            const leaves = [];
            const tArr = [];
            const els = document.querySelectorAll('div, span, p');

            for (const el of els) {
                if (el.childElementCount !== 0) continue;
                const t = (el.textContent || '').trim();
                if (!t || t.length > 600) continue;

                const r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                if (r.bottom > inputTop - 6) continue;
                if (r.left < paneL || r.right > paneR) continue;
                if (r.bottom < inputTop - 700) continue;

                if (/^\\d{1,2}:\\d{2}([AP]M)?$/i.test(t)) {
                    tArr.push({t: t, bottom: r.bottom});
                    continue;
                }
                if (/^(hôm nay|hom nay|hôm qua|hom qua|today|yesterday)$/i.test(t)) continue;
                if (/^\\d{1,2}[\\/-]\\d{1,2}([\\/-]\\d{2,4})?$/.test(t)) continue;
                if (/chưa có tin nhắn|select a conversation|start a conversation|bắt đầu trò chuyện|no messages/i.test(t)) continue;
                if (/^(đã xem|seen|đã gửi|delivered|sent)$/i.test(t)) continue;

                leaves.push({t: t, bottom: r.bottom, right: r.right});
            }

            let maxTextBottom = -1;
            for (const l of leaves) {
                if (l.bottom > maxTextBottom) maxTextBottom = l.bottom;
            }

            const imgs = document.querySelectorAll('img');
            for (const im of imgs) {
                const r = im.getBoundingClientRect();
                if (r.width < 40 || r.height < 40) continue;
                if (r.bottom > inputTop - 6) continue;
                if (r.left < paneL || r.right > paneR) continue;
                if (r.bottom < inputTop - 700) continue;
                if (r.bottom > maxTextBottom + 10) {
                    leaves.push({t: '[ảnh/video]', bottom: r.bottom, right: r.right});
                }
            }

            if (!leaves.length) return null;
            leaves.sort((a, b) => b.bottom - a.bottom);
            const last = leaves[0];
            const isSelf = (paneRight - last.right) < rect.width * 0.2;

            let timeHint = '';
            let best = -1;
            for (const x of tArr) {
                if (x.bottom >= last.bottom - 90 && x.bottom <= last.bottom + 70) {
                    if (x.bottom > best) {
                        best = x.bottom;
                        timeHint = x.t;
                    }
                }
            }

            return {text: last.t, is_self: isSelf, time_hint: timeHint};
        }""", bb)
    except Exception:
        return None

    if not data or not data.get("text"):
        return None

    return {
        "text": data["text"],
        "sig": "g:" + data["text"][:120] + "|" + str(data.get("time_hint", "")),
        "is_self": bool(data.get("is_self")),
        "time_hint": data.get("time_hint", ""),
    }


async def read_last_chat_message_retry(page, tries=3, gap=2.0):
    for _ in range(tries):
        msg = await read_last_chat_message(page)
        if msg:
            return msg
        await asyncio.sleep(gap)
    return None


async def get_chat_username(page):
    try:
        header = await page.query_selector(
            "[data-e2e='conversation-header'], "
            "[class*='ConversationHeader']"
        )
        if header:
            link = await header.query_selector("a[href*='/@']")
            if link:
                href = await link.get_attribute("href") or ""
                m = re.search(r"/@([A-Za-z0-9._]+)", href)
                if m:
                    return m.group(1)

            ht = (await header.inner_text() or "").strip()
            m = re.search(r"@([a-zA-Z0-9._]{3,})", ht)
            if m:
                return m.group(1)

            parts = [p.strip() for p in ht.split("\n") if p.strip()]
            if parts:
                cand = parts[0].strip().lstrip("@")
                cand = re.sub(r"[^\w._]+", "", cand, flags=re.UNICODE)
                if cand:
                    return cand
    except Exception:
        pass

    return ""


async def open_chat_via_profile(page, username):
    if not page_alive(page):
        return False

    url = "https://www.tiktok.com/@" + username + "?lang=" + LANG
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return False

    await asyncio.sleep(3)
    await close_modals(page)

    btn = None
    for s in (
        "[data-e2e='message-button']",
        "button[data-e2e='message-button']",
        "button[aria-label*='Nhắn' i]",
        "button[aria-label*='Tin nhắn' i]",
    ):
        try:
            loc = page.locator(s).first
            if await loc.count() > 0 and await loc.is_visible():
                btn = loc
                break
        except Exception:
            continue

    if not btn:
        try:
            pat = re.compile(r"^(Tin nhắn|Nhắn tin|Message)$", re.I)
            loc = page.get_by_role("button", name=pat).first
            if await loc.count() > 0:
                btn = loc
        except Exception:
            pass

    if not btn:
        return False

    clicked = False
    for attempt in ("normal", "force", "mouse"):
        try:
            if attempt == "normal":
                await btn.click(timeout=4000)
            elif attempt == "force":
                await btn.click(force=True, timeout=3000)
            else:
                bb = await btn.bounding_box()
                if bb:
                    cx = bb["x"] + bb["width"] / 2
                    cy = bb["y"] + bb["height"] / 2
                    await page.mouse.click(cx, cy)
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        return False

    await asyncio.sleep(3)
    await close_modals(page)
    await accept_message_request(page)

    if await find_box(page, 5000):
        await asyncio.sleep(2)
        return True
    return False


async def open_chat_for_user(page, username, uid, nickname=""):
    if not page_alive(page):
        return False

    if uid:
        for _ in range(2):
            try:
                url = ("https://www.tiktok.com/messages?lang="
                       + LANG + "&u=" + str(uid))
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=30000)
                await asyncio.sleep(3)
                await close_modals(page)
                await accept_message_request(page)
                if await find_box(page, 6000):
                    await asyncio.sleep(2)
                    return True
            except Exception:
                pass

    try:
        await page.goto("https://www.tiktok.com/messages?lang=" + LANG,
                        wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return False

    await asyncio.sleep(3)
    await close_modals(page)

    un = username.lower()
    nick = (nickname or "").strip().lower()

    items = []
    for sel in (
        "[data-e2e='conversation-item']",
        "[class*='ConversationListItem']",
        "[class*='ConversationItem']",
        "li[class*='conversation']",
        "div[class*='conversation']",
    ):
        try:
            items = await page.query_selector_all(sel)
        except Exception:
            items = []
        if items:
            break

    for it in items:
        try:
            t = (await it.inner_text() or "")
        except Exception:
            continue
        lines = [x.strip() for x in t.split("\n") if x.strip()]
        if not lines:
            continue
        head = lines[0].lower()

        hit = (head == nick) or (head == un)
        if not hit and nick and len(nick) >= 6:
            hit = nick in head
        if not hit:
            continue

        try:
            await it.click(timeout=3000)
        except Exception:
            try:
                await it.click(force=True, timeout=2000)
            except Exception:
                continue

        await asyncio.sleep(2.5)
        await close_modals(page)
        await accept_message_request(page)
        if await find_box(page, 5000):
            await asyncio.sleep(2)
            return True

    return await open_chat_via_profile(page, username)


# ============ send ============
async def send_via_url(page, uid, msg):
    if not page_alive(page):
        return False
    url = "https://www.tiktok.com/messages?lang=" + LANG + "&u=" + str(uid)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return False
    await asyncio.sleep(5)
    await close_modals(page)
    await accept_message_request(page)

    box = None
    for _ in range(10):
        if not page_alive(page):
            return False
        box = await find_box(page, 1500)
        if box:
            break
        await asyncio.sleep(0.6)
        await close_modals(page)

    if not box:
        return False
    if not await type_box(page, box, msg):
        return False
    await asyncio.sleep(0.4)
    if not await press_enter(page, box):
        return False
    await asyncio.sleep(1.5)
    return True


async def send_via_profile(page, username, msg):
    if not page_alive(page):
        return False
    url = "https://www.tiktok.com/@" + username + "?lang=" + LANG
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return False
    await asyncio.sleep(4)
    await close_modals(page)

    btn = None
    for s in (
        "[data-e2e='message-button']",
        "button[data-e2e='message-button']",
        "button[aria-label*='Nhắn' i]",
        "button[aria-label*='Tin nhắn' i]",
    ):
        try:
            loc = page.locator(s).first
            if await loc.count() > 0 and await loc.is_visible():
                btn = loc
                break
        except Exception:
            continue

    if not btn:
        try:
            pat = re.compile(r"^(Tin nhắn|Nhắn tin|Message)$", re.I)
            loc = page.get_by_role("button", name=pat).first
            if await loc.count() > 0:
                btn = loc
        except Exception:
            pass

    if not btn:
        return False

    clicked = False
    for attempt in ("normal", "force", "mouse"):
        try:
            if attempt == "normal":
                await btn.click(timeout=4000)
            elif attempt == "force":
                await btn.click(force=True, timeout=3000)
            else:
                bb = await btn.bounding_box()
                if bb:
                    cx = bb["x"] + bb["width"] / 2
                    cy = bb["y"] + bb["height"] / 2
                    await page.mouse.click(cx, cy)
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        return False

    await asyncio.sleep(2.5)
    await close_modals(page)
    await accept_message_request(page)

    box = None
    for _ in range(10):
        if not page_alive(page):
            return False
        box = await find_box(page, 1500)
        if box:
            break
        await asyncio.sleep(0.6)

    if not box:
        return False
    if not await type_box(page, box, msg):
        return False
    await asyncio.sleep(0.4)
    if not await press_enter(page, box):
        return False
    await asyncio.sleep(1.5)
    return True


async def send_dm(page, cfg, target, msg=None):
    u = parse_user(target)
    if not u:
        return False

    me = await get_self(page)
    if me and me.get("uniqueId", "").lower() == u.lower():
        return False

    info = await get_user_info(page, u)
    rendered = render_msg(
        msg or cfg["send_message_content"], u,
        info.get("nickname", ""),
    )

    if info.get("uid"):
        if await send_via_url(page, info["uid"], rendered):
            send_webhook(cfg, "DM tới **@" + u + "**")
            return True

    if await send_via_profile(page, u, rendered):
        send_webhook(cfg, "DM tới **@" + u + "**")
        return True
    return False


async def send_many(page, cfg, targets, msg=None):
    if isinstance(targets, str):
        targets = parse_users(targets)
    if not targets:
        wn("không có user")
        return

    print()
    print("  " + col("=== GỬI " + str(len(targets)) + " USER ===",
                     C.BOLD + C.MAGENTA))
    print()

    ok_l = []
    fail = []
    delay = int(cfg.get("send_delay_seconds", 8))

    for i, u in enumerate(targets, 1):
        print("  " + col("[" + str(i) + "/" + str(len(targets)) + "]",
                         C.CYAN) + " @" + u)
        try:
            s = await send_dm(page, cfg, u, msg)
            if s:
                ok_l.append(u)
            else:
                fail.append(u)
            tag = "[OK]" if s else "[FAIL]"
            clr = C.GREEN if s else C.RED
            print("     " + col(tag, clr))
        except Exception as e:
            print("     " + col("[ERR] " + str(e)[:60], C.RED))
            fail.append(u)
        if i < len(targets):
            await asyncio.sleep(delay)

    print()
    line = col("KẾT QUẢ:", C.BOLD) + " "
    line += col(str(len(ok_l)) + " OK", C.GREEN) + ", "
    line += col(str(len(fail)) + " FAIL", C.RED)
    print("  " + line)
    print()
    return {"ok": list(ok_l), "fail": list(fail)}


async def send_all_cache(page, cfg, msg=None):
    cache = load_cache()
    if not cache:
        wn("cache trống")
        return
    users = sorted(cache.keys())
    await send_many(page, cfg, users, msg)


# ============ group detect ============
async def is_group_chat(page):
    if not page_alive(page):
        return False
    try:
        return await page.evaluate("""
            () => {
                const sels = [
                    "[data-e2e='conversation-header']",
                    "[class*='ConversationHeader']",
                    "[data-e2e='chat-header']",
                ];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (!el) continue;
                    const t = (el.innerText || '').toLowerCase();
                    if (/nhóm|group/.test(t)) return true;
                    if (/\\band\\b.*\\bother/.test(t)) return true;
                    if ((t.match(/,/g) || []).length >= 1) return true;
                }
                const avatars = document.querySelectorAll(
                    "[class*='ConversationHeader'] [class*='Avatar'], "
                    + "[data-e2e='conversation-header'] [class*='Avatar']"
                );
                if (avatars.length >= 2) return true;
                return false;
            }
        """)
    except Exception:
        return False


async def is_group_sidebar_item(el):
    try:
        return await el.evaluate("""
            (el) => {
                const txt = (el.innerText || '').toLowerCase();
                if (/nhóm|group/.test(txt)) return true;
                if (/\\+\\d+/.test(txt)) return true;
                const avatars = el.querySelectorAll(
                    '[class*="Avatar"], img[class*="avatar"]'
                );
                if (avatars.length > 1) return true;
                return false;
            }
        """)
    except Exception:
        return False


# ============ hidden thread detect ============
def _walk_unique_ids(node, out, depth=0):
    if depth > 8 or len(out) > 200:
        return
    if isinstance(node, dict):
        uid = node.get("uniqueId") or node.get("unique_id")
        if isinstance(uid, str) and re.fullmatch(r"[A-Za-z0-9._]{2,}", uid):
            out.add(uid.lower())
        for v in node.values():
            _walk_unique_ids(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node[:200]:
            _walk_unique_ids(v, out, depth + 1)


HIDDEN_REQ_TAB_SEL = [
    "[data-e2e='message-request']",
    "[data-e2e='inbox-request-tab']",
    "div:has-text('Yêu cầu tin nhắn')",
    "div:has-text('Tin nhắn yêu cầu')",
    "div:has-text('Message requests')",
    "div:has-text('Requests')",
]


async def _scrape_conv_items(page):
    sels = [
        "[data-e2e='conversation-item']",
        "[class*='ConversationListItem']",
        "[class*='ConversationItem']",
        "li[class*='conversation']",
        "div[class*='conversation']",
    ]
    out = set()
    for sel in sels:
        try:
            items = await page.query_selector_all(sel)
        except Exception:
            items = []
        for it in items[:60]:
            hrefs = []
            try:
                hrefs = await it.eval_on_selector_all(
                    "a[href*='/@']",
                    "els => els.map(e => e.getAttribute('href'))")
            except Exception:
                pass
            got = False
            for h in hrefs or []:
                m = re.search(r"/@([A-Za-z0-9._]+)", str(h))
                if m:
                    out.add(m.group(1).lower())
                    got = True
            if not got:
                try:
                    t = (await it.inner_text() or "")
                except Exception:
                    t = ""
                m = re.search(r"@([A-Za-z0-9._]{2,})", t)
                if m:
                    out.add(m.group(1).lower())
        if out:
            break
    return out


async def detect_hidden_conversations(page):
    """Hội thoại không hiện trên UI PC (tab yêu cầu / API nội bộ / sidebar)
    nhưng vẫn có uid — trả về list username."""
    if not page_alive(page):
        return []
    found = set()

    # 1) API nội bộ — fail-soft, endpoint đổi thì bỏ qua
    try:
        data = await page.evaluate("""async () => {
            const paths = [
                '/api/inbox/v1/inbox/?count=50&language=vi-VN',
                '/api/message/inbox/?count=50&language=vi-VN',
                '/api/inbox/list/?count=50',
            ];
            for (const p of paths) {
                try {
                    const r = await fetch(p, {credentials: 'include'});
                    if (!r.ok) continue;
                    const j = await r.json();
                    if (j && (j.conversations || j.data || j.inbox)) return j;
                } catch (e) {}
            }
            return null;
        }""")
        if data:
            _walk_unique_ids(data, found)
    except Exception:
        pass

    # 2) tab "Yêu cầu tin nhắn" — nơi thread ẩn nằm lại
    try:
        await page.goto("https://www.tiktok.com/messages?lang=" + LANG,
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await close_modals(page)
        for s in HIDDEN_REQ_TAB_SEL:
            try:
                loc = page.locator(s).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=3000)
                    await asyncio.sleep(2.5)
                    break
            except Exception:
                continue
        found |= await _scrape_conv_items(page)
    except Exception:
        pass

    # 3) sidebar chính
    try:
        if "tiktok.com/messages" in (page.url or ""):
            found |= await _scrape_conv_items(page)
    except Exception:
        pass

    return sorted(x for x in found if x)


# ============ inbox reply ============
async def reply_inbox_method(page, cfg, tracker, last_msg_state, fail_logged):
    if not page_alive(page):
        return 0

    try:
        await page.goto(
            "https://www.tiktok.com/messages?lang=" + LANG,
            wait_until="domcontentloaded",
            timeout=30000,
        )
    except Exception:
        return 0

    await asyncio.sleep(3)
    await close_modals(page)

    sels = [
        "[data-e2e='conversation-item']",
        "[class*='ConversationListItem']",
        "[class*='ConversationItem']",
        "li[class*='conversation']",
        "div[class*='conversation']",
    ]
    items = []
    for sel in sels:
        items = await page.query_selector_all(sel)
        if items:
            break

    if not items:
        log_once(fail_logged, "inbox:noitems",
                 "không thấy conversation item", C.YELLOW)
        return 0

    replied = 0

    for it in items[:10]:
        if not page_alive(page):
            break

        try:
            if await is_group_sidebar_item(it):
                continue

            try:
                await it.click(timeout=3000)
            except Exception:
                try:
                    await it.click(force=True, timeout=2000)
                except Exception:
                    continue

            await asyncio.sleep(2.5)
            await close_modals(page)
            await accept_message_request(page)

            if await is_group_chat(page):
                continue

            username = await get_chat_username(page)
            if not username:
                continue

            key = username.lower()

            msg = await read_last_chat_message_retry(page, 2, 1.5)
            if not msg:
                if cfg.get("auto_reply_verbose"):
                    step("@" + username + " không đọc được message")
                continue

            if msg["is_self"]:
                last_msg_state[key] = msg["sig"]
                continue

            if key not in last_msg_state:
                last_msg_state[key] = msg["sig"]
                if cfg.get("auto_reply_verbose"):
                    step("@" + username + " ghi nhận tin cũ, bỏ qua")
                continue

            if msg["sig"] == last_msg_state.get(key):
                continue

            max_age = int(cfg.get("auto_reply_max_message_age_minutes", 10))
            age = msg_age_minutes(msg.get("time_hint", ""))
            if max_age > 0 and age is not None and age > max_age:
                print("     " + col("[SKIP]", C.YELLOW)
                      + " @" + username + " tin cũ " + str(age)
                      + "p > " + str(max_age) + "p")
                last_msg_state[key] = msg["sig"]
                continue

            print()
            print("  " + col("📩", C.YELLOW) + " @" + username + ": " + msg["text"][:60])
            send_webhook(cfg, "tin mới @" + username)

            rem = tracker.rem(key)
            if rem > 0:
                print("     " + col("[COOLDOWN]", C.YELLOW) + " còn " + str(rem) + "s")
                continue

            box = await find_box(page, 6000)
            if not box:
                log_once(fail_logged, "box:" + key,
                         "không thấy ô nhập @" + username)
                continue

            info = get_cached(username)
            nick = info.get("nickname", "") if info else ""
            reply, how = choose_reply(cfg, msg["text"], username, nick)
            tdel = float(cfg.get("auto_reply_typing_delay_seconds", 0) or 0)
            if tdel > 0:
                await asyncio.sleep(
                    random.uniform(max(0.5, tdel * 0.7), tdel * 1.4))

            sent, method = await send_reply(page, box, reply)

            if sent:
                replied += 1
                print("     " + col("[REPLY]", C.GREEN) + " " + reply[:50]
                      + " (" + method + "/" + how + ")")
                send_webhook(cfg, "đã rep @" + username)

                tracker.touch(key)

                last_msg_state[key] = msg["sig"]
            else:
                print("     " + col("[FAIL]", C.RED) + " gửi reply thất bại @" + username)

            await asyncio.sleep(2)

        except Exception as e:
            if "closed" in str(e).lower():
                break
            print("     " + col("[ERR]", C.RED) + " @" + username
                  if 'username' in dir() else "" + " " + str(e)[:60])

    return replied


# ============ watchlist reply (sequential) ============
async def auto_reply_watchlist(page, cfg, tracker, stop, watchlist,
                               last_msg_state, fail_logged):
    targets = list(watchlist)
    if not targets:
        return

    for u in targets:
        if stop.is_set() or not cfg.get("auto_reply_enabled"):
            break
        if not page_alive(page):
            break

        try:
            info = get_cached(u)
            if not info or not info.get("uid"):
                info = await get_user_info(page, u)

            uid = info.get("uid") if info else ""
            nick = info.get("nickname", "") if info else ""

            if not uid:
                log_once(fail_logged, "uid:" + u,
                         "không lấy được uid @" + u)
                continue

            opened = await open_chat_for_user(page, u, uid, nick)
            if not opened:
                log_once(fail_logged, "open:" + u,
                         "không mở được chat @" + u)
                continue

            msg = await read_last_chat_message_retry(page, 3, 2.0)
            if not msg:
                log_once(fail_logged, "read:" + u,
                         "không đọc được message @" + u, C.YELLOW)
                continue

            key = u.lower()

            if msg["is_self"]:
                last_msg_state[key] = msg["sig"]
                continue

            if key not in last_msg_state:
                last_msg_state[key] = msg["sig"]
                if cfg.get("auto_reply_verbose"):
                    step("@" + u + " ghi nhận tin cũ, bỏ qua")
                continue

            if msg["sig"] == last_msg_state.get(key):
                continue

            max_age = int(cfg.get("auto_reply_max_message_age_minutes", 10))
            age = msg_age_minutes(msg.get("time_hint", ""))
            if max_age > 0 and age is not None and age > max_age:
                print("     " + col("[SKIP]", C.YELLOW)
                      + " @" + u + " tin cũ " + str(age)
                      + "p > " + str(max_age) + "p")
                last_msg_state[key] = msg["sig"]
                continue

            print()
            print("  " + col("📩", C.YELLOW) + " @" + u + ": " + msg["text"][:60])
            send_webhook(cfg, "tin mới @" + u)

            rem = tracker.rem(key)
            if rem > 0:
                print("     " + col("[COOLDOWN]", C.YELLOW) + " còn " + str(rem) + "s")
                continue

            box = await find_box(page, 6000)
            if not box:
                await accept_message_request(page)
                box = await find_box(page, 4000)
            if not box:
                log_once(fail_logged, "box:" + key,
                         "không thấy ô nhập @" + u)
                continue

            reply, how = choose_reply(cfg, msg["text"], u, nick)
            tdel = float(cfg.get("auto_reply_typing_delay_seconds", 0) or 0)
            if tdel > 0:
                await asyncio.sleep(
                    random.uniform(max(0.5, tdel * 0.7), tdel * 1.4))

            sent, method = await send_reply(page, box, reply)

            if sent:
                print("     " + col("[REPLY]", C.GREEN) + " " + reply[:50]
                      + " (" + method + "/" + how + ")")
                send_webhook(cfg, "đã rep @" + u)

                tracker.touch(key)

                last_msg_state[key] = msg["sig"]
            else:
                print("     " + col("[FAIL]", C.RED) + " gửi reply thất bại @" + u)

            await asyncio.sleep(2)

        except Exception as e:
            if "closed" in str(e).lower():
                break
            print("     " + col("[ERR]", C.RED) + " @" + u + " " + str(e)[:60])

        await asyncio.sleep(1.5)


# ============ tracker ============
class Tracker:
    def __init__(self, mins):
        self.cd = mins * 60
        self.last = {}
        self.lk = threading.Lock()
        self.path = os.path.join(DATA_DIR, "cooldowns.json")
        try:
            if os.path.isfile(self.path):
                with open(self.path, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    self.last = {str(k): float(v) for k, v in d.items()}
        except Exception:
            pass

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.last, f)
        except Exception:
            pass

    def can(self, u):
        now = time.time()
        with self.lk:
            if now - self.last.get(u, 0) >= self.cd:
                self.last[u] = now
                self._save()
                return True
            return False

    def touch(self, u):
        with self.lk:
            self.last[u] = time.time()
            self._save()

    def rem(self, u):
        with self.lk:
            last = self.last.get(u, 0)
        return max(0, int(self.cd - (time.time() - last)))


async def auto_reply_loop(page, cfg, tracker, stop,
                          watchlist, wl_lock, p_lock, last_msg_state):
    method = cfg.get("check_method", "inbox")
    print()
    print("  " + col("=== AUTO-REPLY ĐANG CHẠY ===",
                     C.BOLD + C.BLUE))
    print("  method: " + col(method.upper(), C.YELLOW)
          + " | cooldown: " + str(cfg["auto_reply_cooldown_minutes"])
          + "p | max age: " + str(cfg.get("auto_reply_max_message_age_minutes", 10))
          + "p | poll: " + str(cfg["poll_interval_seconds"]) + "s")

    fail_logged = set()

    while not stop.is_set():
        if not page_alive(page):
            break
        if not cfg.get("auto_reply_enabled"):
            await asyncio.sleep(2)
            continue
        if not in_active_hours(cfg):
            await asyncio.sleep(30)
            continue

        try:
            async with p_lock:
                if method == "inbox":
                    await reply_inbox_method(page, cfg, tracker,
                                             last_msg_state, fail_logged)
                else:
                    async with wl_lock:
                        wl_copy = list(watchlist)
                    await auto_reply_watchlist(page, cfg, tracker, stop,
                                               wl_copy, last_msg_state,
                                               fail_logged)
        except Exception as e:
            if "closed" in str(e).lower():
                break

        try:
            await asyncio.sleep(int(cfg.get("poll_interval_seconds", 15)))
        except asyncio.CancelledError:
            break


# ============ auto send ============
def seconds_until_time(hh, mm, tz_offset):
    tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(tz)
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def do_auto_send(page, cfg, wl):
    mode = cfg.get("auto_send_targets", "cache")

    if mode == "cache":
        users = sorted(load_cache().keys())
    elif mode == "watchlist":
        users = list(wl)
    elif isinstance(mode, list):
        users = parse_users(" ".join(mode))
    else:
        users = []

    if not users:
        print("  " + col("[auto-send]", C.YELLOW)
              + " không có user")
        return

    msg = (cfg.get("auto_send_message") or "").strip()
    if not msg:
        msg = cfg.get("send_message_content", "")

    print("  " + col("[auto-send]", C.MAGENTA)
          + " gửi " + str(len(users)) + " user (mode: "
          + str(mode) + ")")

    await send_many(page, cfg, users, msg)


async def auto_send_loop(page, cfg, stop, wl, wl_lock, plk):
    start_logged = False
    while not stop.is_set():
        try:
            if not cfg.get("auto_send_enabled"):
                if start_logged:
                    start_logged = False
                await asyncio.sleep(10)
                continue
            if not page_alive(page):
                break

            try:
                raw = cfg.get("auto_send_time", "00:00")
                hh_s, mm_s = raw.split(":")
                hh, mm = int(hh_s), int(mm_s)
            except Exception:
                hh, mm = 0, 0

            tz_off = int(cfg.get("auto_send_timezone_offset", 7))
            secs = seconds_until_time(hh, mm, tz_off)

            if not start_logged:
                hrs = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                print("  " + col("[auto-send]", C.MAGENTA)
                      + " chờ " + str(hrs) + "h" + str(mins) + "m"
                      + " đến " + str(hh).zfill(2) + ":"
                      + str(mm).zfill(2) + " GMT+" + str(tz_off))
                start_logged = True

            waited = 0.0
            while waited < secs and not stop.is_set():
                chunk = min(60.0, secs - waited)
                await asyncio.sleep(chunk)
                waited += chunk

                remaining = secs - waited
                if 0 < remaining <= 60:
                    print("  " + col("[auto-send]", C.YELLOW)
                          + " còn " + str(int(remaining))
                          + "s → gửi...")

            if stop.is_set():
                break

            async with wl_lock:
                wl_copy = list(wl)

            try:
                async with plk:
                    await do_auto_send(page, cfg, wl_copy)
            except Exception as e:
                print("  " + col("[auto-send] err: "
                                 + str(e)[:80], C.RED))

            start_logged = False
            await asyncio.sleep(5)

        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(30)


# ============ menu ============
def show_menu(cfg, wl_n):
    ar_on = cfg.get("auto_reply_enabled")
    hd_on = cfg.get("headless")
    vb_on = cfg.get("auto_reply_verbose")
    as_on = cfg.get("auto_send_enabled")

    ar = col("BẬT", C.GREEN) if ar_on else col("TẮT", C.RED)
    hd = col("BẬT", C.GREEN) if hd_on else col("TẮT", C.GRAY)
    vb = col("BẬT", C.GREEN) if vb_on else col("TẮT", C.GRAY)
    asn = col("BẬT", C.GREEN) if as_on else col("TẮT", C.GRAY)

    mt = cfg.get("check_method", "inbox")
    mc = col(mt.upper(), C.GREEN if mt == "inbox" else C.YELLOW)

    uid_n = len(load_cache())
    atime = cfg.get("auto_send_time", "00:00")
    atz = cfg.get("auto_send_timezone_offset", 7)

    if SELF_STATUS["live"]:
        self_txt = "@" + str(SELF_STATUS["username"])
        if SELF_STATUS["nickname"]:
            self_txt += " (" + str(SELF_STATUS["nickname"]) + ")"
        st_color = C.GREEN
        st_tag = "[LIVE]"
    else:
        self_txt = "(chưa login)"
        st_color = C.RED
        st_tag = "[DIE]"

    print()
    print(col("  " + "=" * 64, C.CYAN))
    print(col("  ", C.CYAN) + col(TOOL_NAME.center(62),
                                   C.BOLD + C.WHITE))
    print(col("  " + "=" * 64, C.CYAN))
    print("  account: " + col(st_tag, st_color)
          + " " + col(self_txt, st_color))
    print("  watchlist: " + col(str(wl_n), C.YELLOW)
          + " | uid cache: " + col(str(uid_n), C.YELLOW)
          + " | method: " + mc)
    print("  headless: " + hd + " | verbose: " + vb
          + " | auto-send: " + asn
          + " (" + atime + " GMT+" + str(atz) + ")")
    print(col("  " + "-" * 64, C.GRAY))
    print("   " + col("1.", C.BOLD) + " gửi DM (nhập '*' = ALL cache)")
    print("   " + col("2.", C.BOLD) + " thêm user watchlist")
    print("   " + col("3.", C.BOLD) + " xem watchlist")
    print("   " + col("4.", C.BOLD) + " xóa user khỏi watchlist")
    print("   " + col("5.", C.BOLD) + " xóa HẾT watchlist")
    print(col("  " + "-" * 64, C.GRAY))
    print("   " + col("6.", C.BOLD) + " auto-reply: " + ar)
    print("   " + col("7.", C.BOLD) + " đổi method: " + mc)
    print("   " + col("8.", C.BOLD) + " trạng thái + toggle")
    print("   " + col("9.", C.BOLD) + " sửa template gửi")
    print("   " + col("10.", C.BOLD) + " gửi ALL cache")
    print(col("  " + "-" * 64, C.GRAY))
    print("   " + col("11.", C.BOLD) + " xem UID cache")
    print("   " + col("12.", C.BOLD) + " xóa 1 user cache")
    print("   " + col("13.", C.BOLD) + " xóa HẾT cache")
    print("   " + col("14.", C.BOLD) + " auto-send định kỳ GMT+7")
    print("   " + col("0.", C.BOLD) + " thoát")
    print()


async def ain(p):
    try:
        return await asyncio.to_thread(input, p)
    except (EOFError, KeyboardInterrupt):
        return ""


async def edit_template(cfg):
    print()
    print("  " + col("SỬA TEMPLATE GỬI", C.BOLD + C.CYAN))
    for line in cfg["send_message_content"].split("\n"):
        print("      " + col(line, C.GRAY))
    print()
    pv = render_msg(cfg["send_message_content"], "user123", "Nguyễn Văn A")
    print("  preview:")
    for line in pv.split("\n"):
        print("      " + line)
    print()
    print("  " + col("1", C.GREEN) + " gọn   "
          + col("2", C.GREEN) + " siêu gọn   "
          + col("3", C.GREEN) + " đầy đủ")
    print("  " + col("c", C.YELLOW) + " custom   "
          + col("0", C.GRAY) + " về")
    ch = (await ain("  > ")).strip()

    presets = {
        "1": (
            "🌸 REP CHUỖI TỰ ĐỘNG 🌸\n"
            "───────────\n"
            "\n"
            "Chào {nickname} 👋\n"
            "Chúc bạn một ngày tốt lành 💖\n"
            "\n"
            "📌 Made by: Nguyễn Hữu Minh Tiến"
        ),
        "2": (
            "Chào {nickname} 👋\n"
            "Chúc bạn một ngày tốt lành 💖\n"
            "\n"
            "🌸 Made by: Nguyễn Hữu Minh Tiến"
        ),
        "3": (
            "✨ REP CHUỖI TỰ ĐỘNG ✨\n"
            "───────────\n"
            "\n"
            "Xin chào {nickname} 👋\n"
            "Chúc bạn 1 ngày tốt lành 💖\n"
            "\n"
            "───────────\n"
            "🌸 Made by: Nguyễn Hữu Minh Tiến"
        ),
    }

    if ch in presets:
        cfg["send_message_content"] = presets[ch]
        save_cfg(cfg)
        ok("đã đổi")
        return
    if ch.lower() == "c":
        print("  Nhập (END để kết):")
        lines = []
        while True:
            ln = await ain("  ")
            if ln.strip() == "END":
                break
            lines.append(ln.replace("\\n", "\n"))
        if lines:
            cfg["send_message_content"] = "\n".join(lines)
            save_cfg(cfg)
            ok("đã lưu")


async def menu(page, cfg, tracker, stop, wl, wlk, plk):
    while not stop.is_set():
        if not page_alive(page):
            break
        try:
            await refresh_self_status(page)
        except Exception:
            pass
        async with wlk:
            n = len(wl)
        show_menu(cfg, n)
        ch = (await ain("  " + col(">", C.CYAN) + " Chọn: ")).strip()

        if ch == "1":
            raw = (await ain("  Username (hoặc '*'): ")).strip()
            if raw in ("*", "all", "ALL"):
                custom = (await ain(
                    "  Nội dung (Enter=mặc định): ")).strip()
                async with plk:
                    await send_all_cache(
                        page, cfg,
                        custom or cfg["send_message_content"])
                continue
            targets = parse_users(raw)
            if not targets:
                wn("không parse")
                continue
            custom = (await ain(
                "  Nội dung (Enter=mặc định): ")).strip()
            async with plk:
                await send_many(page, cfg, targets,
                                custom or cfg["send_message_content"])
            continue

        if ch == "2":
            raw = (await ain("  Username: ")).strip()
            parsed = parse_users(raw)
            added = []
            async with wlk:
                for x in parsed:
                    if x not in wl:
                        wl.append(x)
                        added.append(x)
                save_watchlist(wl)
            if not added:
                continue
            ok("thêm: " + ", ".join("@" + x for x in added))

            for u in added:
                if not get_cached(u):
                    try:
                        async with plk:
                            info = await get_user_info(page, u)
                            if info.get("uid"):
                                step("@" + u + " → uid=" + info["uid"]
                                     + " " + info.get("nickname", ""))
                            else:
                                wn("@" + u + " → uid fail")
                    except Exception as e:
                        wn("@" + u + " → err " + str(e)[:40])
            continue

        if ch == "3":
            async with wlk:
                lst = list(wl)
            if lst:
                print()
                for i, x in enumerate(lst, 1):
                    info = get_cached(x) or {}
                    print("   " + str(i) + ". @" + x
                          + "  uid=" + info.get("uid", "")
                          + "  " + info.get("nickname", ""))
            else:
                in4("trống")
            continue

        if ch == "4":
            async with wlk:
                lst = list(wl)
            if not lst:
                wn("trống")
                continue
            print()
            for i, x in enumerate(lst, 1):
                print("   " + col(str(i) + ".", C.YELLOW) + " @" + x)
            print("   " + col("a.", C.RED) + " xóa hết   "
                  + col("0.", C.GRAY) + " hủy")
            sel = (await ain("  > ")).strip().lower()
            if sel == "0":
                continue
            if sel == "a":
                yn = (await ain("  Xóa HẾT? (y/N): ")).strip().lower()
                if yn == "y":
                    async with wlk:
                        wl.clear()
                        save_watchlist(wl)
                    ok("đã xóa hết")
                continue
            try:
                i = int(sel) - 1
                if 0 <= i < len(lst):
                    async with wlk:
                        if lst[i] in wl:
                            wl.remove(lst[i])
                            save_watchlist(wl)
                    ok("đã xóa @" + lst[i])
            except Exception:
                pass
            continue

        if ch == "5":
            yn = (await ain("  Xóa HẾT? (y/N): ")).strip().lower()
            if yn == "y":
                async with wlk:
                    wl.clear()
                    save_watchlist(wl)
                ok("đã xóa hết")
            continue

        if ch == "6":
            cfg["auto_reply_enabled"] = not cfg.get(
                "auto_reply_enabled", True)
            save_cfg(cfg)
            st = "BẬT" if cfg["auto_reply_enabled"] else "TẮT"
            ok("auto-reply: " + st)
            continue

        if ch == "7":
            cur = cfg.get("check_method", "inbox")
            new = "watchlist" if cur == "inbox" else "inbox"
            cfg["check_method"] = new
            save_cfg(cfg)
            ok("method: " + new.upper())
            continue

        if ch == "8":
            print()
            print("  " + col("TRẠNG THÁI", C.BOLD + C.CYAN))
            print("   auto-reply: "
                  + ("BẬT" if cfg.get("auto_reply_enabled") else "TẮT"))
            print("   headless:   "
                  + ("BẬT" if cfg.get("headless") else "TẮT"))
            print("   verbose:    "
                  + ("BẬT" if cfg.get("auto_reply_verbose") else "TẮT"))
            print("   method:     "
                  + cfg.get("check_method", "inbox").upper())
            print("   cooldown:   "
                  + str(cfg["auto_reply_cooldown_minutes"]) + "p")
            print("   max age:    "
                  + str(cfg.get("auto_reply_max_message_age_minutes", 10)) + "p")
            print("   poll:       "
                  + str(cfg["poll_interval_seconds"]) + "s")
            print("   delay:      "
                  + str(cfg["send_delay_seconds"]) + "s")
            print()
            print("  " + col("1", C.GREEN) + " toggle headless")
            print("  " + col("2", C.GREEN) + " toggle verbose")
            print("  " + col("0", C.GRAY) + " về")
            sub = (await ain("  > ")).strip()
            if sub == "1":
                cfg["headless"] = not cfg.get("headless", False)
                save_cfg(cfg)
                wn("cần CHẠY LẠI tool để áp dụng")
            elif sub == "2":
                cfg["auto_reply_verbose"] = not cfg.get(
                    "auto_reply_verbose", False)
                save_cfg(cfg)
                st = "BẬT" if cfg["auto_reply_verbose"] else "TẮT"
                ok("verbose: " + st)
            continue

        if ch == "9":
            await edit_template(cfg)
            continue

        if ch == "10":
            custom = (await ain(
                "  Nội dung (Enter=mặc định): ")).strip()
            async with plk:
                await send_all_cache(
                    page, cfg,
                    custom or cfg["send_message_content"])
            continue

        if ch == "11":
            cache = load_cache()
            if not cache:
                in4("cache trống")
                continue
            print()
            for i, (u, info) in enumerate(sorted(cache.items()), 1):
                print("   " + str(i) + ". @" + u
                      + "  uid=" + info.get("uid", "")
                      + "  " + info.get("nickname", ""))
            continue

        if ch == "12":
            cache = load_cache()
            if not cache:
                in4("cache trống")
                continue
            users = sorted(cache.keys())
            print()
            for i, u in enumerate(users, 1):
                print("   " + col(str(i) + ".", C.YELLOW) + " @" + u)
            print("   " + col("0.", C.GRAY) + " hủy")
            sel = (await ain("  > ")).strip()
            if sel == "0" or not sel:
                continue
            try:
                i = int(sel) - 1
                if 0 <= i < len(users):
                    if remove_cached(users[i]):
                        ok("đã xóa @" + users[i])
            except Exception:
                pass
            continue

        if ch == "13":
            cache = load_cache()
            if not cache:
                in4("cache trống")
                continue
            n_c = len(cache)
            yn = (await ain(
                "  Xóa HẾT " + str(n_c) + " user? (y/N): "
            )).strip().lower()
            if yn == "y":
                save_cache({})
                ok("đã xóa hết cache")
            continue

        if ch == "14":
            print()
            print("  " + col("AUTO-SEND ĐỊNH KỲ", C.BOLD + C.CYAN))
            ae = "BẬT" if cfg.get("auto_send_enabled") else "TẮT"
            at = cfg.get("auto_send_time", "00:00")
            az = cfg.get("auto_send_timezone_offset", 7)
            atg = cfg.get("auto_send_targets", "cache")
            am = cfg.get("auto_send_message") or ""
            print("   enabled:  " + ae)
            print("   targets:  " + str(atg))
            print("   time:     " + at + " GMT+" + str(az))
            msg_s = "dùng template gửi" if not am else "custom"
            print("   message:  " + msg_s)
            print()
            print("  " + col("1", C.GREEN) + " toggle")
            print("  " + col("2", C.GREEN) + " đổi giờ (HH:MM)")
            print("  " + col("3", C.GREEN) + " đổi targets")
            print("  " + col("4", C.GREEN) + " đổi message custom")
            print("  " + col("0", C.GRAY) + " về")
            sub = (await ain("  > ")).strip()

            if sub == "1":
                cfg["auto_send_enabled"] = not cfg.get(
                    "auto_send_enabled", False)
                save_cfg(cfg)
                st = "BẬT" if cfg["auto_send_enabled"] else "TẮT"
                ok("auto-send: " + st)
            elif sub == "2":
                t = (await ain("  Giờ (HH:MM): ")).strip()
                try:
                    hh_s, mm_s = t.split(":")
                    hh, mm = int(hh_s), int(mm_s)
                    if 0 <= hh <= 23 and 0 <= mm <= 59:
                        cfg["auto_send_time"] = (
                            str(hh).zfill(2) + ":" + str(mm).zfill(2))
                        save_cfg(cfg)
                        ok("giờ: " + cfg["auto_send_time"])
                    else:
                        er("giờ không hợp lệ")
                except Exception:
                    er("format sai")
            elif sub == "3":
                print("  1=cache  2=watchlist  3=list user")
                t = (await ain("  > ")).strip()
                if t == "1":
                    cfg["auto_send_targets"] = "cache"
                elif t == "2":
                    cfg["auto_send_targets"] = "watchlist"
                elif t == "3":
                    lst = (await ain("  usernames: ")).strip()
                    cfg["auto_send_targets"] = parse_users(lst)
                else:
                    continue
                save_cfg(cfg)
                ok("targets: " + str(cfg["auto_send_targets"]))
            elif sub == "4":
                m = (await ain(
                    "  Message (Enter=xóa về mặc định): ")).strip()
                cfg["auto_send_message"] = m
                save_cfg(cfg)
                ok("đã lưu")
            continue

        if ch == "0":
            print("  " + col("thoát...", C.YELLOW))
            stop.set()
            break
        wn("không hợp lệ")


# ============ runner ============
async def open_browser_and_page(cfg):
    # fail closed trước: thiếu/khỏe token → dừng ngay, không mở browser
    cookies = load_cookies()
    pw = await async_playwright().start()
    is_headless = bool(cfg.get("headless"))
    launch = {
        "headless": is_headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--no-sandbox",
        ],
    }
    if not is_headless:
        launch["args"].append("--start-maximized")
        ch_b = (cfg.get("browser_channel") or "").strip()
        if ch_b:
            launch["channel"] = ch_b

    try: 
        browser = await pw.chromium.launch(**launch)
    except Exception as e:
        wn("launch fail: " + str(e)[:60])
        launch.pop("channel", None)
        browser = await pw.chromium.launch(**launch)

    ctx = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=cfg["user_agent"],
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
    )
    await ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', "
        "{get: () => undefined});"
    )

    try:
        n_ok = await add_cookies_to_ctx(ctx, cookies)
        ok(str(n_ok) + "/" + str(len(cookies)) + " cookies")
        page = await ctx.new_page()
    except Exception:
        # không rò rỉ browser process nếu giữa chừng hỏng
        for closeable in (ctx, browser):
            try:
                await closeable.close()
            except Exception:
                pass
        try:
            await pw.stop()
        except Exception:
            pass
        raise
    return pw, browser, ctx, page


async def run():
    print()
    print(col("  " + "=" * 64, C.CYAN))
    print(col("  ", C.CYAN) + col(TOOL_NAME.center(62),
                                   C.BOLD + C.WHITE))
    print(col("  " + "=" * 64, C.CYAN))

    cfg = load_cfg()
    pw, browser, ctx, page = await open_browser_and_page(cfg)

    in4("check login...")
    try:
        await page.goto("https://www.tiktok.com/?lang=" + LANG,
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(8)
        await refresh_self_status(page)
        if SELF_STATUS["live"]:
            ok("login: @" + SELF_STATUS["username"]
               + " (" + SELF_STATUS["nickname"] + ")")
        else:
            wn("chưa login (có thể chưa load kịp)")
    except Exception as e:
        er(str(e)[:60])

    tracker = Tracker(int(cfg["auto_reply_cooldown_minutes"]))
    stop = asyncio.Event()
    wl = load_watchlist()
    wlk = asyncio.Lock()
    plk = asyncio.Lock()
    last_msg_state = {}

    ar_task = asyncio.create_task(
        auto_reply_loop(page, cfg, tracker, stop, wl, wlk, plk,
                        last_msg_state))
    as_task = asyncio.create_task(
        auto_send_loop(page, cfg, stop, wl, wlk, plk))

    try:
        await menu(page, cfg, tracker, stop, wl, wlk, plk)
    except KeyboardInterrupt:
        print()
        print("  " + col("dừng...", C.YELLOW))

    stop.set()
    for t in (ar_task, as_task):
        try:
            t.cancel()
        except Exception:
            pass
    for t in (ar_task, as_task):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    try:
        await browser.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass
    print("  " + col("đã thoát", C.GREEN))


async def run_daemon(cfg):
    print()
    print(col("  " + "=" * 64, C.CYAN))
    print(col("  ", C.CYAN) + col(TOOL_NAME.center(62),
                                   C.BOLD + C.WHITE))
    print(col("  " + "=" * 64, C.CYAN))
    print("  " + col("[DAEMON MODE]", C.YELLOW)
          + " chạy ngầm không menu")
    print("  Ctrl+C để dừng")
    print()

    pw, browser, ctx, page = await open_browser_and_page(cfg)

    try:
        await page.goto("https://www.tiktok.com/?lang=" + LANG,
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(8)
        await refresh_self_status(page)
        if SELF_STATUS["live"]:
            ok("login: @" + SELF_STATUS["username"]
               + " (" + SELF_STATUS["nickname"] + ")")
        else:
            wn("chưa login?")
    except Exception:
        pass

    tracker = Tracker(int(cfg["auto_reply_cooldown_minutes"]))
    stop = asyncio.Event()
    wl = load_watchlist()
    wlk = asyncio.Lock()
    plk = asyncio.Lock()
    last_msg_state = {}

    ar_task = asyncio.create_task(
        auto_reply_loop(page, cfg, tracker, stop, wl, wlk, plk,
                        last_msg_state))
    as_task = asyncio.create_task(
        auto_send_loop(page, cfg, stop, wl, wlk, plk))

    try:
        while not stop.is_set():
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

    stop.set()
    for t in (ar_task, as_task):
        try:
            t.cancel()
        except Exception:
            pass
    for t in (ar_task, as_task):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    try:
        await browser.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass
    print("  " + col("đã thoát", C.GREEN))


async def run_send_mode(cfg, target_raw, message=None):
    pw, browser, ctx, page = await open_browser_and_page(cfg)
    try:
        await page.goto("https://www.tiktok.com/?lang=" + LANG,
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await send_many(page, cfg, parse_users(target_raw),
                        message or cfg["send_message_content"])
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="")
    ap.add_argument("--message", default="")
    ap.add_argument("--daemon", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg()

    if args.target:
        asyncio.run(run_send_mode(cfg, args.target, args.message))
        return

    if args.daemon:
        asyncio.run(run_daemon(cfg))
        return

    asyncio.run(run())


if __name__ == "__main__":
    main()