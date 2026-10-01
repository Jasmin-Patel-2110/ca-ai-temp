"use server";

import { cookies } from "next/headers";
import apiService from "@/lib/apiService";

type InvoiceReadResult<T> =
  | { success: true; data: T }
  | { success: false; error: string; data: null };

type InvoicesResponse = {
  status: number;
  message: string;
  invoices: any[];
};

type InvoiceSearchResponse = {
  status: number;
  message: string;
  query: string;
  results: any[];
};

function invoiceReadError(error: any, fallback: string): string {
  const body = error?.response?.data;
  if (typeof body?.message === "string" && body.message) return body.message;
  if (typeof body?.detail === "string" && body.detail) return body.detail;
  if (error?.response?.status) return `Server error: ${error.response.status}`;
  return typeof error?.message === "string" && error.message ? error.message : fallback;
}

export async function getInvoicesAction(): Promise<InvoiceReadResult<InvoicesResponse>> {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;
    if (!token) {
      return { success: false, error: "Not authenticated", data: null };
    }

    const data = await apiService.get<InvoicesResponse>("/invoices", {
      headers: { "Authorization": `Bearer ${token}` }
    });
    return { success: true, data };
  } catch (error: any) {
    return { success: false, error: invoiceReadError(error, "Failed to fetch invoices"), data: null };
  }
}

export async function searchInvoicesAction(query: string): Promise<InvoiceReadResult<InvoiceSearchResponse>> {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;
    if (!token) {
      return { success: false, error: "Not authenticated", data: null };
    }

    const data = await apiService.get<InvoiceSearchResponse>("/invoices/search", {
      headers: { "Authorization": `Bearer ${token}` },
      params: { q: query, top_k: 20 }
    });
    return { success: true, data };
  } catch (error: any) {
    return { success: false, error: invoiceReadError(error, "Failed to search invoices"), data: null };
  }
}

export async function deleteInvoiceAction(invoiceId: string | number) {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;

    if (!token) {
      return { success: false, error: "Not authenticated" };
    }

    await apiService.delete(`/invoices/${invoiceId}`, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    return { success: true };
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message || "Failed to delete invoice";
    return { success: false, error: errorMsg };
  }
}

export async function getInvoiceByIdAction(invoiceId: string | number) {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;

    if (!token) {
      return { success: false, error: "Not authenticated", data: null };
    }

    const data = await apiService.get<any>(`/invoices/${invoiceId}`, {
      headers: { "Authorization": `Bearer ${token}` }
    });

    return { success: true, data };
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message || "Failed to fetch invoice";
    return { success: false, error: errorMsg, data: null };
  }
}

export async function updateInvoiceAction(invoiceId: string | number, payload: Record<string, unknown>) {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;

    if (!token) { 
      return { success: false, error: "Not authenticated" };
    }

    await apiService.patch<any>(`/invoices/${invoiceId}`, payload, {
      headers: { "Authorization": `Bearer ${token}` }
    });

    return { success: true };
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message || "Failed to update invoice";
    return { success: false, error: errorMsg };
  }
}

export async function bulkUpdateInvoicesAction(
  updates: { id: string | number; fields: Record<string, unknown> }[]
) {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;

    if (!token) {
      return { success: false, error: "Not authenticated", results: [] };
    }

    const results = await Promise.allSettled(
      updates.map(({ id, fields }) =>
        apiService.patch<any>(`/invoices/${id}`, fields, {
          headers: { "Authorization": `Bearer ${token}` },
        })
      )
    );

    const perInvoice = results.map((r, i) => ({
      id: updates[i].id,
      success: r.status === "fulfilled",
      error:
        r.status === "rejected"
          ? (r.reason?.response?.data?.detail ?? r.reason?.message ?? "Failed")
          : undefined,
    }));

    const failedCount = perInvoice.filter((r) => !r.success).length;

    return {
      success: failedCount === 0,
      error: failedCount > 0 ? `${failedCount} invoice(s) failed to update` : undefined,
      results: perInvoice,
    };
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message || "Bulk update failed";
    return { success: false, error: errorMsg, results: [] };
  }
}

export async function bulkVerifyInvoicesAction(invoiceIds: (string | number)[]) {
  return bulkUpdateInvoicesAction(
    invoiceIds.map((id) => ({ id, fields: { status: "verified" } }))
  );
}
