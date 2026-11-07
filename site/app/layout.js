import "./globals.css";
import Sidebar from "../components/Sidebar";
import StatusBadge from "../components/StatusBadge";
import ToastHost from "../components/Toast";

export const metadata = {
  title: "TikTok Auto Reply — Panel",
  description: "Điều khiển bot TikTok: auto-reply, watchlist, gửi tin, token login",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>
        <div className="shell">
          <Sidebar />
          <main className="main">
            <header className="topbar">
              <div className="crumb">TikTok Auto Reply · Control Panel</div>
              <StatusBadge />
            </header>
            <div className="content">{children}</div>
          </main>
        </div>
        <ToastHost />
      </body>
    </html>
  );
}
