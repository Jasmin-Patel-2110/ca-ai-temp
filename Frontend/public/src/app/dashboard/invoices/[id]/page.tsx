"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  ServerCrash,
  FileText,
  Save,
  CheckCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import {
  getInvoiceByIdAction,
  updateInvoiceAction,
} from "@/app/actions/invoices";
import {
  getCategoriesByIndustry,
  getSubCategories,
  getIndustries,
} from "@/constants/industryMapping";

// ─── Types ────────────────────────────────────────────────────────────────────

interface InvoiceDetail {
  id: number;
  invoice_number?: string;
  user_id?: string;
  doc_id?: string;
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
  created_datetime?: string;
  updated_datetime?: string;
}

// ─── Status badge ─────────────────────────────────────────────────────────────

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

// ─── Editable fields ──────────────────────────────────────────────────────────

const FIELDS: {
  key: string;
  label: string;
  type?: "date" | "time" | "select" | "textarea" | "datetime-local";
  options?: string[];
}[] = [
  { key: "invoice_number", label: "Invoice Number" },
  { key: "invoice_date", label: "Invoice Date", type: "date" },
  { key: "client_name", label: "Client Name" },
  {
    key: "industry",
    label: "Industry",
    type: "select",
    options: getIndustries(),
  },
  {
    key: "transaction_type",
    label: "Transaction Type",
    type: "select",
    options: ["Sales", "Purchase"],
  },
  { key: "category", label: "Category", type: "select" },
  { key: "sub_category", label: "Sub Category", type: "select" },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: [
      "pending_extraction",
      "pending_verification",
      "verified",
      "error",
    ],
  },
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
  { key: "buyer_contact_number", label: "Buyer Contact Number" },
  { key: "buyer_gst_number", label: "Buyer GST Number" },
  { key: "buyer_pan_number", label: "Buyer PAN Number" },
  { key: "buyer_location", label: "Buyer Location" },
  { key: "seller_party_name", label: "Seller Party Name" },
  { key: "seller_contact_number", label: "Seller Contact Number" },
  { key: "seller_gst_number", label: "Seller GST Number" },
  { key: "seller_pan_number", label: "Seller PAN Number" },
  { key: "seller_location", label: "Seller Location" },
  { key: "additional_detail", label: "Additional Details", type: "textarea" },
];

// ─── Document Preview ─────────────────────────────────────────────────────────

