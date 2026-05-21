"use client";

import { useCallback } from "react";
import { Upload, FileText, Image, FileSpreadsheet } from "lucide-react";
import { SUPPORTED_FORMATS } from "@/types";
import { useToast } from "@/hooks/use-toast";

interface UploadBoxProps {
  onFileSelect: (file: File) => void;
  disabled?: boolean;
}

export function UploadBox({ onFileSelect, disabled }: UploadBoxProps) {
  const toast = useToast();

  const validate = useCallback(
    (f: File) => {
      const ext = `.${  f.name.split(".").pop()?.toLowerCase()}`;
      if (!SUPPORTED_FORMATS.includes(ext)) {
        toast.errorAlert({
          message: `Only ${SUPPORTED_FORMATS.join(", ")} are supported.`,
        });
        return;
      }
      onFileSelect(f);
    },
    [onFileSelect, toast],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const dropped = e.dataTransfer.files[0];
      if (dropped) validate(dropped);
    },
    [validate],
  );

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className={`border-2 border-dashed border-border rounded-xl p-12 text-center transition-colors cursor-pointer ${disabled
          ? "opacity-50 pointer-events-none"
          : "hover:border-primary/50 hover:bg-accent/30"
        }`}
      onClick={() => document.getElementById("upload-file-input")?.click()}
    >
      <Upload className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
      <h3 className="text-lg font-semibold text-foreground mb-2">
        Drag & drop your invoice here
      </h3>
      <p className="text-sm text-muted-foreground mb-4">or click to browse files</p>
      <div className="flex items-center justify-center gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <FileText className="w-3.5 h-3.5" /> PDF
        </span>
        <span className="flex items-center gap-1">
          <Image className="w-3.5 h-3.5" /> JPEG/PNG
        </span>
        <span className="flex items-center gap-1">
          <FileSpreadsheet className="w-3.5 h-3.5" /> Excel
        </span>
      </div>
      <input
        id="upload-file-input"
        type="file"
        className="hidden"
        accept=".pdf,.jpeg,.jpg,.png,.xlsx"
        onChange={(e) => {
          if (e.target.files?.[0]) validate(e.target.files[0]);
        }}
      />
    </div>
  );
}
