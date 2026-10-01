"use server";

import { cookies } from "next/headers";
import axios from "axios";
import apiService from "@/lib/apiService";

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

    const response = await apiService.get<{ data?: DashboardData }>("/invoices/dashboard", {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    });

    return { success: true, data: response?.data };
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response) {
      return { success: false, error: `API error: ${error.response.status}` };
    }

    const errorMessage = error instanceof Error ? error.message : "Failed to fetch dashboard data";
    return { success: false, error: errorMessage };
  }
}
