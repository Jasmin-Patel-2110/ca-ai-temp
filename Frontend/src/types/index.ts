export interface Invoice {
  id: string;
  clientName: string;
  industry: string;
  type: "Purchase" | "Sales";
  category: string;
  subCategory: string;
  date: string;
  time?: string;
  billId: string;
  age?: number;
  gender?: string;
  totalAmount: number;
  status: "pending_extraction" | "pending_verification" | "error" | "verified";
  confidenceScores?: Record<string, number>;
  panNumber?: string;
  gstNumber?: string;
  contactNumber?: string;
}


export interface DashboardStats {
  totalInvoices: number;
  pendingVerification: number;
  processedToday: number;
  exportedInvoices: number;
}

export interface UserProfile {
  sub?: string;
  name: string;
  email: string;
  company: string;
  role: string;
  gstNumber?: string;
  mobileNumber?: string;
  address?: string;
  avatar?: string;
}

export const SUPPORTED_FORMATS = [".pdf", ".jpeg", ".jpg", ".png", ".xlsx"];

import { getIndustries } from "@/constants/industryMapping";

export const INDUSTRIES = getIndustries();

import type { ExtractedData } from "@/components/upload/InvoiceForm";

export const INVOICE_TYPES = ["Purchase", "Sales"] as const;

export interface ExtractionResult {
  data: ExtractedData;
  confidenceScores: {
    [key: string]: number;
  };
}
