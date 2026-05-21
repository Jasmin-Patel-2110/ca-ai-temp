import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import StoreProvider from "@/lib/redux/StoreProvider";
import { Toaster } from "react-hot-toast";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://ledger-ai-optimised.vercel.app"),
  title: {
    default: "LedgerAI - Smart Invoice Processing",
    template: "%s | LedgerAI",
  },
  description: "AI-powered invoice extraction, verification, and export — built for modern financial teams.",
  keywords: ["Invoice Extraction", "AI", "OCR", "Accounting", "Automation"],
  authors: [{ name: "LedgerAI Team" }],
  openGraph: {
    title: "LedgerAI - Smart Invoice Processing",
    description: "Modern document extraction with AI precision.",
    url: "https://ledger-ai-optimised.vercel.app",
    siteName: "LedgerAI",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "LedgerAI",
    description: "AI-powered invoice extraction",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <StoreProvider>
          {children}
          <Toaster />
        </StoreProvider>
      </body>
    </html>
  );
}
