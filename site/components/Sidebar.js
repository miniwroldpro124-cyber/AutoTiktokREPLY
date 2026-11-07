"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ICONS = {
  grid: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  chat: (
    <>
      <path d="M20.5 12.2c0 4-3.8 7.2-8.5 7.2-1.1 0-2.2-.2-3.2-.5L4 20.5l1.6-4.2C4.6 15.2 3.5 13.8 3.5 12.2 3.5 8.2 7.3 5 12 5s8.5 3.2 8.5 7.2z" />
      <path d="M8.5 11.5h7M8.5 14.5h4.5" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
      <path d="M16 5.3a3.5 3.5 0 0 1 0 5.4M17.5 14.6c2.1.8 3.5 2.7 3.5 5.4" />
    </>
  ),
  send: (
    <>
      <path d="M21 3.5 10.5 14" />
      <path d="M21 3.5l-6.6 17-3.9-7.5L3 9.1z" />
    </>
  ),
  term: (
    <>
      <rect x="3" y="4.5" width="18" height="15" rx="2" />
      <path d="M7 9.5l3 2.5-3 2.5M12.5 14.5H17" />
    </>
  ),
  gear: (
    <>
      <path d="M4 7.5h9M17 7.5h3M4 16.5h3M11 16.5h9" />
      <circle cx="15" cy="7.5" r="2.2" />
      <circle cx="9" cy="16.5" r="2.2" />
    </>
  ),
};

const NAV = [
  { group: "Điều khiển" },
  { href: "/", label: "Tổng quan", icon: "grid" },
  { href: "/auto-reply", label: "Auto-Reply", icon: "chat" },
  { href: "/watchlist", label: "Watchlist", icon: "users" },
  { href: "/send", label: "Gửi tin", icon: "send" },
  { group: "Hệ thống" },
  { href: "/logs", label: "Nhật ký", icon: "term" },
  { href: "/settings", label: "Cài đặt", icon: "gear" },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="dot" />
        <div>
          <b>TT AUTO</b>
          <span>selfbot panel v1.0</span>
        </div>
      </div>
      <nav className="nav">
        {NAV.map((n, i) =>
          n.group ? (
            <div className="grp" key={"g" + i}>{n.group}</div>
          ) : (
            <Link key={n.href} href={n.href} className={path === n.href ? "on" : ""}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                {ICONS[n.icon]}
              </svg>
              <span>{n.label}</span>
            </Link>
          )
        )}
      </nav>
      <div className="foot">
        Playwright worker 24/7<br />
        Panel host: Vercel
      </div>
    </aside>
  );
}
