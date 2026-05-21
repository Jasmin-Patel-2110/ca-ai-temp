import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function decodeJWT(token: string) {
  try {
    const base64Url = token.split(".")[1];
    if (!base64Url) return null;
    
    // Handle padding
    let base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    while (base64.length % 4) {
      base64 += "=";
    }

    // Decode to binary string
    const binaryString = atob(base64);
    
    // Correctly handle UTF-8 characters
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const jsonPayload = new TextDecoder().decode(bytes);
    return JSON.parse(jsonPayload);
  } catch (error) {
    return null;
  }
}
