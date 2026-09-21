import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Files, FileText,
  CheckCircle, Loader2, AlertCircle,
  Trash2, Play, ShieldCheck,
  Eye, Save, X, ChevronDown, ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import apiService from "@/lib/apiService";
import { useRedux } from "@/hooks/useRedux";
import { bulkUploadAction } from "@/app/actions/upload";
import {
  getInvoiceByIdAction,
  bulkUpdateInvoicesAction,
  bulkVerifyInvoicesAction,
} from "@/app/actions/invoices";
import {
  getCategoriesByIndustry,
  getSubCategories,
  getIndustries,
} from "@/constants/industryMapping";
import { motion } from "framer-motion";

// ─── Types ────────────────────────────────────────────────────────────────────

interface QueuedFile {
  id: string;
  file: File;
  status: "queued" | "uploading" | "processing" | "completed" | "error";
  progress: number;
}

interface InvoiceDetail {
  id: number;
  invoice_number?: string;
  buyer_party_name?: string;
  seller_party_name?: string;
  client_name?: string;
  industry?: string;
  transaction_type?: string;
  category?: string;
  sub_category?: string;
  status?: string;
  invoice_date?: string | null;
  invoice_datetime?: string | null;
  buyer_pan_number?: string;
  seller_pan_number?: string;
  buyer_gst_number?: string;
  seller_gst_number?: string;
  buyer_contact_number?: string | null;
  seller_contact_number?: string | null;
  buyer_location?: string;
  seller_location?: string;
  product_name?: string;
  gst?: number | null;
  cgst?: number | null;
  sgst?: number | null;
  igst?: number | null;
  total?: number | null;
  quantity?: number | null;
  rate?: number | null;
  amount?: number | null;
  amount_paid?: number | null;
  balance_amount?: number | null;
  payment_mode?: string;
  additional_detail?: Record<string, unknown> | null;
  document?: {
    id?: number;
    doc_id?: string;
    doc_name?: string;
    s3_key?: string;
    s3_url?: string;
    preview_url?: string;
    created_at?: string;
  } | null;
  [key: string]: unknown;
}

interface BulkUploadProps {
  onUploadSuccess?: () => void;
}

// ─── Editable fields (matching the detail page) ──────────────────────────────

const FIELDS: {
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  pending_extraction: { bg: "bg-primary/10", text: "text-primary", dot: "bg-primary" },
  pending_verification: { bg: "bg-warning/10", text: "text-warning", dot: "bg-warning" },
  verified: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
  error: { bg: "bg-destructive/10", text: "text-destructive", dot: "bg-destructive" },
  completed: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
  pending: { bg: "bg-warning/10", text: "text-warning", dot: "bg-warning" },
};

function formatStatus(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("auth_token") ?? "";
}

// ─── Document Preview (same as detail page) ──────────────────────────────────