function DocumentPreview({
  url,
  fileName,
}: {
  url?: string;
  fileName?: string;
}) {
  const name = fileName ?? "Document";
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const isPdf = ext === "pdf";
  const isImage = ["jpg", "jpeg", "png", "webp"].includes(ext);

  return (
    <div className="bg-card rounded-xl border border-border flex flex-col overflow-hidden h-full shadow-sm">
      <div className="px-5 py-3 border-b border-border flex items-center gap-2 shrink-0">
        <FileText className="w-4 h-4 text-primary" />
        <span className="text-sm font-medium text-foreground truncate">
          {name}
        </span>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto text-xs text-primary hover:underline whitespace-nowrap shrink-0"
          >
            Open ↗
          </a>
        )}
      </div>
      <div className="flex-1 overflow-auto bg-muted/30 flex items-center justify-center p-4 min-h-[400px]">
        {!url ? (
          <div className="text-center text-muted-foreground">
            <FileText className="w-16 h-16 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No document preview available</p>
          </div>
        ) : isImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt="Invoice"
            className="max-w-full max-h-[600px] rounded-lg object-contain"
          />
        ) : isPdf ? (
          <iframe
            src={`https://docs.google.com/viewer?url=${encodeURIComponent(url)}&embedded=true`}
            title="PDF Preview"
            className="w-full h-full min-h-[500px] rounded-lg border-0"
          />
        ) : (
          <div className="text-center text-muted-foreground space-y-3">
            <FileText className="w-16 h-16 mx-auto opacity-30" />
            <p className="text-sm">Preview not supported for this file type</p>
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary text-sm hover:underline font-medium"
            >
              Open document ↗
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { success, errorAlert } = useToast();

  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [initialFormData, setInitialFormData] = useState<
    Record<string, string>
  >({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchInvoice = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getInvoiceByIdAction(id);
      if (!res.success || !res.data) {
        setError(res.error ?? "Invoice not found");
        return;
      }
      // API wraps the invoice inside res.data.invoice
      const inv: InvoiceDetail = res.data?.invoice ?? res.data;
      setInvoice(inv);

      // Format invoice_datetime or invoice_date for datetime-local input without timezone conversion
      let dateTimeValue = "";
      const rawDate = inv.invoice_date || inv.invoice_datetime || "";
      if (rawDate) {
        const raw = String(rawDate);
        // If it is already YYYY-MM-DDTHH:MM:SS, keep first 10 chars for date.
        dateTimeValue = raw.length >= 10 ? raw.slice(0, 10) : raw;
      }

      // Serialize additional_detail object as pretty JSON for the textarea
      const additionalStr = inv.additional_detail
        ? JSON.stringify(inv.additional_detail, null, 2)
        : "";

      // Build flat form state from all FIELDS keys
      const initial: Record<string, string> = {};
      FIELDS.forEach(({ key }) => {
        if (key === "invoice_date") {
          initial[key] = dateTimeValue;
          return;
        }
        if (key === "additional_detail") {
          initial[key] = additionalStr;
          return;
        }
        const raw = (inv as unknown as Record<string, unknown>)[key];
        initial[key] = raw != null ? String(raw) : "";
      });
      setFormData(initial);
      setInitialFormData(initial);
    } catch {
      setError("Failed to load invoice details.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchInvoice();
  }, [fetchInvoice]);

  const handleSave = async () => {
    if (!id) return;

    const updatedFields: Record<string, any> = {};
    let hasChanges = false;
    for (const key in formData) {
      if (formData[key] !== initialFormData[key]) {
        updatedFields[key] = formData[key];
        hasChanges = true;
      }
    }

    if (!hasChanges) {
      success({ message: "No changes to save." });
      return;
    }

    setSaving(true);
    try {
      const res = await updateInvoiceAction(id, updatedFields);
      if (res.success) {
        success({ message: "Invoice updated successfully." });
        fetchInvoice();
      } else {
        errorAlert({ message: res.error ?? "Failed to save changes." });
      }
    } catch {
      errorAlert({ message: "An unexpected error occurred." });
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!id) return;

    const updatedFields: Record<string, any> = {};
    for (const key in formData) {
      if (formData[key] !== initialFormData[key]) {
        updatedFields[key] = formData[key];
      }
    }
    updatedFields["status"] = "verified";

    setSaving(true);
    try {
      const res = await updateInvoiceAction(id, updatedFields);
      if (res.success) {
        success({ message: "Invoice verified and saved." });
        router.push("/dashboard/invoices");
      } else {
        errorAlert({ message: res.error ?? "Failed to approve invoice." });
      }
    } catch {
      errorAlert({ message: "An unexpected error occurred." });
    } finally {
      setSaving(false);
    }
  };

  // ─── Loading / Error states ─────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="w-10 h-10 animate-spin text-primary" />
          <p className="text-sm">Loading invoice…</p>
        </div>
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3 text-destructive">
          <ServerCrash className="w-10 h-10 opacity-60" />
          <p className="text-sm font-medium">{error ?? "Invoice not found"}</p>
          <Button variant="outline" size="sm" onClick={() => router.back()}>
            Go Back
          </Button>
        </div>
      </div>
    );
  }

  const status = String(invoice.status ?? "pending_extraction").toLowerCase();
  const statusStyle =
    STATUS_STYLES[status] ?? STATUS_STYLES["pending_extraction"];
  const invoiceLabel = invoice.invoice_number
    ? `INV-${String(invoice.invoice_number).replace(/^INV-/i, "")}`
    : `#${invoice.id}`;

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full animate-in fade-in duration-400 space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            onClick={() => router.back()}
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-bold text-foreground">
                {invoiceLabel}
              </h2>
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`}
                />
                {formatStatus(invoice.status ?? "pending_extraction")}
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              {invoice.buyer_party_name ?? invoice.seller_party_name ?? invoice.client_name ?? "—"}{" "}
              {formData["invoice_date"]
                ? `· ${formData["invoice_date"].replace("T", " ")}`
                : ""}
            </p>
          </div>
        </div>

        <div className="flex gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSave}
            disabled={saving}
            className="gap-2"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Save Changes
          </Button>
          {status !== "verified" && (
            <Button
              size="sm"
              onClick={handleApprove}
              disabled={saving}
              className="gap-2 bg-green-600 hover:bg-green-700 text-white"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle className="w-4 h-4" />
              )}
              Approve & Verify
            </Button>
          )}
        </div>
      </div>

      {/* Split View */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1 min-h-[calc(100vh-12rem)] lg:min-h-[calc(100vh-13rem)]">
        {/* Left — Document Preview */}
        <DocumentPreview
          url={invoice.document?.preview_url ?? invoice.document?.s3_url}
          fileName={invoice.document?.doc_name}
        />

        {/* Right — Extracted Fields (editable) */}
        <div className="bg-card rounded-xl border border-border flex flex-col overflow-hidden shadow-sm">
          <div className="px-5 py-3 border-b border-border shrink-0">
            <span className="text-sm font-semibold text-foreground">
              Extracted Fields
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {FIELDS.map(({ key, label, type, options }) => {
              const current = (formData[key] || "").toString().trim();
              const original = (initialFormData[key] || "").toString().trim();
              const changed = current !== original;

              let currentOptions = options;
              if (key === "category") {
                currentOptions = getCategoriesByIndustry(
                  formData.industry || "",
                );
              } else if (key === "sub_category") {
                currentOptions = getSubCategories(
                  formData.industry || "",
                  formData.category || "",
                );
              }

              return (
                <div
                  key={key}
                  className={`space-y-1.5 p-2.5 rounded-lg border transition-colors ${
                    changed ? "manually-changed" : "border-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {label}
                    </Label>
                    {changed && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-blue-100 text-blue-700 border border-blue-200 uppercase tracking-wider">
                        Edited
                      </span>
                    )}
                  </div>
                  {type === "select" ? (
                    <select
                      value={formData[key] ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setFormData((prev) => {
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
                  ) : type === "textarea" ? (
                    <textarea
                      value={formData[key] ?? ""}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                      rows={3}
                      className={`w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary resize-y min-h-[120px] md:min-h-[180px] transition-colors ${
                        changed
                          ? "bg-transparent border-blue-400 font-medium"
                          : "bg-background border-input"
                      }`}
                    />
                  ) : (
                    <Input
                      type={
                        type === "date"
                          ? "date"
                          : type === "time"
                            ? "time"
                            : type === "datetime-local"
                              ? "datetime-local"
                              : "text"
                      }
                      value={formData[key] ?? ""}
                      onChange={(e) =>
                        setFormData((prev) => ({
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
        </div>
      </div>
    </div>
  );
}
