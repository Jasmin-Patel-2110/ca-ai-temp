"use server";

import { ExtractionResult } from "@/types";
import { cookies } from "next/headers";
import apiService from "@/lib/apiService";

export async function uploadInvoiceAction(formData: FormData): Promise<{ success: boolean; data?: ExtractionResult; error?: string }> {
  const file = formData.get("file") as File;
  if (!file) {
    return { success: false, error: "No file uploaded" };
  }

  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 2000));

  // Mock extraction data (similar to ledger-light/src/lib/api.ts)
  const mockData: ExtractionResult = {
    data: {
      client_name: "Sunrise Pharma Pvt Ltd",
      buyer_party_name: "Sunrise Pharma Pvt Ltd",
      seller_party_name: "Health Equipment Ltd",
      buyer_gst_number: "22AAAAA0000A1Z5",
      seller_gst_number: "33BBBBB1111B2Z6",
      buyer_pan_number: "AAAAA0000A",
      seller_pan_number: "BBBBB1111B",
      buyer_contact_number: "9876543210",
      seller_contact_number: "0123456789",
      industry: "Healthcare",
      type: "Purchase",
      category: "Medical Supplies",
      subcategory: "Equipment",
      date: "2025-02-20",
      time: "14:30",
      bill_id: "B-4521",
      age: "45",
      gender: "Male",
      total_amount: "45200",
    },
    confidenceScores: {
      client_name: 0.97,
      buyer_party_name: 0.97,
      seller_party_name: 0.95,
      buyer_gst_number: 0.9,
      seller_gst_number: 0.88,
      buyer_pan_number: 0.92,
      seller_pan_number: 0.91,
      buyer_contact_number: 0.85,
      seller_contact_number: 0.86,
      industry: 0.88,
      type: 0.91,
      category: 0.72,
      subcategory: 0.65,
      date: 0.99,
      time: 0.85,
      bill_id: 0.94,
      age: 0.78,
      gender: 0.69,
      total_amount: 0.95,
    },
  };

  return { success: true, data: mockData };
}

export async function bulkUploadAction(formData: FormData) {
  const files = formData.getAll("files") as File[];
  if (!files || files.length === 0) {
    return { success: false, error: "No files uploaded" };
  }

  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;

    if (!token) {
      return { success: false, error: "Not authenticated" };
    }
    const uploadFormData = new FormData();
    const clientName = formData.get("client_name");
    if (clientName) {
      uploadFormData.append("known_client_name", clientName as string);
    }
    for (const file of files) {
      uploadFormData.append("files", file);
    }

    try {
      // Send all files in one single request and capture the response
      const response = await apiService.upload<any>("/invoices/upload", uploadFormData, {
        headers: {
          "Authorization": `Bearer ${token}`
        },
        timeout: 300000 // Increase timeout to 5 minutes as OCR takes time
      });

      // If the batch request succeeds, we assume all files in the batch were processed
      const successes = files.map(f => f.name);

      return {
        success: true,
        processedCount: successes.length,
        successes,
        errors: [],
        message: `${successes.length} invoice(s) processed successfully.`,
        responseData: response,
      };
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || "Bulk upload failed";
      // If the batch request fails, mark all files in the batch as error
      return {
        success: false,
        error: errorMsg,
        successes: [],
        errors: files.map(f => f.name)
      };
    }
  } catch (error: any) {
    return { success: false, error: error?.message || "Failed to connect to upload API", successes: [], errors: [] };
  }
}