function DocumentPreview({ url, fileName }: { url?: string; fileName?: string }) {
  const name = fileName ?? "Document";
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const isPdf = ext === "pdf";
  const isImage = ["jpg", "jpeg", "png", "webp"].includes(ext);

  return (
    <div className="bg-card rounded-xl border border-border flex flex-col overflow-hidden h-full shadow-sm">
      <div className="px-4 py-2.5 border-b border-border flex items-center gap-2 shrink-0 bg-muted/30">
        <FileText className="w-3.5 h-3.5 text-primary" />
        <span className="text-xs font-medium text-foreground truncate">{name}</span>
        {url && (
          <a href={url} target="_blank" rel="noreferrer"
            className="ml-auto text-[10px] text-primary hover:underline whitespace-nowrap shrink-0">
            Open ↗
          </a>
        )}
      </div>
      <div className="flex-1 overflow-auto bg-muted/20 flex items-center justify-center p-3 min-h-[300px]">
        {!url ? (
          <div className="text-center text-muted-foreground">
            <FileText className="w-12 h-12 mx-auto mb-2 opacity-30" />
            <p className="text-xs">No document preview available</p>
          </div>
        ) : isImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt="Invoice" className="max-w-full max-h-[400px] rounded-lg object-contain" />
        ) : isPdf ? (
          <iframe
            src={`https://docs.google.com/viewer?url=${encodeURIComponent(url)}&embedded=true`}
            title="PDF Preview"
            className="w-full h-full min-h-[400px] rounded-lg border-0"
          />
        ) : (
          <div className="text-center text-muted-foreground space-y-2">
            <FileText className="w-12 h-12 mx-auto opacity-30" />
            <p className="text-xs">Preview not supported</p>
            <a href={url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary text-xs hover:underline font-medium">
              Open document ↗
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Document Group Card (split view with multiple invoices) ─────────────────

function DocumentGroupCard({
  docName,
  invoices,
  index,
  allFormData,
  allInitialData,
  onFieldChange,
}: {
  docName: string;
  invoices: InvoiceDetail[];
  index: number;
  allFormData: Record<string, Record<string, string>>;
  allInitialData: Record<string, Record<string, string>>;
  onFieldChange: (invoiceId: string, key: string, value: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);

  const firstInvoice = invoices[0];
  const url = firstInvoice?.document?.preview_url ?? firstInvoice?.document?.s3_url;

  // Aggregate changed fields count across all invoices
  const changedCount = invoices.reduce((acc, inv) => {
    const formData = allFormData[String(inv.id)] ?? {};
    const initialData = allInitialData[String(inv.id)] ?? {};
    return acc + Object.keys(formData).filter((k) => formData[k] !== initialData[k]).length;
  }, 0);

  // Status aggregation
  let groupStatus = "verified";
  if (invoices.some((inv) => inv.status?.toLowerCase() === "error")) groupStatus = "error";
  else if (invoices.some((inv) => inv.status?.toLowerCase() === "pending_extraction")) groupStatus = "pending_extraction";
  else if (invoices.some((inv) => inv.status?.toLowerCase() === "pending_verification")) groupStatus = "pending_verification";

  const style = STATUS_STYLES[groupStatus] ?? STATUS_STYLES["pending"];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.4 }}
      className="bg-card rounded-xl border border-border shadow-sm overflow-hidden"
    >
      {/* Card Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
            <FileText className="w-4 h-4 text-primary" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 flex-1 min-w-0">
              <span className="text-sm font-bold text-foreground">{docName}</span>
              <Badge variant="outline" className="text-[10px] bg-muted text-muted-foreground border-border">
                {invoices.length} {invoices.length === 1 ? "entry" : "entries"}
              </Badge>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${style.bg} ${style.text}`}>
                <span className={`w-1 h-1 rounded-full ${style.dot}`} />
                {formatStatus(groupStatus)}
              </span>
              {changedCount > 0 && (
                <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/20">
                  {changedCount} edit{changedCount !== 1 ? "s" : ""}
                </Badge>
              )}
            </div>
            {invoices.length === 1 ? (
              <p className="text-xs text-muted-foreground mt-0.5">
                Invoice {invoices[0].invoice_number ? `INV-${String(invoices[0].invoice_number).replace(/^INV-/i, "")}` : `#${invoices[0].id}`}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground mt-0.5">
                Multiple invoices extracted from this file
              </p>
            )}
          </div>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full shrink-0">
          {collapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </Button>
      </div>

      {/* Card Body — Split View */}
      {!collapsed && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 divide-y lg:divide-y-0 lg:divide-x divide-border">
          {/* Left — Document Preview */}
          <div className="min-h-[300px]">
            <DocumentPreview url={url} fileName={docName} />
          </div>

          {/* Right — Extracted Fields */}
          <div className="flex flex-col max-h-[500px] overflow-y-auto bg-muted/5">
            {invoices.map((inv, invIndex) => {
              const formData = allFormData[String(inv.id)] ?? {};
              const initialData = allInitialData[String(inv.id)] ?? {};
              const invoiceLabel = inv.invoice_number
                ? `INV-${String(inv.invoice_number).replace(/^INV-/i, "")}`
                : `#${inv.id}`;

              return (
                <div key={inv.id} className="flex flex-col border-b border-border last:border-0 relative">
                  <div className="px-4 py-2.5 bg-muted/30 shrink-0 sticky top-0 z-10 border-b border-border flex items-center justify-between backdrop-blur-md">
                    <span className="text-xs font-bold text-foreground flex items-center gap-2">
                       <span className="w-5 h-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-[10px] tabular-nums shadow-sm">{invIndex + 1}</span>
                       <span className="font-mono">{invoiceLabel}</span>
                    </span>
                    <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">Extracted Fields</span>
                  </div>
                  <div className="p-3 space-y-2 bg-card">
                    {FIELDS.map(({ key, label, type, options }) => {
                      const current = (formData[key] || "").trim();
                      const original = (initialData[key] || "").trim();
                      const changed = current !== original;

                      let currentOptions = options;
                      if (key === "category") {
                        currentOptions = getCategoriesByIndustry(formData.industry || "");
                      } else if (key === "sub_category") {
                        currentOptions = getSubCategories(formData.industry || "", formData.category || "");
                      }

                      return (
                        <div
                          key={key}
                          className={`space-y-1 p-2 rounded-lg border transition-colors ${
                            changed
                              ? "border-blue-300 dark:border-blue-700 bg-blue-50/50 dark:bg-blue-950/20"
                              : "border-transparent"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                              {label}
                            </Label>
                            {changed && (
                              <span className="text-[9px] px-1 py-0.5 rounded font-bold bg-primary/10 text-primary border border-primary/20 uppercase tracking-wider">
                                Edited
                              </span>
                            )}
                          </div>
                          {type === "select" ? (
                            <select
                              value={formData[key] ?? ""}
                              onChange={(e) => {
                                const val = e.target.value;
                                onFieldChange(String(inv.id), key, val);
                                if (key === "industry") {
                                  onFieldChange(String(inv.id), "category", "");
                                  onFieldChange(String(inv.id), "sub_category", "");
                                } else if (key === "category") {
                                  onFieldChange(String(inv.id), "sub_category", "");
                                }
                              }}
                              className={`w-full h-8 rounded-md border px-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary transition-colors ${
                                changed ? "bg-primary/5 border-primary/40 font-medium" : "bg-background border-input"
                              }`}
                            >
                              <option value="">Select…</option>
                              {currentOptions?.map((o) => (
                                <option key={o} value={o}>{o}</option>
                              ))}
                            </select>
                          ) : (
                            <Input
                              type={type === "date" ? "date" : "text"}
                              value={formData[key] ?? ""}
                              onChange={(e) => onFieldChange(String(inv.id), key, e.target.value)}
                              className={`h-8 text-xs transition-colors ${
                                changed ? "bg-primary/5 border-primary/40 font-medium" : "bg-background"
                              }`}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export function BulkUpload({ onUploadSuccess }: BulkUploadProps) {
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [clientName, setClientName] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const { success, errorAlert } = useToast();
  const { selector } = useRedux();
  const user = selector((s) => s.auth.user);
  const userId = user?.sub ?? "6";

  // ── Preview state ─────────────────────────────────────────────────────────
  const [showPreview, setShowPreview] = useState(false);
  const [previewInvoices, setPreviewInvoices] = useState<InvoiceDetail[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  // Per-invoice form data: { [invoiceId]: { [field]: value } }
  const [allFormData, setAllFormData] = useState<Record<string, Record<string, string>>>({});
  const [allInitialData, setAllInitialData] = useState<Record<string, Record<string, string>>>({});
  const [verifyingAll, setVerifyingAll] = useState(false);
  // Track IDs that existed BEFORE upload so we can identify new ones
  const [preUploadIds, setPreUploadIds] = useState<Set<number>>(new Set());
  const [savingAll, setSavingAll] = useState(false);

  // ── File handlers ─────────────────────────────────────────────────────────

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const newFiles = Array.from(e.target.files).map(f => ({
      id: Math.random().toString(36).substr(2, 9),
      file: f,
      status: "queued" as const,
      progress: 0,
    }));
    setQueue(prev => [...prev, ...newFiles]);
  };

  const removeFile = (id: string) => {
    setQueue(prev => prev.filter(f => f.id !== id));
  };

  // ── Fetch current invoice IDs (call BEFORE upload) ─────────────────────────

  const snapshotExistingInvoices = useCallback(async (): Promise<Set<number>> => {
    try {
      const token = getToken();
      const data = await apiService.get<any>(`/invoices/all?user_id=${userId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const ids = (data.invoices ?? []).map((inv: any) => Number(inv.id));
      return new Set(ids);
    } catch {
      return new Set();
    }
  }, [userId]);

  // ── Fetch invoice details for preview (only NEW invoices) ──────────────────

  const fetchInvoiceDetails = useCallback(async (existingIds: Set<number>) => {
    setPreviewLoading(true);
    try {
      const token = getToken();
      // Fetch all invoices after upload
      const data = await apiService.get<any>(`/invoices/all?user_id=${userId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const allInvoices = data.invoices ?? [];

      // Find only NEW invoices (IDs that didn't exist before upload)
      const newInvoices = allInvoices.filter(
        (inv: any) => !existingIds.has(Number(inv.id))
      );
      // Sort newest first
      newInvoices.sort((a: any, b: any) => (Number(b.id) || 0) - (Number(a.id) || 0));

      // If no new invoices detected (edge case), fall back to latest 5
      const toFetch = newInvoices.length > 0 ? newInvoices : allInvoices.sort((a: any, b: any) => (Number(b.id) || 0) - (Number(a.id) || 0)).slice(0, 5);
      const idsToFetch = toFetch.map((inv: any) => inv.id);

      // Fetch full details for each invoice (including document info)
      const detailResults = await Promise.allSettled(
        idsToFetch.map((id: number) => getInvoiceByIdAction(id))
      );

      const invoices: InvoiceDetail[] = [];
      const formDataMap: Record<string, Record<string, string>> = {};
      const initialDataMap: Record<string, Record<string, string>> = {};

      for (const result of detailResults) {
        if (result.status === "fulfilled" && result.value.success && result.value.data) {
          const inv: InvoiceDetail = result.value.data?.invoice ?? result.value.data;
          invoices.push(inv);

          // Build form data for this invoice
          const id = String(inv.id);
          const form: Record<string, string> = {};
          FIELDS.forEach(({ key }) => {
            if (key === "invoice_date") {
              const rawDate = inv.invoice_date || inv.invoice_datetime || "";
              form[key] = rawDate ? String(rawDate).slice(0, 10) : "";
            } else {
              const raw = (inv as Record<string, unknown>)[key];
              form[key] = raw != null ? String(raw) : "";
            }
          });
          formDataMap[id] = { ...form };
          initialDataMap[id] = { ...form };
        }
      }

      setPreviewInvoices(invoices);
      setAllFormData(formDataMap);
      setAllInitialData(initialDataMap);
    } catch {
      // Silent fail
    } finally {
      setPreviewLoading(false);
    }
  }, [userId]);

  // ── Upload processing ─────────────────────────────────────────────────────

  const startProcessing = async () => {
    const pendingFiles = queue.filter(f => f.status !== "completed");
    if (pendingFiles.length === 0) return;

    if (!clientName.trim()) {
      errorAlert({ message: "Please enter the Client Name before uploading." });
      return;
    }

    setIsProcessing(true);

    // Snapshot existing IDs before upload so we can find new ones after
    const existingIds = await snapshotExistingInvoices();
    setPreUploadIds(existingIds);

    setQueue(prev => prev.map(f => pendingFiles.find(p => p.id === f.id)
      ? { ...f, status: "processing", progress: 50 }
      : f
    ));

    const formData = new FormData();
    formData.append("client_name", clientName.trim());
    pendingFiles.forEach(item => {
      formData.append("files", item.file);
    });

    try {
      const result = await bulkUploadAction(formData);

      if (result.success) {
        const successes = result.successes || [];
        const errors = result.errors || [];

        setQueue(prev => prev.map(f => {
          if (f.status === "completed") return f;
          if (successes.includes(f.file.name)) {
            return { ...f, status: "completed", progress: 100 };
          }
          if (errors.includes(f.file.name)) {
            return { ...f, status: "error", progress: 0 };
          }
          return f;
        }));

        if (successes.length > 0) {
          success({
            message: `Successfully processed ${successes.length} invoice(s)!`,
          });
          // Transition to preview mode — fetch all NEW invoices (not limited by file count)
          setShowPreview(true);
          fetchInvoiceDetails(existingIds);
        } else if (errors.length > 0) {
          errorAlert({ message: "None of the invoices could be processed." });
        }
      } else {
        setQueue(prev => prev.map(f => pendingFiles.find(p => p.id === f.id)
          ? { ...f, status: "error", progress: 0 }
          : f
        ));
        errorAlert({ message: result.error || "Bulk processing failed." });
      }
    } catch {
      setQueue(prev => prev.map(f => queue.find(p => p.id === f.id)
        ? { ...f, status: "error", progress: 0 }
        : f
      ));
      errorAlert({ message: "An unexpected error occurred during upload." });
    } finally {
      setIsProcessing(false);
    }
  };

  // ── Field change handler ──────────────────────────────────────────────────

  const handleFieldChange = (invoiceId: string, key: string, value: string) => {
    setAllFormData(prev => ({
      ...prev,
      [invoiceId]: { ...(prev[invoiceId] ?? {}), [key]: value },
    }));
  };

  // ── Check for any edits ───────────────────────────────────────────────────

  const hasAnyEdits = (() => {
    for (const id of Object.keys(allFormData)) {
      const form = allFormData[id];
      const initial = allInitialData[id];
      if (!initial) continue;
      for (const key of Object.keys(form)) {
        if (form[key] !== initial[key]) return true;
      }
    }
    return false;
  })();

  // ── Save all edits ────────────────────────────────────────────────────────

  const handleSaveAll = async () => {
    setSavingAll(true);
    try {
      const updates: { id: string; fields: Record<string, unknown> }[] = [];
      for (const id of Object.keys(allFormData)) {
        const form = allFormData[id];
        const initial = allInitialData[id];
        if (!initial) continue;
        const changed: Record<string, unknown> = {};
        for (const key of Object.keys(form)) {
          if (form[key] !== initial[key]) changed[key] = form[key];
        }
        if (Object.keys(changed).length > 0) {
          updates.push({ id, fields: changed });
        }
      }
      if (updates.length > 0) {
        const result = await bulkUpdateInvoicesAction(updates);
        if (result.success) {
          success({ message: `${updates.length} invoice(s) saved!` });
          // Update initial data to current
          setAllInitialData({ ...allFormData });
        } else {
          errorAlert({ message: result.error ?? "Some updates failed." });
        }
      }
    } catch {
      errorAlert({ message: "Failed to save changes." });
    } finally {
      setSavingAll(false);
    }
  };

  // ── Verify all & close ────────────────────────────────────────────────────

  const handleVerifyAllAndClose = async () => {
    setVerifyingAll(true);
    try {
      // Save edits first
      if (hasAnyEdits) {
        const updates: { id: string; fields: Record<string, unknown> }[] = [];
        for (const id of Object.keys(allFormData)) {
          const form = allFormData[id];
          const initial = allInitialData[id];
          if (!initial) continue;
          const changed: Record<string, unknown> = {};
          for (const key of Object.keys(form)) {
            if (form[key] !== initial[key]) changed[key] = form[key];
          }
          if (Object.keys(changed).length > 0) {
            updates.push({ id, fields: changed });
          }
        }
        if (updates.length > 0) {
          await bulkUpdateInvoicesAction(updates);
        }
      }
      // Verify all
      const ids = previewInvoices.map((inv) => inv.id).filter(Boolean);
      if (ids.length > 0) {
        const result = await bulkVerifyInvoicesAction(ids);
        if (result.success) {
          success({ message: `${ids.length} invoice(s) verified!` });
        } else {
          errorAlert({ message: result.error ?? "Some verifications failed." });
        }
      }
    } catch {
      errorAlert({ message: "Verification failed." });
    } finally {
      setVerifyingAll(false);
      if (onUploadSuccess) onUploadSuccess();
    }
  };

  // ── Group Invoices by Document ────────────────────────────────────────────
  const groupedInvoices = useMemo(() => {
    const map = new Map<string, InvoiceDetail[]>();
    for (const inv of previewInvoices) {
      const docName = inv.document?.doc_name || `Invoice #${inv.id}`;
      if (!map.has(docName)) map.set(docName, []);
      map.get(docName)!.push(inv);
    }
    return Array.from(map.entries());
  }, [previewInvoices]);

  // ─── PREVIEW VIEW ──────────────────────────────────────────────────────────

  if (showPreview) {
    return (
      <div className="w-full space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-success text-success-foreground shadow-sm flex items-center justify-center shrink-0">
              <CheckCircle className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground">Upload Complete!</h2>
              <p className="text-xs text-muted-foreground">
                Review extracted data, edit fields, then verify or close.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="gap-1 bg-success/10 text-success border-success/20 text-xs px-2.5 py-1">
              <CheckCircle className="w-3.5 h-3.5" />
              {queue.filter(f => f.status === "completed").length} Processed
            </Badge>
            {queue.filter(f => f.status === "error").length > 0 && (
              <Badge variant="outline" className="gap-1 bg-destructive/10 text-destructive border-destructive/20 text-xs">
                <AlertCircle className="w-3 h-3" />
                {queue.filter(f => f.status === "error").length} Failed
              </Badge>
            )}
          </div>
        </div>

        {/* Invoice Cards — Scrollable */}
        {previewLoading ? (
          <div className="py-16 flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Loading extracted invoices…</p>
          </div>
        ) : previewInvoices.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground text-sm">
            No invoices found. They may still be processing.
          </div>
        ) : (
          <div className="space-y-4 max-h-[65vh] overflow-y-auto pr-1 scrollbar-thin">
            {groupedInvoices.map(([docName, invs], i) => (
              <DocumentGroupCard
                key={docName}
                docName={docName}
                invoices={invs}
                index={i}
                allFormData={allFormData}
                allInitialData={allInitialData}
                onFieldChange={handleFieldChange}
              />
            ))}
          </div>
        )}

        {/* Footer Actions */}
        <div className="sticky bottom-0 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 p-4 sm:p-0 sm:pt-4 sm:pb-2 border-t border-border flex flex-col sm:flex-row items-stretch sm:items-center gap-3 mt-4 z-10 sm:px-1">
          {hasAnyEdits && (
            <Button variant="outline" size="sm" className="gap-2 font-medium w-full sm:w-auto" onClick={handleSaveAll} disabled={savingAll}>
              {savingAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4 text-primary" />}
              Save All Edits
            </Button>
          )}
          <div className="hidden sm:block flex-1" />
          <Button variant="outline" size="sm" onClick={() => { if (onUploadSuccess) onUploadSuccess(); }} className="gap-2 font-medium w-full sm:w-auto sm:px-4">
            <X className="w-4 h-4" /> Close
          </Button>
          <Button
            size="sm"
            className="gap-2 bg-success hover:bg-success/90 text-success-foreground shadow-sm font-medium w-full sm:w-auto sm:px-6"
            onClick={handleVerifyAllAndClose}
            disabled={verifyingAll || previewInvoices.length === 0}
          >
            {verifyingAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            Verify All & Close
          </Button>
        </div>
      </div>
    );
  }

  // ─── UPLOAD VIEW (original) ─────────────────────────────────────────────────

  return (
    <div className="w-full space-y-6">
      <div className="flex justify-between items-end mb-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-foreground tracking-tight">Bulk Upload</h2>
          <p className="text-muted-foreground mt-1 text-sm">Process multiple invoices simultaneously with AI.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setQueue([])} disabled={isProcessing || queue.length === 0}>
            Clear
          </Button>
          <Button size="sm" onClick={startProcessing} disabled={isProcessing || queue.length === 0} className="gap-2 shadow-sm">
            {isProcessing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Start
          </Button>
        </div>
      </div>

      {/* Client Name Input */}
      <div className="space-y-2">
        <Label htmlFor="client-name" className="text-sm font-medium">
          Client Name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="client-name"
          placeholder="Enter client name..."
          value={clientName}
          onChange={(e) => setClientName(e.target.value)}
          disabled={isProcessing}
        />
      </div>

      {/* Upload Zone */}
      <div
        className="border-2 border-dashed border-border rounded-xl p-8 sm:p-12 text-center bg-card hover:bg-accent/20 transition-all cursor-pointer group"
        onClick={() => !isProcessing && document.getElementById("bulk-file-input")?.click()}
      >
        <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform shadow-inner">
          <Files className="w-6 h-6 sm:w-8 sm:h-8 text-primary" />
        </div>
        <h3 className="text-lg sm:text-xl font-bold text-foreground mb-2">Select Multiple Invoices</h3>
        <p className="text-muted-foreground text-xs sm:text-sm mb-6 max-w-xs mx-auto">
          Drag and drop files or click to select from your computer. Supports PDF, JPEG, and Excel.
        </p>
        <input
          id="bulk-file-input"
          type="file"
          multiple
          className="hidden"
          onChange={handleFileSelect}
          disabled={isProcessing}
        />
        <Button variant="secondary" size="sm" className="rounded-full px-6">
          Browse Files
        </Button>
      </div>

      {/* Queue List */}
      {queue.length > 0 && (
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-border bg-muted/30 flex justify-between items-center">
            <span className="text-sm font-semibold text-foreground">{queue.length} Files in Queue</span>
            <span className="text-xs text-muted-foreground">
              {queue.filter(f => f.status === "completed").length} / {queue.length} Completed
            </span>
          </div>
          <div className="divide-y divide-border">
            {queue.map((item) => (
              <div key={item.id} className="p-3 sm:p-4 flex items-center gap-3 sm:gap-4 hover:bg-muted/10 transition-colors">
                <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg bg-muted flex items-center justify-center shadow-sm shrink-0">
                  <FileText className="w-4 h-4 sm:w-5 sm:h-5 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex justify-between items-center gap-2">
                    <p className="text-xs sm:text-sm font-medium text-foreground truncate">{item.file.name}</p>
                    {item.status === "completed" ? (
                      <CheckCircle className="w-4 h-4 text-success shrink-0" />
                    ) : item.status === "processing" ? (
                      <Loader2 className="w-4 h-4 text-primary animate-spin shrink-0" />
                    ) : item.status === "error" ? (
                      <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
                    ) : (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="w-6 h-6 rounded-full hover:bg-destructive/10 hover:text-destructive shrink-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeFile(item.id);
                        }}
                        disabled={isProcessing}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <Progress value={item.progress} className="h-1 sm:h-1.5 flex-1" />
                    <span className="text-[10px] sm:text-xs font-semibold text-muted-foreground w-8 text-right">
                      {item.progress}%
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
