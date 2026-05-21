"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, FileText, Settings, LogOut, Zap, ChevronLeft, ChevronRight, UserCircle2, Download
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useDispatch, useSelector } from "react-redux";
import { logout } from "@/lib/redux/slices/authSlice";
import { logoutAction } from "@/app/actions/auth";
import { RootState } from "@/lib/redux/store";


const navItems = [
  { title: "Dashboard", icon: LayoutDashboard, path: "/dashboard" },
  { title: "Invoices",  icon: FileText,         path: "/dashboard/invoices" },
  { title: "Export",    icon: Download,         path: "/dashboard/export" },
  { title: "Settings",  icon: Settings,          path: "/dashboard/settings" },
];

export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);

  const initials = user?.name
    ?.split(" ")
    .map((n: string) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) ?? "U";

  const handleLogout = async () => {
    dispatch(logout());
    await logoutAction();
    router.refresh();
  };

  return (
    <>
      {/* ── Desktop Sidebar ───────────────────────────────── */}
      <aside
        className={cn(
          "hidden md:flex flex-col h-screen bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-all duration-300 shrink-0 z-30",
          collapsed ? "w-[68px]" : "w-[220px]"
        )}
      >
        {/* Logo */}
        <div className={cn(
          "flex items-center h-16 border-b border-sidebar-border px-4 gap-3",
          collapsed && "justify-center px-0"
        )}>
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sidebar-primary shrink-0">
            <Zap className="w-4 h-4 text-sidebar-primary-foreground" />
          </div>
          {!collapsed && (
            <span className="font-bold text-base text-sidebar-accent-foreground tracking-tight truncate">
              LedgerAI
            </span>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-4 space-y-1">
          {navItems.map((item) => {
          const active = item.path === "/dashboard"
              ? pathname === "/dashboard"
              : pathname === item.path || pathname.startsWith(`${item.path  }/`);
            return (
              <Link
                key={item.path}
                href={item.path}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200",
                  collapsed ? "justify-center px-0" : "",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm"
                    : "text-sidebar-muted hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                )}
                title={collapsed ? item.title : undefined}
              >
                <item.icon className="w-5 h-5 shrink-0" />
                {!collapsed && <span>{item.title}</span>}
                {active && !collapsed && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-sidebar-primary" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Bottom: user + logout */}
        <div className="border-t border-sidebar-border p-3 space-y-1">
          {/* User chip */}
          {!collapsed && (
            <div className="flex items-center gap-3 px-3 py-2 rounded-xl bg-sidebar-accent/40 mb-2">
              <div className="w-9 h-9 rounded-full bg-sidebar-primary/20 border border-sidebar-primary/30 flex items-center justify-center shrink-0">
                <UserCircle2 className="w-5 h-5 text-sidebar-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-sidebar-accent-foreground truncate">{user?.name || "User"}</p>
                <p className="text-xs text-sidebar-muted truncate">{user?.email ?? ""}</p>
              </div>
            </div>
          )}
          {collapsed && (
            <div className="flex justify-center mb-2">
              <div className="w-9 h-9 rounded-full bg-sidebar-primary/20 border border-sidebar-primary/30 flex items-center justify-center">
                <UserCircle2 className="w-5 h-5 text-sidebar-primary" />
              </div>
            </div>
          )}

          {/* Logout */}
          <button
            onClick={handleLogout}
            className={cn(
              "flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 text-sidebar-muted hover:bg-red-500/10 hover:text-red-400",
              collapsed ? "justify-center px-0" : ""
            )}
            title={collapsed ? "Logout" : undefined}
          >
            <LogOut className="w-5 h-5 shrink-0" />
            {!collapsed && <span>Logout</span>}
          </button>

          {/* Collapse toggle */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className={cn(
              "flex items-center gap-3 w-full px-3 py-2 rounded-xl text-xs text-sidebar-muted hover:bg-sidebar-accent/40 hover:text-sidebar-accent-foreground transition-all",
              collapsed ? "justify-center px-0" : ""
            )}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : (
              <>
                <ChevronLeft className="w-4 h-4" />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>

      {/* ── Mobile Bottom Navigation Bar ─────────────────── */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-card/95 backdrop-blur-lg flex items-center justify-around px-2 py-1 safe-area-pb">
        {navItems.map((item) => {
          const active = item.path === "/dashboard"
            ? pathname === "/dashboard"
            : pathname === item.path || pathname.startsWith(`${item.path  }/`);
          return (
            <Link
              key={item.path}
              href={item.path}
              className={cn(
                "flex flex-col items-center gap-0.5 px-4 py-2 rounded-xl flex-1 transition-all duration-200",
                active
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <item.icon className={cn("w-5 h-5", active && "scale-110")} />
              <span className="text-[10px] font-medium leading-none">{item.title}</span>
              {active && <span className="w-1 h-1 rounded-full bg-primary mt-0.5" />}
            </Link>
          );
        })}
        <button
          onClick={handleLogout}
          className="flex flex-col items-center gap-0.5 px-4 py-2 rounded-xl flex-1 text-muted-foreground hover:text-red-500 transition-colors"
        >
          <LogOut className="w-5 h-5" />
          <span className="text-[10px] font-medium leading-none">Logout</span>
        </button>
      </nav>
    </>
  );
}
