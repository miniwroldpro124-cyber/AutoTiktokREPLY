# TikTok Auto Reply — Panel (Vercel)

Web panel điều khiển bot TikTok selfbot: menu tổng quan, auto-reply, watchlist, gửi tin,
nhật ký, nhập token/cookie TikTok. Panel chạy trên Vercel (24/7), bot Playwright chạy
trong worker riêng (docker) nối với panel qua `WORKER_URL`.

## Cấu trúc

```
site/
  app/                    # Next.js App Router
    page.js               # Tổng quan (status, toggle nhanh, log)
    auto-reply/page.js    # Mẫu tin, cooldown, chu kỳ quét
    watchlist/page.js     # Thêm/xóa/resolve UID
    send/page.js          # Gửi DM hàng loạt + preview
    settings/page.js      # Nhập token/cookie, webhook, trình duyệt, auto-send
    logs/page.js          # Log worker realtime
    api/bot/[...slug]/    # Proxy toàn bộ /api/* → worker
    api/health/route.js
  components/             # Sidebar, status badge, UI kit, toast
  lib/api.js              # client fetch helpers
  lib/token.js            # parser cookie/token (JSON, document.cookie, sessionid trần)
```

## Deploy lên Vercel

```bash
cd site
npm install
npx vercel            # lần đầu: link project
npx vercel --prod     # deploy production
```

Hoặc import repo trên vercel.com → Framework: **Next.js** → Deploy.

### Environment (Project Settings → Environment Variables)

| Key | Ví dụ | Ý nghĩa |
|---|---|---|
| `WORKER_URL` | `https://bot-worker.onrender.com` | URL worker 24/7 |
| `WORKER_API_KEY` | `chimian-bat-ki` | Khóa giống `WORKER_API_KEY` của worker |

## Worker 24/7

Worker chạy Playwright headless trong docker — xem `../DEPLOY.md` và `../Dockerfile`.
Panel không tự chạy browser: Vercel không giữ process nền, nên browser nằm ở worker.

## API (worker, panel proxy nguyên xi)

```
GET    /api/status
GET    /api/config            PUT /api/config            (merge partial)
GET    /api/watchlist         POST /api/watchlist        {users: "raw"}
DEL    /api/watchlist         DEL /api/watchlist/:user   POST /api/watchlist/lookup
GET    /api/logs?limit=500    POST /api/logs/clear
POST   /api/send              {targets, message, delay_seconds}
POST   /api/auth/import       {raw}                      {raw: cookie/token}
POST   /api/auth/test
```

## Chạy local

```bash
cd site
npm run dev          # http://localhost:3000
# set WORKER_URL=http://127.0.0.1:8787 trong .env.local nếu worker chạy local
```
