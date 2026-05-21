"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Download,
  Loader2,
  ServerCrash,
  Inbox,
  CheckSquare,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { useRedux } from "@/hooks/useRedux";
import * as xlsx from "xlsx";

// Shadcn UI components
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("auth_token") ?? "";
}

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

function mapInvoiceForExport(inv: Record<string, any>) {
  const tType = String(inv.transaction_type ?? inv.type ?? "").toLowerCase().trim();
  
  let partyName = "";
  let gstNo = "";
  
  if (tType === "sales" || tType === "sale") {
    partyName = inv.buyer_party_name ?? "";
    gstNo = inv.buyer_gst_number ?? inv.gst_number ?? inv.gst_no ?? "";
  } else if (tType === "purchase") {
    partyName = inv.seller_party_name ?? "";
    gstNo = inv.seller_gst_number ?? inv.gst_number ?? inv.gst_no ?? "";
  } else {
    // Default fallback
    partyName = inv.buyer_party_name ?? inv.seller_party_name ?? "";
    gstNo = inv.buyer_gst_number ?? inv.seller_gst_number ?? inv.gst_number ?? inv.gst_no ?? "";
  }

  return {
    _id: String(
      inv.id ??
      inv.invoice_id ??
      inv.invoice_number ??
      Math.random()
    ), // Used for internal react key / selection
    "Invoice No": inv.invoice_number ?? inv.invoice_id ?? inv.id ?? "",
    "Invoice Date": inv.invoice_date?.split("T")[0] ?? inv.date ?? inv.invoice_datetime?.split("T")[0] ?? "",
    "Party Name": partyName,
    "Transaction Type": inv.transaction_type ?? inv.type ?? "",
    "Sale Ledger": inv.subcategory ?? inv.sub_category ?? "",
    "Product Name": inv.line_items?.[0]?.product_name ?? inv.product_name ?? inv.item_name ?? "",
    "Quantity": inv.quantity ?? "",
    "Rate": inv.rate ?? "",
    "Amount": inv.amount ?? inv.total_amount ?? inv.total ?? "",
    "GST No": gstNo,
    "SGST": inv.sgst ?? "",
    "CGST": inv.cgst ?? "",
    "IGST": inv.igst ?? "",
  };
}

