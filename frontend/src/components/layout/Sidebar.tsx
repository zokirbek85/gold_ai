"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity, TrendingUp, LineChart, Zap, BarChart3,
  Newspaper, Calendar, FlaskConical, BookOpen, Brain,
  Settings, Shield, LogOut, Telescope,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_GROUPS = [
  {
    label: "Overview",
    items: [
      { href: "/dashboard", icon: Activity, label: "Dashboard" },
      { href: "/market", icon: TrendingUp, label: "Live Market" },
      { href: "/charts",   icon: LineChart,  label: "Live Chart" },
      { href: "/forecast", icon: Telescope,  label: "Forecast"   },
    ],
  },
  {
    label: "Trading",
    items: [
      { href: "/signals", icon: Zap, label: "Signals" },
      { href: "/analysis", icon: BarChart3, label: "Market Analysis" },
      { href: "/journal", icon: BookOpen, label: "Trade Journal" },
      { href: "/backtesting", icon: FlaskConical, label: "Backtesting" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/news", icon: Newspaper, label: "News" },
      { href: "/economic-calendar", icon: Calendar, label: "Econ Calendar" },
      { href: "/ml", icon: Brain, label: "Machine Learning" },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/settings", icon: Settings, label: "Settings" },
      { href: "/admin", icon: Shield, label: "Admin Panel" },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    router.push("/login");
  }

  const isActive = (href: string) =>
    pathname === href || (href !== "/" && pathname.startsWith(href + "/"));

  return (
    <aside
      className="w-56 shrink-0 flex flex-col h-screen sticky top-0 overflow-hidden"
      style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}
    >
      {/* Logo */}
      <div className="px-4 py-4 flex items-center gap-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-[13px] font-bold"
          style={{ background: "rgba(245,166,35,0.12)", color: "var(--gold)" }}
        >
          AU
        </div>
        <div className="min-w-0">
          <p className="text-sm font-bold leading-tight" style={{ color: "var(--gold)" }}>GOLD AI</p>
          <p className="text-[10px] leading-tight" style={{ color: "var(--text-faint)" }}>Trading Intelligence</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
        {NAV_GROUPS.map(group => (
          <div key={group.label}>
            <p
              className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest"
              style={{ color: "var(--text-faint)" }}
            >
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map(({ href, icon: Icon, label }) => {
                const active = isActive(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] transition-all duration-150 relative group",
                      active
                        ? "font-medium"
                        : "font-normal hover:bg-[var(--surface-2)]"
                    )}
                    style={active ? {
                      background: "rgba(245,166,35,0.1)",
                      color: "var(--gold)",
                    } : {
                      color: "var(--text-muted)",
                    }}
                  >
                    {active && (
                      <span
                        className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-r"
                        style={{ background: "var(--gold)" }}
                      />
                    )}
                    <Icon className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-2" style={{ borderTop: "1px solid var(--border)" }}>
        <button
          onClick={logout}
          className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] w-full transition-colors duration-150"
          style={{ color: "var(--text-faint)" }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLElement).style.color = "var(--red)";
            (e.currentTarget as HTMLElement).style.background = "rgba(239,68,68,0.08)";
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLElement).style.color = "var(--text-faint)";
            (e.currentTarget as HTMLElement).style.background = "transparent";
          }}
        >
          <LogOut className="w-3.5 h-3.5 shrink-0" />
          Sign Out
        </button>
        <p className="text-[10px] text-center mt-2" style={{ color: "var(--text-faint)" }}>
          Gold AI v2.0 · {new Date().getFullYear()}
        </p>
      </div>
    </aside>
  );
}
