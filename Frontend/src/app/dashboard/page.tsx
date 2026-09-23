"use client";

import { useEffect, useState } from "react";
import {
  FileText,
  Clock,
  CheckCircle,
  UserCircle2,
  RefreshCw,
} from "lucide-react";
import { useSelector } from "react-redux";
import { RootState } from "@/lib/redux/store";
import { motion } from "framer-motion";
import {
  getDashboardStats,
  DashboardData,
  RecentInvoice,
} from "@/app/actions/dashboard";

// ── Status style map (normalised to lowercase keys from API) ──────────────────
const statusStyles: Record<string, { bg: string; text: string; dot: string }> =
  {
    verified: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
    pending_verification: {
      bg: "bg-warning/10",
      text: "text-warning",
      dot: "bg-warning",
    },
    pending_extraction: {
      bg: "bg-primary/10",
      text: "text-primary",
      dot: "bg-primary",
    },
    error: {
      bg: "bg-destructive/10",
      text: "text-destructive",
      dot: "bg-destructive",
    },
  };

function formatStatus(status: string) {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatAmount(total: string | null) {
  if (!total) return "—";
  const num = parseFloat(total);
  if (isNaN(num)) return "—";
  return `₹${num.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

type DashboardLoadResult =
  | { data: DashboardData; error?: never }
  | { data?: never; error: string };

async function loadDashboard(userId: string): Promise<DashboardLoadResult> {
  const result = await getDashboardStats();
  if (!result.success || !result.data) {
    return { error: result.error ?? "Failed to load data" };
  }

  let data = result.data;

  try {
    const url = `${process.env.NEXT_PUBLIC_API_URL ?? ""}/invoices/all?user_id=${encodeURIComponent(userId)}`;
    const token = localStorage.getItem("auth_token");
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.ok) {
      const json: { invoices?: RecentInvoice[] } = await response.json();
      if (json.invoices) {
        const recentInvoices = [...json.invoices]
          .sort((a, b) => (b.id || 0) - (a.id || 0))
          .slice(0, 5);
        data = { ...data, recent_invoices: recentInvoices };
      }
    }
  } catch {
    // Dashboard statistics remain usable when recent invoice enrichment fails.
  }

  return { data };
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.09 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] as const },
  },
};

// ── Skeleton loader ───────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="bg-card border border-border rounded-2xl p-5 animate-pulse">
      <div className="flex justify-between mb-4">
        <div className="w-10 h-10 rounded-xl bg-muted" />
        <div className="w-14 h-5 rounded-full bg-muted" />
      </div>
      <div className="w-20 h-8 rounded bg-muted mb-2" />
      <div className="w-32 h-4 rounded bg-muted mb-1" />
      <div className="w-24 h-3 rounded bg-muted" />
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useSelector((state: RootState) => state.auth);
  const firstName = user?.name?.split(" ")[0] ?? "there";
  const fullName = user?.name ?? "";
  const userId = String(user?.sub ?? "6");

  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  // ── API state ─────────────────────────────────────────────────────────────
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = async () => {
    setLoading(true);
    setError(null);
    const result = await loadDashboard(userId);
    if (result.data) {
      setData(result.data);
    } else {
      setError(result.error);
    }
    setLoading(false);
  };

  useEffect(() => {
    let cancelled = false;

    void loadDashboard(userId).then((result) => {
      if (cancelled) return;

      if (result.data) {
        setData(result.data);
      } else {
        setError(result.error);
      }
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  // ── Stat cards config ─────────────────────────────────────────────────────
  const statCards = [
    {
      label: "Total Invoices",
      value: data?.total_invoices ?? 0,
      icon: FileText,
      iconBg: "bg-primary/10",
      iconColor: "text-primary",
      borderAccent: "border-l-primary",
      description: "Total processed",
    },
    {
      label: "Pending Verification",
      value: data?.total_pending_verification ?? 0,
      icon: Clock,
      iconBg: "bg-warning/10",
      iconColor: "text-warning",
      borderAccent: "border-l-warning",
      description: "Awaiting review",
    },
    {
      label: "Created Today",
      value: data?.total_created_today ?? 0,
      icon: CheckCircle,
      iconBg: "bg-success/10",
      iconColor: "text-success",
      borderAccent: "border-l-success",
      description: "Invoices created today",
    },
  ];

  const recentInvoices: RecentInvoice[] = data?.recent_invoices ?? [];

  return (
    <motion.div
      className="space-y-6"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* ── Welcome Banner ───────────────────────────────────────────────── */}
      <motion.div
        variants={itemVariants}
        className="relative overflow-hidden rounded-2xl shadow-xl"
        style={{
          background:
            "linear-gradient(135deg, #0f2167 0%, #1a3a8f 35%, #1e52c4 65%, #2563eb 100%)",
          minHeight: 200,
        }}
      >
        <motion.div
          className="pointer-events-none absolute rounded-full"
          style={{
            width: 280,
            height: 280,
            top: -80,
            right: -60,
            background:
              "radial-gradient(circle, rgba(99,179,237,0.35) 0%, transparent 70%)",
          }}
          animate={{ scale: [1, 1.15, 1], x: [0, 15, 0], y: [0, -10, 0] }}
          transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="pointer-events-none absolute rounded-full"
          style={{
            width: 200,
            height: 200,
            bottom: -60,
            left: 40,
            background:
              "radial-gradient(circle, rgba(167,139,250,0.3) 0%, transparent 70%)",
          }}
          animate={{ scale: [1, 1.2, 1], x: [0, -12, 0], y: [0, 12, 0] }}
          transition={{
            duration: 9,
            repeat: Infinity,
            ease: "easeInOut",
            delay: 2,
          }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "radial-gradient(circle, white 1px, transparent 1px)",
            backgroundSize: "22px 22px",
          }}
        />
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.04) 50%, transparent 60%)",
          }}
        />

        <div className="relative p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2 mb-4">
                <motion.span
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full"
                  style={{
                    background: "rgba(255,255,255,0.15)",
                    backdropFilter: "blur(8px)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    color: "rgba(255,255,255,0.9)",
                  }}
                  animate={{ opacity: [0.8, 1, 0.8] }}
                  transition={{ duration: 2.5, repeat: Infinity }}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  System Active
                </motion.span>
                <span className="text-xs text-white/50">{today}</span>
              </div>

              <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-white">
                {getGreeting()},
                <br className="hidden sm:block" />
                <span
                  className="bg-clip-text text-transparent"
                  style={{
                    backgroundImage: "linear-gradient(90deg, #93c5fd, #c4b5fd)",
                  }}
                >
                  {" "}
                  {firstName}!
                </span>
              </h2>
              <p className="mt-3 text-sm sm:text-base max-w-md leading-relaxed text-white/60">
                Your AI invoice workspace is ready. Here&apos;s a live summary
                of today&apos;s activity.
              </p>
            </div>

            <div className="flex-shrink-0 flex flex-col items-center gap-2">
              <div className="relative">
                <motion.div
                  className="absolute inset-0 rounded-2xl"
                  style={{
                    background: "linear-gradient(135deg, #93c5fd, #c084fc)",
                    padding: 2,
                  }}
                  animate={{ opacity: [0.6, 1, 0.6] }}
                  transition={{ duration: 2.5, repeat: Infinity }}
                />
                <div
                  className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl flex items-center justify-center m-0.5"
                  style={{
                    background: "rgba(30, 60, 140, 0.8)",
                    backdropFilter: "blur(10px)",
                  }}
                >
                  <UserCircle2 className="w-12 h-12 sm:w-14 sm:h-14 text-white/90" />
                </div>
                <span className="absolute -bottom-1.5 -right-1.5 w-5 h-5 rounded-full border-2 border-white bg-emerald-400" />
              </div>
              <p className="text-xs text-white/70 text-center max-w-[110px] leading-snug font-medium">
                {fullName || "User"}
              </p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* ── Analytics Cards ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading
          ? [1, 2, 3].map((i) => <SkeletonCard key={i} />)
          : statCards.map((stat, i) => (
              <motion.div
                key={stat.label}
                variants={itemVariants}
                custom={i}
                className={`group relative bg-card border border-border rounded-2xl p-5 shadow-sm hover:shadow-md transition-all duration-300 hover:-translate-y-0.5 border-l-4 ${stat.borderAccent}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className={`rounded-xl p-2.5 ${stat.iconBg}`}>
                    <stat.icon className={`w-5 h-5 ${stat.iconColor}`} />
                  </div>
                </div>
                <p className="text-4xl font-extrabold text-foreground tracking-tight leading-none">
                  {stat.value.toLocaleString()}
                </p>
                <p className="text-sm font-semibold text-foreground/80 mt-2">
                  {stat.label}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {stat.description}
                </p>
              </motion.div>
            ))}
      </div>

      {/* ── Error Banner ─────────────────────────────────────────────────── */}
      {error && !loading && (
        <div className="flex items-center justify-between bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
          <span>{error}</span>
          <button
            onClick={fetchDashboard}
            className="flex items-center gap-1.5 text-xs font-medium hover:underline"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      )}

      {/* ── Recent Invoices ──────────────────────────────────────────────── */}
      <motion.div
        variants={itemVariants}
        className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            <h3 className="font-semibold text-foreground">Recent Invoices</h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground bg-muted px-3 py-1 rounded-full font-medium">
              Last 5 entries
            </span>
            <button
              onClick={fetchDashboard}
              title="Refresh"
              className="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
              />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/40 border-b border-border">
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Invoice
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Client Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Buyer Party
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Seller Party
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Product Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Amount
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Date
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                [1, 2, 3, 4, 5].map((i) => (
                  <tr key={i} className="animate-pulse">
                    {[1, 2, 3, 4, 5, 6, 7, 8].map((j) => (
                      <td key={j} className="px-6 py-4">
                        <div className="h-4 bg-muted rounded w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : recentInvoices.length === 0 ? (
                <tr>
                  <td
                    colSpan={8}
                    className="px-6 py-10 text-center text-muted-foreground text-sm"
                  >
                    No invoices found
                  </td>
                </tr>
              ) : (
                recentInvoices.map((inv) => {
                  const styleKey = inv.status.toLowerCase();
                  const style =
                    statusStyles[styleKey] ?? statusStyles["pending"];
                  return (
                    <tr
                      key={inv.id}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-6 py-4 font-mono text-xs font-bold text-foreground">
                        {(() => {
                          const idVal = inv.invoice_number ?? inv.id;
                          if (idVal != null) {
                            const strVal = String(idVal);
                            if (!/^\d+$/.test(strVal) && isNaN(Number(strVal)))
                              return strVal;
                            const numStr = strVal.replace(/\D/g, "");
                            if (numStr) return `INV-${numStr.padStart(3, "0")}`;
                          }
                          return "—";
                        })()}
                      </td>
                      <td className="px-4 py-4 text-sm text-muted-foreground max-w-[180px] truncate">
                        {inv.client_name ?? "—"}
                      </td>
                      <td className="px-4 py-4 text-sm text-muted-foreground max-w-[180px] truncate">
                        {inv.buyer_party_name ?? "—"}
                      </td>
                      <td className="px-4 py-4 text-sm text-muted-foreground max-w-[180px] truncate">
                        {inv.seller_party_name ?? "—"}
                      </td>
                      <td className="px-4 py-4 text-sm text-muted-foreground max-w-[180px] truncate">
                        {inv.product_name ?? "—"}
                      </td>
                      <td className="px-4 py-4 text-sm font-semibold text-foreground">
                        {formatAmount(inv.total)}
                      </td>
                      <td className="px-4 py-4">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${style.bg} ${style.text}`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${style.dot}`}
                          />
                          {formatStatus(inv.status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs text-muted-foreground">
                        {formatDate(inv.invoice_date ?? null)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </motion.div>
    </motion.div>
  );
}
