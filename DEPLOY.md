# Deploy 24/7 — worker + panel

## 0. Upload an toàn (chạy trước khi push / `npx vercel`)

Repo có `.gitignore` sẵn — các file sau **không bao giờ** lên GitHub/Vercel:

| file | vì sao |
|---|---|
| `cookies.json` (+ `.bak-*`) | session TikTok thật — ai có là vào được tài khoản |
| `config.json` | chứa Discord webhook token |
| `uids.json`, `watchlist.json`, `*.log` | dữ liệu runtime, tạo lại trên server |
| `site/.env.local`, `.env` | env cá nhân |

- Vercel chỉ nhận thư mục `site/` — env (`WORKER_URL`, `WORKER_API_KEY`)
  set ở **Settings → Environment Variables**, không commit.
- Chạy thử trước khi push: `git status` — không có file đỏ nào trong list trên.
- Lần đầu chạy worker ở máy mới: `config.json` tự tạo với cấu hình mặc định.

Kiến trúc 2 mảnh:

```
[Vercel]  panel Next.js (site/)      ← 24/7, không cần worker vẫn mở được
    │  WORKER_URL + WORKER_API_KEY
[host]    worker Playwright (Docker) ← 24/7, giữ session TikTok + auto-reply
```

Vercel **không** chạy được browser nền (function hết hạn sau mỗi request), nên
Playwright nằm trong worker container. Panel chỉ là điều khiển + hiển thị.

## 1. Worker local (chạy thử)

```powershell
cd C:\Users\LaptopAT\Documents\tiktok_selfbot
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\playwright install chromium
.\.venv\Scripts\python worker.py
# API: http://127.0.0.1:8787/api/health
```

Panel local: `cd site`, tạo `.env.local` theo `site/.env.example`
(`WORKER_URL=http://127.0.0.1:8787` + `WORKER_API_KEY`), rồi `npm run start`.

**Khóa API:** tạo file `.env` ở gốc thư mục bot chứa `WORKER_API_KEY=<khóa>`
— worker tự nạp `.env` khi khởi động, docker compose cũng đọc file này.
Panel tự gắn header `x-api-key`. Ngoại lệ: `/api/health` trả lời không cần
khóa (Docker healthcheck/uptime monitor), mọi route khác trả `401` nếu sai
khóa. Không set khóa = API mở toang — chỉ để local, không bao giờ expose
công khai.

## 2. Worker bằng Docker (khuyến nghị)

```bash
docker compose up -d --build
curl http://127.0.0.1:8787/api/health
docker compose logs -f          # xem log
```

- Dữ liệu (config/cookies/uids/watchlist/cooldowns) nằm trong volume
  `bot-data` → `/app/data`, sống sót qua rebuild.
- `restart: unless-stopped` → container tự bật lại khi máy/daemon khởi động.
- Đổi khóa API: sửa `.env` (WORKER_API_KEY=...) rồi `docker compose up -d`.

## 3. Host 24/7 — chọn 1

**Render.com (dễ nhất)**
1. Push repo lên GitHub → New → Web Service → chọn repo.
2. Environment = **Docker**, root directory = thư mục chứa Dockerfile.
3. Add **Disk** (mount path `/app/data`) để dữ liệu không mất khi redeploy.
4. Env: `WORKER_API_KEY=<khóa>`. Lấy URL `https://xxx.onrender.com`.
5. Free tier ngủ sau 15 phút idle → cần paid starter cho 24/7 thật.

**Fly.io**
```bash
fly launch --no-deploy
fly volumes create bot_data --size 1 --region sin
# trong fly.toml: [mounts] source="bot_data" destination="/app/data"
fly deploy
```

**VPS (DigitalOcean/Hetzner/Vultr — 24/7 thật, ~$4/tháng)**
```bash
ssh root@<ip>
git clone <repo> && cd <repo>
echo "WORKER_API_KEY=chimian" > .env
docker compose --env-file .env up -d --build
# restart khi reboot: compose đã có restart: unless-stopped
```

## 4. Nối panel (Vercel)

1. `cd site && npx vercel --prod` (xem `site/README.md`).
2. Vercel project → Settings → Environment Variables:
   - `WORKER_URL` = URL worker, ví dụ `https://tiktok-worker.onrender.com`
   - `WORKER_API_KEY` = đúng khóa đã set cho worker
3. Deployments → Redeploy (env chỉ áp dụng khi redeploy).

## 5. Đăng nhập TikTok

Panel → **Cài đặt** → dán cookie/token (JSON EditThisCookie, `document.cookie`,
hoặc token `sessionid` trần) → **Nhập vào worker**. Worker mã hóa AES (Fernet)
thành `cookies.enc` rồi làm lại session — plaintext không được ghi ra đĩa.
Khóa nằm ở `secret.key` (tự sinh lần đầu, nằm cùng volume data). Hai file
này đi cùng nhau: mất volume → dán lại cookie là xong. Hết hạn cũng dán lại —
không cần đụng server.

## 6. Kiểm tra 24/7

```bash
curl https://<worker>/api/health          # {"ok":true,...}
# panel: badge LIVE @username, uptime tăng đều = đang sống
```

- Worker tự mở lại session nếu browser chết (keepalive 60s).
- Healthcheck Docker tự restart container nếu API chết.
- Log ring buffer 1500 dòng: panel → Nhật ký (không mất khi page reload).

## API worker

```
GET    /api/status                 # live, avatar, watchlist, config, detect
GET    /api/config    PUT /api/config        # PUT = merge partial
GET    /api/watchlist POST /api/watchlist    # {users:"raw"} → auto resolve uid+avatar
DEL    /api/watchlist DEL /api/watchlist/:u  POST /api/watchlist/lookup
GET    /api/users                 # cache + avatar + nickname
GET    /api/logs?limit=500        POST /api/logs/clear
POST   /api/send                  # {targets, message, delay_seconds} → queued
POST   /api/auth/import           # {raw} → nạp cookie + restart session
POST   /api/auth/test             POST /api/detect
POST   /api/lookup                # {input} link/username → uid + nickname + avatar
```

Header `x-api-key: <WORKER_API_KEY>` nếu có set khóa (panel tự gắn).
