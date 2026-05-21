"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Save, CheckCircle } from "lucide-react";
import { INDUSTRIES, INVOICE_TYPES } from "@/types";
import { getCategoriesByIndustry, getSubCategories } from "@/constants/industryMapping";
import { useToast } from "@/hooks/use-toast";

export interface ExtractedData {
  client_name: string;
  buyer_party_name: string;
  seller_party_name: string;
  buyer_gst_number: string;
  seller_gst_number: string;
  buyer_pan_number: string;
  seller_pan_number: string;
  buyer_contact_number: string;
  seller_contact_number: string;
  industry: string;
  type: string;
  category: string;
  subcategory: string;
  date: string;
  time: string;
  bill_id: string;
  age: string;
  gender: string;
  total_amount: string;
}

interface InvoiceFormProps {
  data: ExtractedData;
  onChange: (data: ExtractedData) => void;
  originalData?: ExtractedData;
  confidenceScores?: Record<string, number>;
}

function ConfBadge({ score, isEdited }: { score?: number; isEdited?: boolean }) {
  if (score === undefined && !isEdited) return null;
  
  if (isEdited) {
    return (
      <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-blue-100 text-blue-700 border border-blue-200">
        Edited
      </span>
    );
  }

  const pct = Math.round(score! * 100);
  const color =
    pct >= 90
      ? "bg-success/10 text-success"
      : pct >= 75
        ? "bg-warning/10 text-warning"
        : "bg-destructive/10 text-destructive";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${color}`}>
      {pct}%
    </span>
  );
}

const FIELDS: {
  key: keyof ExtractedData;
  label: string;
  type?: "select" | "date" | "time";
  options?: readonly string[] | string[];
}[] = [
  { key: "client_name", label: "Client Name" },
  { key: "buyer_party_name", label: "Buyer Name" },
  { key: "seller_party_name", label: "Seller Name" },
  { key: "buyer_gst_number", label: "Buyer GST" },
  { key: "seller_gst_number", label: "Seller GST" },
  { key: "buyer_pan_number", label: "Buyer PAN" },
  { key: "seller_pan_number", label: "Seller PAN" },
  { key: "buyer_contact_number", label: "Buyer Contact" },
  { key: "seller_contact_number", label: "Seller Contact" },
  { key: "industry", label: "Industry", type: "select", options: INDUSTRIES },
  { key: "type", label: "Type", type: "select", options: INVOICE_TYPES },
  { key: "category", label: "Category", type: "select" },
  { key: "subcategory", label: "Sub Category", type: "select" },
  { key: "date", label: "Date", type: "date" },
  { key: "time", label: "Time (Optional)", type: "time" },
  { key: "bill_id", label: "Bill ID" },
  { key: "age", label: "Age" },
  {
    key: "gender",
    label: "Gender",
    type: "select",
    options: ["Male", "Female", "Other"],
  },
  { key: "total_amount", label: "Total Amount" },
];

export function InvoiceForm({
  data,
  onChange,
  originalData,
  confidenceScores = {},
}: InvoiceFormProps) {
  const toast = useToast();
  const update = (key: keyof ExtractedData, value: string) => {
    const newData = { ...data, [key]: value };
    if (key === "industry") {
      newData.category = "";
      newData.subcategory = "";
    } else if (key === "category") {
      newData.subcategory = "";
    }
    onChange(newData);
  };
  
  const isLow = (key: string) => (confidenceScores[key] ?? 1) < 0.8;
  const isChanged = (key: keyof ExtractedData) => {
    if (!originalData) return false;
    const current = (data[key] || "").toString().trim();
    const original = (originalData[key] || "").toString().trim();
    return current !== original;
  };

  return (
    <div className="bg-card rounded-xl border border-border card-shadow flex flex-col overflow-hidden h-full">
      <div className="px-5 py-3 border-b border-border">
        <span className="text-sm font-medium text-foreground">
          Extracted Fields
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {FIELDS.map(({ key, label, type, options }) => {
          const changed = isChanged(key);
          const lowConf = isLow(key);
          
          let currentOptions = options;
          if (key === "category") {
            currentOptions = getCategoriesByIndustry(data.industry || "");
          } else if (key === "subcategory") {
            currentOptions = getSubCategories(data.industry || "", data.category || "");
          }
          
          return (
            <div
              key={key}
              className={`space-y-1.5 p-2.5 rounded-lg border transition-colors ${
                changed 
                  ? "manually-changed" 
                  : lowConf 
                    ? "low-confidence" 
                    : "border-transparent"
              }`}
            >
              <div className="flex items-center justify-between">
                <Label className="text-xs">{label}</Label>
                <ConfBadge score={confidenceScores[key]} isEdited={changed} />
              </div>
              {type === "select" ? (
                <select
                  value={data[key]}
                  onChange={(e) => update(key, e.target.value)}
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
                  type={type === "date" ? "date" : type === "time" ? "time" : "text"}
                  value={data[key]}
                  onChange={(e) => update(key, e.target.value)}
                  className={`transition-colors ${
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

      <div className="flex gap-3 p-4 border-t border-border">
        <Button
          variant="outline"
          className="flex-1"
          onClick={() => toast.success({ message: "Changes saved" })}
        >
          <Save className="w-4 h-4 mr-2" /> Save Changes
        </Button>
        <Button
          className="flex-1"
          onClick={() => toast.success({ message: "Invoice approved & exported!" })}
        >
          <CheckCircle className="w-4 h-4 mr-2" /> Approve & Export
        </Button>
      </div>
    </div>
  );
}
