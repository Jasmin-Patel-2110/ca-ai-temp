"use client";

import { FileText } from "lucide-react";
import Image from "next/image";

interface InvoicePreviewProps {
  file: File;
  previewUrl: string | null;
}

export function InvoicePreview({ file, previewUrl }: InvoicePreviewProps) {
  const isPdf = file.name.toLowerCase().endsWith(".pdf");
  const isImage = /\.(jpe?g|png)$/i.test(file.name);

  return (
    <div className="bg-card rounded-xl border border-border card-shadow flex flex-col overflow-hidden h-full">
      <div className="px-5 py-3 border-b border-border flex items-center gap-2">
        <FileText className="w-4 h-4 text-primary" />
        <span className="text-sm font-medium text-foreground truncate">
          {file.name}
        </span>
        <span className="ml-auto text-xs text-muted-foreground">
          {(file.size / 1024).toFixed(1)} KB
        </span>
      </div>

      <div className="flex-1 overflow-auto bg-muted/30 flex items-center justify-center p-4 min-h-[400px]">
        {isImage && previewUrl ? (
          <Image
            src={previewUrl}
            alt="Invoice preview"
            width={0}
            height={0}
            sizes="100vw"
            className="max-w-full max-h-[600px] rounded-lg object-contain"
          />
        ) : isPdf && previewUrl ? (
          <iframe
            src={previewUrl}
            title="PDF Preview"
            className="w-full h-full min-h-[500px] rounded-lg border-0"
          />
        ) : (
          <div className="text-center text-muted-foreground">
            <FileText className="w-16 h-16 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Document preview</p>
            <p className="text-xs mt-1">{file.name}</p>
          </div>
        )}
      </div>
    </div>
  );
}