export default function ExportPage() {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New UI state
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedFormat, setSelectedFormat] = useState("excel");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { success, errorAlert } = useToast();
  const { selector } = useRedux();
  const user = selector((s) => s.auth.user);

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
      const json = await res.json();
      const rawInvoices = json.invoices ?? [];
      setData(rawInvoices.map(mapInvoiceForExport));
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load data for export.",
      );
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // Filtering data for preview
  const filteredData = useMemo(() => {
    if (!searchQuery.trim()) return data;
    const query = searchQuery.toLowerCase();
    return data.filter((row) =>
      Object.values(row).some((val) =>
        String(val).toLowerCase().includes(query),
      ),
    );
  }, [data, searchQuery]);

  // Selection handlers
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      const allIds = new Set(filteredData.map((r) => r._id));
      setSelectedIds(allIds);
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectRow = (id: string, checked: boolean) => {
    const newSelected = new Set(selectedIds);
    if (checked) {
      newSelected.add(id);
    } else {
      newSelected.delete(id);
    }
    setSelectedIds(newSelected);
  };

  const isAllSelected =
    filteredData.length > 0 && selectedIds.size === filteredData.length;
  const isSomeSelected =
    selectedIds.size > 0 && selectedIds.size < filteredData.length;

  const handleExport = () => {
    if (selectedIds.size === 0) {
      errorAlert({ message: "Please select at least one invoice to export." });
      return;
    }

    const rowsToExport = data
      .filter((row) => selectedIds.has(row._id))
      .map((row) => {
        // Strip out internal _id and Status for the final export
        const { _id, Status, ...rest } = row;
        return rest;
      });

    if (selectedFormat === "csv") {
      try {
        const headers = Object.keys(rowsToExport[0]);
        const csvContent = [
          headers.join(","),
          ...rowsToExport.map((row) =>
            headers
              .map((field) => {
                const val = row[field as keyof typeof row];
                const stringVal = String(val).replace(/"/g, "\"\"");
                return `"${stringVal}"`;
              })
              .join(","),
          ),
        ].join("\n");

        const blob = new Blob([csvContent], {
          type: "text/csv;charset=utf-8;",
        });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `exported_invoices_${new Date().toISOString().split("T")[0]}.csv`;
        link.click();
        success({
          message: `Successfully exported ${rowsToExport.length} invoice(s) to CSV!`,
        });
      } catch (err) {
        errorAlert({ message: "Failed to generate CSV." });
      }
    } else {
      try {
        const worksheet = xlsx.utils.json_to_sheet(rowsToExport);
        const workbook = xlsx.utils.book_new();
        xlsx.utils.book_append_sheet(workbook, worksheet, "Invoices");
        xlsx.writeFile(
          workbook,
          `exported_invoices_${new Date().toISOString().split("T")[0]}.xlsx`,
        );
        success({
          message: `Successfully exported ${rowsToExport.length} invoice(s) to Excel!`,
        });
      } catch (err) {
        errorAlert({ message: "Failed to generate Excel file." });
      }
    }
  };

  const displayedColumns =
    data.length > 0 ? Object.keys(data[0]).filter((k) => k !== "_id") : [];

  return (
    <div className="space-y-6 animate-in fade-in duration-500 h-full flex flex-col">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Export Data</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Select the invoices and the format you wish to export.
          </p>
        </div>

        <div className="flex items-center gap-3 bg-card p-2 rounded-xl border border-border shadow-sm">
          <Select value={selectedFormat} onValueChange={setSelectedFormat}>
            <SelectTrigger className="w-[140px] h-9 border-none bg-muted/50 focus:ring-0">
              <SelectValue placeholder="Format" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="excel">Excel (.xlsx)</SelectItem>
              <SelectItem value="csv">CSV (.csv)</SelectItem>
            </SelectContent>
          </Select>
          <Button
            onClick={handleExport}
            disabled={selectedIds.size === 0 || loading}
            className="gap-2 h-9 px-4"
          >
            <Download className="w-4 h-4" />
            Export {selectedIds.size > 0 ? `(${selectedIds.size})` : ""}
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="bg-card rounded-xl border border-border shadow-sm flex flex-col flex-1 min-h-[500px]">
        {/* Table Toolbar */}
        <div className="p-4 border-b border-border flex flex-col sm:flex-row gap-4 items-center justify-between bg-muted/20">
          <div className="relative w-full sm:max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search invoices..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9 bg-background"
            />
          </div>
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <CheckSquare className="w-4 h-4 text-primary" />
            <span className="font-medium text-foreground">
              {selectedIds.size}
            </span>{" "}
            selected
            {filteredData.length !== data.length &&
              ` (out of ${filteredData.length} filtered)`}
          </div>
        </div>

        {/* Table/Status States */}
        <div className="flex-1 overflow-auto relative">
          {loading ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <Loader2 className="w-10 h-10 text-primary animate-spin mb-4" />
              <p className="text-muted-foreground font-medium">
                Loading records...
              </p>
            </div>
          ) : error ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <ServerCrash className="w-10 h-10 opacity-60 text-destructive mb-4" />
              <p className="text-muted-foreground font-medium">{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchAll}
                className="mt-4"
              >
                Retry
              </Button>
            </div>
          ) : filteredData.length === 0 ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <Inbox className="w-10 h-10 opacity-40 text-muted-foreground mb-4" />
              <p className="text-muted-foreground font-medium">
                {searchQuery
                  ? "No invoices match your search."
                  : "No records found to export."}
              </p>
            </div>
          ) : (
            <table className="w-full text-sm text-left whitespace-nowrap">
              <thead className="sticky top-0 z-10 bg-card border-b border-border shadow-sm">
                <tr>
                  <th className="px-5 py-4 w-12">
                    <Checkbox
                      checked={
                        isAllSelected ||
                        (isSomeSelected ? "indeterminate" : false)
                      }
                      onCheckedChange={(checked) => handleSelectAll(!!checked)}
                      aria-label="Select all"
                    />
                  </th>
                  {displayedColumns.map((col) => (
                    <th
                      key={col}
                      className="px-4 py-4 font-semibold text-muted-foreground"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredData.map((row) => {
                  const isSelected = selectedIds.has(row._id);
                  return (
                    <tr
                      key={row._id}
                      className={`transition-colors hover:bg-muted/40 cursor-pointer ${
                        isSelected ? "bg-primary/5 hover:bg-primary/10" : ""
                      }`}
                      onClick={() => handleSelectRow(row._id, !isSelected)}
                    >
                      <td
                        className="px-5 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={(checked) =>
                            handleSelectRow(row._id, !!checked)
                          }
                          aria-label={`Select row ${row._id}`}
                        />
                      </td>
                      {displayedColumns.map((col) => {
                        const val = row[col as keyof typeof row];
                        let displayVal: React.ReactNode =
                          val === "" || val == null ? (
                            <span className="text-muted-foreground/40 italic text-xs">
                              N/A
                            </span>
                          ) : (
                            String(val)
                          );

                        if (col === "Status" && val) {
                          const statusStr = String(val);
                          const key = statusStr.trim().toLowerCase();
                          const style =
                            STATUS_STYLES[key] ?? STATUS_STYLES["pending"];
                          displayVal = (
                            <span
                              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${style.bg} ${style.text}`}
                            >
                              <span
                                className={`w-1.5 h-1.5 rounded-full ${style.dot}`}
                              />
                              {formatStatus(statusStr)}
                            </span>
                          );
                        }

                        return (
                          <td
                            key={col}
                            className="px-4 py-3 text-foreground/80"
                          >
                            {displayVal}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
