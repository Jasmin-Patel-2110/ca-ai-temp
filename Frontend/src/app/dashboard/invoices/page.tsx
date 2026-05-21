"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Plus,
  MoreVertical,
  FileText,
  Edit,
  Trash2,
  Loader2,
  ServerCrash,
  Inbox,
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  Save,
  X,
  Pencil,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogTrigger,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { BulkUpload } from "@/components/upload/BulkUpload";
import { useToast } from "@/hooks/use-toast";
import {
  deleteInvoiceAction,
  bulkUpdateInvoicesAction,
  bulkVerifyInvoicesAction,
} from "@/app/actions/invoices";
import { useRedux } from "@/hooks/useRedux";
import {
  getCategoriesByIndustry,
  getSubCategories,
  getIndustries,
} from "@/constants/industryMapping";
import { motion, AnimatePresence } from "framer-motion";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ApiInvoice {
  id?: number | string;
  invoice_id?: string;
  invoice_number?: string | number;
  invoice_date?: string | null;
  client_name?: string;
  buyer_party_name?: string;
  seller_party_name?: string;
  transaction_type?: string;
  status?: string;
  industry?: string;
  category?: string;
  sub_category?: string;
  buyer_pan_number?: string;
  seller_pan_number?: string;
  buyer_gst_number?: string;
  seller_gst_number?: string;
  buyer_contact_number?: string;
  seller_contact_number?: string;
  buyer_location?: string;
  seller_location?: string;
  product_name?: string;
  quantity?: number | string;
  rate?: number | string;
  amount?: number | string;
  gst?: number | string;
  cgst?: number | string;
  sgst?: number | string;
  igst?: number | string;
  total_amount?: number | string;
  total?: number | string;
  payment_mode?: string;
  amount_paid?: number | string;
  balance_amount?: number | string;
  additional_detail?: Record<string, unknown> | null;
  [key: string]: unknown;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> =
  {
    pending_extraction: {
      bg: "bg-primary/10",
      text: "text-primary",
      dot: "bg-primary",
    },
    pending_verification: {
      bg: "bg-warning/10",
      text: "text-warning",
      dot: "bg-warning",
    },
    verified: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
    error: {
      bg: "bg-destructive/10",
      text: "text-destructive",
      dot: "bg-destructive",
    },
    completed: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
    pending: { bg: "bg-warning/10", text: "text-warning", dot: "bg-warning" },
    processing: {
      bg: "bg-primary/10",
      text: "text-primary",
      dot: "bg-primary",
    },
    verify: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
  };

function formatStatus(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("auth_token") ?? "";
}

function getInvoiceNumber(inv: ApiInvoice): string {
  const numValue = inv.invoice_number;
  if (numValue != null && numValue !== "") {
    return String(numValue);
  }
  return "—";
}

function formatAmount(total: number | string | null | undefined): string {
  if (total == null || total === "") return "—";
  const num = typeof total === "string" ? parseFloat(total) : total;
  if (isNaN(num)) return "—";
  return `₹${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ─── Editable columns for inline table ────────────────────────────────────────

const INLINE_EDITABLE_KEYS = [
  "invoice_number",
  "client_name",
  "buyer_party_name",
  "seller_party_name",
  "product_name",
  "transaction_type",
  "total_amount",
] as const;

type InlineEditKey = (typeof INLINE_EDITABLE_KEYS)[number];

// ─── All fields for the side-panel quick edit ─────────────────────────────────

const PANEL_FIELDS: {
  key: string;
  label: string;
  type?: "date" | "select" | "textarea";
  options?: string[];
}[] = [
  { key: "invoice_number", label: "Invoice Number" },
  { key: "invoice_date", label: "Invoice Date", type: "date" },
  { key: "client_name", label: "Client Name" },
  { key: "industry", label: "Industry", type: "select", options: getIndustries() },
  { key: "transaction_type", label: "Transaction Type", type: "select", options: ["Sales", "Purchase"] },
  { key: "category", label: "Category", type: "select" },
  { key: "sub_category", label: "Sub Category", type: "select" },
  { key: "status", label: "Status", type: "select", options: ["pending_extraction", "pending_verification", "verified", "error"] },
  { key: "product_name", label: "Product Name" },
  { key: "quantity", label: "Quantity" },
  { key: "rate", label: "Rate" },
  { key: "amount", label: "Amount" },
  { key: "gst", label: "GST" },
  { key: "cgst", label: "CGST" },
  { key: "sgst", label: "SGST" },
  { key: "igst", label: "IGST" },
  { key: "total", label: "Total Amount" },
  { key: "payment_mode", label: "Payment Mode" },
  { key: "amount_paid", label: "Amount Paid" },
  { key: "balance_amount", label: "Balance Amount" },
  { key: "buyer_party_name", label: "Buyer Party Name" },
  { key: "buyer_contact_number", label: "Buyer Contact" },
  { key: "buyer_gst_number", label: "Buyer GST" },
  { key: "buyer_pan_number", label: "Buyer PAN" },
  { key: "buyer_location", label: "Buyer Location" },
  { key: "seller_party_name", label: "Seller Party Name" },
  { key: "seller_contact_number", label: "Seller Contact" },
  { key: "seller_gst_number", label: "Seller GST" },
  { key: "seller_pan_number", label: "Seller PAN" },
  { key: "seller_location", label: "Seller Location" },
];

// ─── Debounce hook ────────────────────────────────────────────────────────────

function useDebounce<T>(value: T, delay = 500): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ─── Inline editable cell component ───────────────────────────────────────────

function EditableCell({
  value,
  field,
  onChange,
  isEdited,
  type = "text",
  options,
}: {
  value: string;
  field: string;
  onChange: (val: string) => void;
  isEdited: boolean;
  type?: "text" | "select";
  options?: string[];
}) {
  const [editing, setEditing] = useState(false);
  const [localVal, setLocalVal] = useState(value);
  const inputRef = useRef<HTMLInputElement | HTMLSelectElement>(null);

  useEffect(() => {
    setLocalVal(value);
  }, [value]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      if (inputRef.current instanceof HTMLInputElement) {
        inputRef.current.select();
      }
    }
  }, [editing]);

  const commit = () => {
    setEditing(false);
    if (localVal !== value) {
      onChange(localVal);
    }
  };

  const cancel = () => {
    setEditing(false);
    setLocalVal(value);
  };

  if (editing) {
    if (type === "select" && options) {
      return (
        <select
          ref={inputRef as React.RefObject<HTMLSelectElement>}
          value={localVal}
          onChange={(e) => {
            setLocalVal(e.target.value);
            onChange(e.target.value);
            setEditing(false);
          }}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
          className="w-full h-8 rounded-md border border-primary/50 bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all"
        >
          <option value="">Select…</option>
          {options.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      );
    }

    return (
      <input
        ref={inputRef as React.RefObject<HTMLInputElement>}
        type="text"
        value={localVal}
        onChange={(e) => setLocalVal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") cancel();
          if (e.key === "Tab") {
            // allow natural tab navigation
            commit();
          }
        }}
        className="w-full h-8 rounded-md border border-primary/50 bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all"
      />
    );
  }

  return (
    <div
      onClick={() => setEditing(true)}
      className={`group/cell cursor-pointer rounded-md px-2 py-1.5 min-h-[32px] flex items-center transition-all hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 ${
        isEdited
          ? "bg-primary/10 ring-1 ring-primary/40"
          : ""
      }`}
      title="Click to edit"
    >
      <span className={`text-sm truncate flex-1 ${isEdited ? "font-semibold text-primary" : "text-foreground"}`}>
        {field === "total_amount" ? formatAmount(value) : (value || "—")}
      </span>
      <Pencil className="w-3 h-3 text-muted-foreground/0 group-hover/cell:text-muted-foreground/60 transition-opacity ml-1 shrink-0" />
    </div>
  );
}

// ─── Skeleton row ─────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr className="border-b border-border animate-pulse">
      {Array.from({ length: 9 }).map((_, i) => (
        <td key={i} className="px-4 py-4">
          <div className="h-4 bg-muted rounded w-20" />
        </td>
      ))}
    </tr>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const ITEMS_PER_PAGE = 10;

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<ApiInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery.trim(), 500);

  const [currentPage, setCurrentPage] = useState(1);

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [invoiceToDelete, setInvoiceToDelete] = useState<
    string | number | null
  >(null);

  // ── Bulk selection ──────────────────────────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<string | number>>(new Set());

  // ── Inline edits tracking: { [invoiceId]: { [field]: newValue } } ───────────
  const [editedInvoices, setEditedInvoices] = useState<
    Record<string, Record<string, string>>
  >({});

  // ── Quick-edit side panel ───────────────────────────────────────────────────
  const [panelInvoice, setPanelInvoice] = useState<ApiInvoice | null>(null);
  const [panelFormData, setPanelFormData] = useState<Record<string, string>>({});
  const [panelOriginal, setPanelOriginal] = useState<Record<string, string>>({});
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelSaving, setPanelSaving] = useState(false);

  // ── Bulk action loading ─────────────────────────────────────────────────────
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkVerifying, setBulkVerifying] = useState(false);

  const router = useRouter();
  const { success, errorAlert } = useToast();
  const { selector } = useRedux();
  const user = selector((s) => s.auth.user);

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const invoiceId = (inv: ApiInvoice) => String(inv.id ?? "");

  const hasAnyEdits = Object.keys(editedInvoices).length > 0;

  const editedCount = Object.keys(editedInvoices).length;

  const getFieldValue = (inv: ApiInvoice, field: string): string => {
    const id = invoiceId(inv);
    if (editedInvoices[id]?.[field] !== undefined) {
      return editedInvoices[id][field];
    }
    const raw = (inv as Record<string, unknown>)[field];
    return raw != null ? String(raw) : "";
  };

  const setFieldValue = (inv: ApiInvoice, field: string, value: string) => {
    const id = invoiceId(inv);
    const original = (inv as Record<string, unknown>)[field];
    const originalStr = original != null ? String(original) : "";

    setEditedInvoices((prev) => {
      const existing = { ...prev };
      if (value === originalStr) {
        // Revert: remove this field from edits
        if (existing[id]) {
          const { [field]: _, ...rest } = existing[id];
          if (Object.keys(rest).length === 0) {
            delete existing[id];
          } else {
            existing[id] = rest;
          }
        }
      } else {
        existing[id] = { ...(existing[id] ?? {}), [field]: value };
      }
      return existing;
    });
  };

  const isFieldEdited = (inv: ApiInvoice, field: string): boolean => {
    const id = invoiceId(inv);
    return editedInvoices[id]?.[field] !== undefined;
  };

  const isRowEdited = (inv: ApiInvoice): boolean => {
    const id = invoiceId(inv);
    return !!editedInvoices[id] && Object.keys(editedInvoices[id]).length > 0;
  };

  // ── Selection helpers ───────────────────────────────────────────────────────

  const paginatedInvoices = invoices.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE,
  );

  const allPageSelected =
    paginatedInvoices.length > 0 &&
    paginatedInvoices.every((inv) => selectedIds.has(inv.id!));

  const someSelected = selectedIds.size > 0;

  const toggleSelect = (id: string | number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allPageSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        paginatedInvoices.forEach((inv) => next.delete(inv.id!));
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        paginatedInvoices.forEach((inv) => next.add(inv.id!));
        return next;
      });
    }
  };

  // ── API ─────────────────────────────────────────────────────────────────────

  const handleConfirmDelete = async () => {
    if (!invoiceToDelete) return;

    setLoading(true);
    try {
      const result = await deleteInvoiceAction(invoiceToDelete);
      if (result.success) {
        success({ message: "Invoice deleted successfully." });
        // Clear from selection & edits
        setSelectedIds((prev) => {
          const n = new Set(prev);
          n.delete(invoiceToDelete);
          return n;
        });
        setEditedInvoices((prev) => {
          const n = { ...prev };
          delete n[String(invoiceToDelete)];
          return n;
        });
        if (debouncedQuery) fetchSearch(debouncedQuery);
        else fetchAll();
      } else {
        errorAlert({ message: result.error || "Failed to delete invoice." });
        setLoading(false);
      }
    } catch {
      errorAlert({ message: "An unexpected error occurred." });
      setLoading(false);
    } finally {
      setInvoiceToDelete(null);
    }
  };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const userId = String(user?.sub ?? "6");
      const url = `${BASE_URL}/invoices/all?user_id=${encodeURIComponent(userId)}`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setInvoices(data.invoices ?? []);
      setEditedInvoices({});
      setSelectedIds(new Set());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load invoices.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  const fetchSearch = useCallback(async (q: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${BASE_URL}/invoices/search?q=${encodeURIComponent(q)}&top_k=20`,
        { headers: { Authorization: `Bearer ${getToken()}` } },
      );
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      const hits: ApiInvoice[] = (data.results ?? []).map(
        (r: Record<string, unknown>) => ({
          id: r.id,
          invoice_number: r.invoice_number,
          invoice_id: r.invoice_id ?? r.id ?? "—",
          client_name: r.client_name ?? r.clientName,
          buyer_party_name: r.buyer_party_name,
          seller_party_name: r.seller_party_name,
          product_name: r.product_name,
          transaction_type: r.transaction_type ?? r.type,
          status: r.status,
          industry: r.industry,
          category: r.category,
          sub_category: r.sub_category,
          buyer_pan_number: r.buyer_pan_number,
          seller_pan_number: r.seller_pan_number,
          buyer_gst_number: r.buyer_gst_number,
          seller_gst_number: r.seller_gst_number,
          buyer_contact_number: r.buyer_contact_number,
          seller_contact_number: r.seller_contact_number,
          total_amount: r.total_amount ?? r.totalAmount ?? r.total,
          total: r.total,
        }),
      );
      setInvoices(hits);
      setCurrentPage(1);
      setEditedInvoices({});
      setSelectedIds(new Set());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debouncedQuery) {
      fetchSearch(debouncedQuery);
    } else {
      fetchAll();
    }
  }, [debouncedQuery, fetchAll, fetchSearch]);

  // ── Bulk Save All ───────────────────────────────────────────────────────────

  const handleSaveAll = async () => {
    if (!hasAnyEdits) return;
    setBulkSaving(true);
    try {
      const updates = Object.entries(editedInvoices).map(([id, fields]) => ({
        id,
        fields: fields as Record<string, unknown>,
      }));
      const result = await bulkUpdateInvoicesAction(updates);
      if (result.success) {
        success({ message: `${updates.length} invoice(s) saved successfully!` });
        setEditedInvoices({});
        if (debouncedQuery) fetchSearch(debouncedQuery);
        else fetchAll();
      } else {
        const failedIds = result.results
          .filter((r) => !r.success)
          .map((r) => r.id);
        errorAlert({
          message: `${result.error}. Failed IDs: ${failedIds.join(", ")}`,
        });
        // Remove succeeded ones from edits
        const succeededIds = new Set(
          result.results.filter((r) => r.success).map((r) => String(r.id)),
        );
        setEditedInvoices((prev) => {
          const next = { ...prev };
          for (const id of succeededIds) delete next[id];
          return next;
        });
      }
    } catch {
      errorAlert({ message: "Failed to save changes." });
    } finally {
      setBulkSaving(false);
    }
  };

  // ── Bulk Verify Selected ────────────────────────────────────────────────────

  const handleBulkVerify = async () => {
    if (selectedIds.size === 0) return;
    setBulkVerifying(true);
    try {
      const ids = Array.from(selectedIds);
      const result = await bulkVerifyInvoicesAction(ids);
      if (result.success) {
        success({ message: `${ids.length} invoice(s) verified!` });
        setSelectedIds(new Set());
        if (debouncedQuery) fetchSearch(debouncedQuery);
        else fetchAll();
      } else {
        errorAlert({ message: result.error ?? "Some invoices failed to verify." });
      }
    } catch {
      errorAlert({ message: "Bulk verify failed." });
    } finally {
      setBulkVerifying(false);
    }
  };

  // ── Bulk Delete Selected ────────────────────────────────────────────────────

  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    setBulkDeleting(true);
    try {
      const ids = Array.from(selectedIds);
      const results = await Promise.allSettled(
        ids.map((id) => deleteInvoiceAction(id)),
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed === 0) {
        success({ message: `${ids.length} invoice(s) deleted!` });
      } else {
        errorAlert({ message: `${failed} invoice(s) failed to delete.` });
      }
      setSelectedIds(new Set());
      setBulkDeleteConfirm(false);
      if (debouncedQuery) fetchSearch(debouncedQuery);
      else fetchAll();
    } catch {
      errorAlert({ message: "Bulk delete failed." });
    } finally {
      setBulkDeleting(false);
    }
  };

  // ── Quick-Edit Panel ────────────────────────────────────────────────────────

  const openPanel = (inv: ApiInvoice) => {
    setPanelInvoice(inv);
    const initial: Record<string, string> = {};
    PANEL_FIELDS.forEach(({ key }) => {
      const id = invoiceId(inv);
      // Start with inline edits if any, otherwise original data
      if (editedInvoices[id]?.[key] !== undefined) {
        initial[key] = editedInvoices[id][key];
      } else {
        const raw = (inv as Record<string, unknown>)[key];
        if (key === "invoice_date") {
          const rawDate = inv.invoice_date || (inv as any).invoice_datetime || "";
          initial[key] = rawDate ? String(rawDate).slice(0, 10) : "";
        } else {
          initial[key] = raw != null ? String(raw) : "";
        }
      }
    });
    setPanelFormData(initial);
    // Store original for diff
    const orig: Record<string, string> = {};
    PANEL_FIELDS.forEach(({ key }) => {
      const raw = (inv as Record<string, unknown>)[key];
      if (key === "invoice_date") {
        const rawDate = inv.invoice_date || (inv as any).invoice_datetime || "";
        orig[key] = rawDate ? String(rawDate).slice(0, 10) : "";
      } else {
        orig[key] = raw != null ? String(raw) : "";
      }
    });
    setPanelOriginal(orig);
    setPanelOpen(true);
  };

  const handlePanelSave = async () => {
    if (!panelInvoice) return;
    const id = invoiceId(panelInvoice);
    // Diff panel form vs original
    const changes: Record<string, string> = {};
    for (const key of Object.keys(panelFormData)) {
      if (panelFormData[key] !== panelOriginal[key]) {
        changes[key] = panelFormData[key];
      }
    }
    if (Object.keys(changes).length === 0) {
      setPanelOpen(false);
      return;
    }
    setPanelSaving(true);
    try {
      const result = await bulkUpdateInvoicesAction([{ id, fields: changes }]);
      if (result.success) {
        success({ message: "Invoice updated successfully!" });
        setPanelOpen(false);
        // Remove this invoice from staged edits if it was there
        setEditedInvoices((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        if (debouncedQuery) fetchSearch(debouncedQuery);
        else fetchAll();
      } else {
        errorAlert({ message: result.error || "Failed to update invoice." });
      }
    } catch {
      errorAlert({ message: "An unexpected error occurred." });
    } finally {
      setPanelSaving(false);
    }
  };

  // ─── Render helpers ─────────────────────────────────────────────────────────

  const renderBody = () => {
    if (loading) {
      return Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />);
    }

    if (error) {
      return (
        <tr>
          <td colSpan={9} className="px-6 py-20 text-center">
            <div className="flex flex-col items-center gap-3 text-destructive">
              <ServerCrash className="w-10 h-10 opacity-60" />
              <p className="font-medium">{error}</p>
              <Button variant="outline" size="sm" onClick={fetchAll}>
                Retry
              </Button>
            </div>
          </td>
        </tr>
      );
    }

    if (invoices.length === 0) {
      return (
        <tr>
          <td colSpan={9} className="px-6 py-20 text-center">
            <div className="flex flex-col items-center gap-3 text-muted-foreground">
              <Inbox className="w-10 h-10 opacity-40" />
              <p className="font-medium">
                {debouncedQuery
                  ? `No results for "${debouncedQuery}"`
                  : "No invoices found."}
              </p>
            </div>
          </td>
        </tr>
      );
    }

    return paginatedInvoices.map((inv, index) => {
      const id = inv.id!;
      const status = String(inv.status ?? "Pending");
      const statusKey = status.trim().toLowerCase();
      const style = STATUS_STYLES[statusKey] ?? STATUS_STYLES["pending"];
      const isSelected = selectedIds.has(id);
      const rowEdited = isRowEdited(inv);

      return (
        <tr
          key={id ?? index}
          className={`group transition-colors border-b border-border ${
            isSelected
              ? "bg-primary/5"
              : rowEdited
                ? "bg-blue-50/50 dark:bg-blue-950/20"
                : "hover:bg-muted/30"
          }`}
        >
          {/* Checkbox */}
          <td className="px-3 py-3 w-10">
            <Checkbox
              checked={isSelected}
              onCheckedChange={() => toggleSelect(id)}
              aria-label={`Select invoice ${getInvoiceNumber(inv)}`}
            />
          </td>

          {/* Row modified indicator */}
          <td className="px-0 py-3 w-2">
            {rowEdited && (
              <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" title="Modified" />
            )}
          </td>

          {/* Invoice Number */}
          <td className="px-2 py-2 min-w-[130px]">
            <button
              type="button"
              onClick={() => router.push(`/dashboard/invoices/${inv.id}`)}
              className="text-primary cursor-pointer font-medium hover:underline px-2 text-sm text-left truncate w-full transition-colors"
              title="View Invoice Details"
            >
              {getFieldValue(inv, "invoice_number") || "—"}
            </button>
          </td>

          {/* Client Name */}
          <td className="px-2 py-2 min-w-[150px]">
            <EditableCell
              value={getFieldValue(inv, "client_name")}
              field="client_name"
              onChange={(val) => setFieldValue(inv, "client_name", val)}
              isEdited={isFieldEdited(inv, "client_name")}
            />
          </td>

          {/* Buyer Party */}
          <td className="px-2 py-2 min-w-[150px]">
            <EditableCell
              value={getFieldValue(inv, "buyer_party_name")}
              field="buyer_party_name"
              onChange={(val) => setFieldValue(inv, "buyer_party_name", val)}
              isEdited={isFieldEdited(inv, "buyer_party_name")}
            />
          </td>

          {/* Seller Party */}
          <td className="px-2 py-2 min-w-[150px]">
            <EditableCell
              value={getFieldValue(inv, "seller_party_name")}
              field="seller_party_name"
              onChange={(val) => setFieldValue(inv, "seller_party_name", val)}
              isEdited={isFieldEdited(inv, "seller_party_name")}
            />
          </td>

          {/* Product Name */}
          <td className="px-2 py-2 min-w-[150px]">
            <EditableCell
              value={getFieldValue(inv, "product_name")}
              field="product_name"
              onChange={(val) => setFieldValue(inv, "product_name", val)}
              isEdited={isFieldEdited(inv, "product_name")}
            />
          </td>

          {/* Transaction Type */}
          <td className="px-2 py-2 min-w-[120px]">
            <EditableCell
              value={getFieldValue(inv, "transaction_type")}
              field="transaction_type"
              onChange={(val) => setFieldValue(inv, "transaction_type", val)}
              isEdited={isFieldEdited(inv, "transaction_type")}
              type="select"
              options={["Sales", "Purchase"]}
            />
          </td>

          {/* Status */}
          <td className="px-3 py-3 whitespace-nowrap">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${style.bg} ${style.text}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
              {formatStatus(status)}
            </span>
          </td>

          {/* Amount */}
          <td className="px-2 py-2 min-w-[120px]">
            <EditableCell
              value={getFieldValue(inv, "total_amount") || getFieldValue(inv, "total")}
              field="total_amount"
              onChange={(val) => setFieldValue(inv, "total_amount", val)}
              isEdited={isFieldEdited(inv, "total_amount")}
            />
          </td>

          {/* Actions */}
          <td 
            className={`px-3 py-3 text-right sticky right-0 z-10 border-l border-border ${
              isSelected || rowEdited ? "bg-card" : "bg-card group-hover:bg-muted"
            }`}
          >
            <div className="flex items-center justify-end gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="rounded-full h-8 w-8 text-muted-foreground hover:text-primary"
                onClick={() => openPanel(inv)}
                title="Quick Edit (all fields)"
              >
                <Edit className="w-4 h-4" />
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="rounded-full h-8 w-8">
                    <MoreVertical className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-44">
                  <DropdownMenuItem
                    className="gap-2 cursor-pointer"
                    onClick={() => router.push(`/dashboard/invoices/${inv.id}`)}
                  >
                    <FileText className="w-4 h-4" /> Full Detail View
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2 cursor-pointer"
                    onClick={() => openPanel(inv)}
                  >
                    <Edit className="w-4 h-4" /> Quick Edit Panel
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2 text-destructive focus:text-destructive cursor-pointer"
                    onClick={() => setInvoiceToDelete(inv.id!)}
                  >
                    <Trash2 className="w-4 h-4" /> Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </td>
        </tr>
      );
    });
  };

  // ─── JSX ────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4 animate-in fade-in duration-500">
      {/* Page heading */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">Invoices</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Edit directly in the table, select invoices for bulk actions, or open the quick-edit panel for all fields.
        </p>
      </div>

      {/* ── Bulk Actions Toolbar ──────────────────────────────────────────── */}
      <AnimatePresence>
        {someSelected && (
          <motion.div
            initial={{ opacity: 0, y: -10, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -10, height: 0 }}
            className="overflow-hidden"
          >
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-primary/5 border border-primary/20 shadow-sm">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                  <CheckCircle className="w-4 h-4 text-primary" />
                </div>
                <span className="text-sm font-semibold text-foreground">
                  {selectedIds.size} selected
                </span>
              </div>
              <div className="h-5 w-px bg-border" />
              <Button
                size="sm"
                className="gap-2 bg-success hover:bg-success/90 text-success-foreground shadow-sm"
                onClick={handleBulkVerify}
                disabled={bulkVerifying}
              >
                {bulkVerifying ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <ShieldCheck className="w-3.5 h-3.5" />
                )}
                Verify Selected
              </Button>
              <Button
                variant="destructive"
                size="sm"
                className="gap-2 shadow-sm"
                onClick={() => setBulkDeleteConfirm(true)}
                disabled={bulkDeleting}
              >
                {bulkDeleting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
                Delete Selected
              </Button>
              <div className="flex-1" />
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground"
                onClick={() => setSelectedIds(new Set())}
              >
                <X className="w-3.5 h-3.5 mr-1" /> Clear
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Search & Actions */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          {loading && searchQuery ? (
            <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground animate-spin" />
          ) : (
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          )}
          <Input
            placeholder="Search invoices by Invoice Number, Buyer/Seller Name…"
            className="pl-10 h-10"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="shadow-sm gap-2 whitespace-nowrap"
            onClick={() => {
              if (debouncedQuery) {
                fetchSearch(debouncedQuery);
              } else {
                fetchAll();
              }
            }}
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
          <Dialog open={isUploadModalOpen} onOpenChange={setIsUploadModalOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2 whitespace-nowrap shadow-sm">
                <Plus className="w-4 h-4" /> Add Invoice &amp; Extract
              </Button>
            </DialogTrigger>
            <DialogContent className="w-[95vw] max-w-7xl p-0 overflow-hidden bg-background max-h-[90vh] flex flex-col">
              <DialogTitle className="sr-only">
                Bulk Upload Invoices
              </DialogTitle>
              <div className="p-4 sm:p-6 md:p-8 flex flex-col flex-1 min-h-0 overflow-y-auto">
                <BulkUpload
                  onUploadSuccess={() => {
                    setIsUploadModalOpen(false);
                    fetchAll();
                  }}
                />
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Result count when searching */}
      {debouncedQuery && !loading && !error && (
        <p className="text-xs text-muted-foreground">
          {invoices.length} result{invoices.length !== 1 ? "s" : ""} for &ldquo;
          {debouncedQuery}&rdquo;
        </p>
      )}

      {/* ── Editable Invoice Table ──────────────────────────────────────── */}
      <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="px-3 py-3 w-10">
                  <Checkbox
                    checked={allPageSelected && paginatedInvoices.length > 0}
                    onCheckedChange={toggleSelectAll}
                    aria-label="Select all"
                  />
                </th>
                <th className="px-0 py-3 w-2" />
                <th className="px-2 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Invoice #
                </th>
                <th className="px-2 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Client Name
                </th>
                <th className="px-2 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Buyer Party
                </th>
                <th className="px-2 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Seller Party
                </th>
                <th className="px-2 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Product Name
                </th>
                <th className="px-2 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Type
                </th>
                <th className="px-3 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Status
                </th>
                <th className="px-2 py-3 font-semibold text-muted-foreground whitespace-nowrap text-xs uppercase tracking-wider">
                  Amount
                </th>
                <th className="px-3 py-3 font-semibold text-muted-foreground text-right whitespace-nowrap text-xs uppercase tracking-wider sticky right-0 z-20 bg-muted/95 backdrop-blur border-l border-border">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>{renderBody()}</tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {!loading && !error && invoices.length > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-muted/20">
            <p className="text-sm text-muted-foreground">
              Showing{" "}
              <span className="font-medium text-foreground">
                {(currentPage - 1) * ITEMS_PER_PAGE + 1}
              </span>{" "}
              to{" "}
              <span className="font-medium text-foreground">
                {Math.min(currentPage * ITEMS_PER_PAGE, invoices.length)}
              </span>{" "}
              of{" "}
              <span className="font-medium text-foreground">
                {invoices.length}
              </span>{" "}
              invoices
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="gap-1 px-3 shadow-none"
              >
                <ChevronLeft className="w-4 h-4" /> Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setCurrentPage((p) =>
                    Math.min(
                      Math.ceil(invoices.length / ITEMS_PER_PAGE),
                      p + 1,
                    ),
                  )
                }
                disabled={
                  currentPage >= Math.ceil(invoices.length / ITEMS_PER_PAGE)
                }
                className="gap-1 px-3 shadow-none"
              >
                Next <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* ── Floating Save All FAB ──────────────────────────────────────── */}
      <AnimatePresence>
        {hasAnyEdits && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className="fixed bottom-6 right-6 z-50"
          >
            <div className="flex items-center gap-3 px-5 py-3 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-2xl shadow-blue-500/25 border border-white/10">
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Save className="w-5 h-5" />
                  <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-white text-blue-600 text-[10px] font-bold flex items-center justify-center">
                    {editedCount}
                  </span>
                </div>
                <span className="text-sm font-medium">
                  {editedCount} unsaved change{editedCount !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-white/80 hover:text-white hover:bg-white/10 h-8"
                  onClick={() => setEditedInvoices({})}
                >
                  Discard
                </Button>
                <Button
                  size="sm"
                  className="bg-white text-blue-600 hover:bg-blue-50 font-semibold shadow-sm h-8 gap-1.5"
                  onClick={handleSaveAll}
                  disabled={bulkSaving}
                >
                  {bulkSaving ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <CheckCircle className="w-3.5 h-3.5" />
                  )}
                  Save All
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Quick-Edit Side Panel ──────────────────────────────────────── */}
      <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-lg overflow-y-auto p-0"
        >
          <SheetHeader className="px-6 pt-6 pb-4 border-b border-border sticky top-0 bg-background z-10">
            <SheetTitle className="flex items-center gap-2 text-lg">
              <Edit className="w-5 h-5 text-primary" />
              Quick Edit
              {panelInvoice && (
                <Badge variant="outline" className="ml-1 text-xs font-mono">
                  {getInvoiceNumber(panelInvoice)}
                </Badge>
              )}
            </SheetTitle>
            <SheetDescription>
              Edit all fields for this invoice. Changes are saved immediately.
            </SheetDescription>
          </SheetHeader>

          <div className="px-6 py-4 space-y-3">
            {PANEL_FIELDS.map(({ key, label, type, options }) => {
              const current = (panelFormData[key] || "").trim();
              const original = (panelOriginal[key] || "").trim();
              const changed = current !== original;

              let currentOptions = options;
              if (key === "category") {
                currentOptions = getCategoriesByIndustry(panelFormData.industry || "");
              } else if (key === "sub_category") {
                currentOptions = getSubCategories(
                  panelFormData.industry || "",
                  panelFormData.category || "",
                );
              }

              return (
                <div
                  key={key}
                  className={`space-y-1.5 p-3 rounded-lg border transition-colors ${
                    changed
                      ? "border-blue-300 dark:border-blue-700 bg-blue-50/50 dark:bg-blue-950/20"
                      : "border-transparent hover:border-border"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {label}
                    </Label>
                    {changed && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 border border-blue-200 dark:border-blue-700 uppercase tracking-wider">
                        Edited
                      </span>
                    )}
                  </div>
                  {type === "select" ? (
                    <select
                      value={panelFormData[key] ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setPanelFormData((prev) => {
                          const next = { ...prev, [key]: val };
                          if (key === "industry") {
                            next.category = "";
                            next.sub_category = "";
                          } else if (key === "category") {
                            next.sub_category = "";
                          }
                          return next;
                        });
                      }}
                      className={`w-full h-9 rounded-md border px-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-colors ${
                        changed
                          ? "bg-transparent border-blue-400 font-medium"
                          : "bg-background border-input"
                      }`}
                    >
                      <option value="">Select…</option>
                      {currentOptions?.map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Input
                      type={type === "date" ? "date" : "text"}
                      value={panelFormData[key] ?? ""}
                      onChange={(e) =>
                        setPanelFormData((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                      className={`h-9 transition-colors ${
                        changed
                          ? "bg-transparent border-blue-400 font-medium"
                          : "bg-background"
                      }`}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* Panel footer */}
          <div className="sticky bottom-0 px-6 py-4 border-t border-border bg-background flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => setPanelOpen(false)}
            >
              Cancel
            </Button>
            <Button
              className="flex-1 gap-2 bg-blue-600 hover:bg-blue-700 text-white"
              onClick={handlePanelSave}
              disabled={panelSaving}
            >
              {panelSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {panelSaving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      {/* ── Delete Confirmation ─────────────────────────────────────────── */}
      <AlertDialog
        open={!!invoiceToDelete}
        onOpenChange={(open) => !open && setInvoiceToDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the
              invoice and remove its data from our servers.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleConfirmDelete}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ── Bulk Delete Confirmation ────────────────────────────────────── */}
      <AlertDialog
        open={bulkDeleteConfirm}
        onOpenChange={(open) => !open && setBulkDeleteConfirm(false)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-destructive" />
              Delete {selectedIds.size} invoice(s)?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete {selectedIds.size} selected invoice(s).
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90 gap-2"
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
            >
              {bulkDeleting && <Loader2 className="w-4 h-4 animate-spin" />}
              Delete All
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
