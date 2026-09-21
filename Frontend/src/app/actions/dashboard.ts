"use server";

import { cookies } from "next/headers";

export interface DashboardData {
  total_invoices: number;
  total_pending_verification: number;
  total_created_today: number;
  recent_invoices: RecentInvoice[];
}

export interface RecentInvoice {
  id: number;
  invoice_number?: string | number;
  client_name: string | null;
  buyer_party_name?: string | null;
  seller_party_name?: string | null;
  product_name?: string | null;
  status: string;
  total: string;
  invoice_date?: string | null;
  created_datetime: string;
}

export async function getDashboardStats(): Promise<{ success: boolean; data?: DashboardData; error?: string }> {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;

    if (!token) {
      return { success: false, error: "Not authenticated" };
    }

    const baseUrl = process.env.API_URL || "http://127.0.0.1:8000";
    const response = await fetch(`${baseUrl}/invoices/dashboard`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return { success: false, error: `API error: ${response.status}` };
    }

    const json = await response.json();
    return { success: true, data: json?.data };
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : "Failed to fetch dashboard data";
    return { success: false, error: errorMessage };
  }
}
