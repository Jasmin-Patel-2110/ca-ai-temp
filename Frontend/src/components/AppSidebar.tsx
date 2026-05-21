import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Upload, Files, FileText, BarChart3,
  Settings, ChevronLeft, ChevronRight, Zap, LogOut, Download
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useDispatch } from "react-redux";
import { logout } from "@/lib/redux/slices/authSlice";


const mainMenuItems = [
  { title: "Dashboard", icon: LayoutDashboard, path: "/dashboard" },
  { title: "Upload Invoice", icon: Upload, path: "/upload" },
  { title: "Bulk Upload", icon: Files, path: "/bulk-upload" },
  { title: "Invoices", icon: FileText, path: "/invoices" },
  { title: "Reports", icon: BarChart3, path: "/reports" },
  { title: "Export", icon: Download, path: "/dashboard/export" },
];

const footerMenuItems = [
  { title: "Settings", icon: Settings, path: "/settings" },
];

export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const dispatch = useDispatch();

  const handleLogout = () => {
    dispatch(logout());
    localStorage.removeItem("token");
    router.push("/login");


  };

  return (
    <aside
      className={cn(
        "flex flex-col h-screen bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-all duration-300 shrink-0",
        collapsed ? "w-16" : "w-60"
      )}
    >
      <div className="flex items-center gap-2 px-4 h-16 border-b border-sidebar-border">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sidebar-primary">
          <Zap className="w-4 h-4 text-sidebar-primary-foreground" />
        </div>
        {!collapsed && (
          <span className="font-bold text-lg text-sidebar-accent-foreground tracking-tight">
            LedgerAI
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col justify-between py-4">
        <nav className="space-y-1 px-2">
          {mainMenuItems.map((item) => {
            const active = pathname === item.path;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                )}
              >
                <item.icon className="w-5 h-5 shrink-0" />
                {!collapsed && <span>{item.title}</span>}
              </Link>
            );
          })}
        </nav>

        <div>
          <nav className="space-y-1 px-2">
            {footerMenuItems.map((item) => {
              const active = pathname === item.path;
              return (
                <Link
                  key={item.path}
                  href={item.path}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                    active
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  )}
                >
                  <item.icon className="w-5 h-5 shrink-0" />
                  {!collapsed && <span>{item.title}</span>}
                </Link>
              );
            })}
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-accent-foreground w-full"
            >
              <LogOut className="w-5 h-5 shrink-0" />
              {!collapsed && <span>Logout</span>}
            </button>
          </nav>

          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center justify-center h-12 border-t border-sidebar-border text-sidebar-muted hover:text-sidebar-accent-foreground transition-colors w-full mt-4"
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </aside>
  );
}
