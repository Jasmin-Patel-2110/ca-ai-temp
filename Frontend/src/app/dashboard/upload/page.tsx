"use client";

import { useState, useMemo } from "react";
import { UploadBox } from "@/components/upload/UploadBox";
import { InvoicePreview } from "@/components/upload/InvoicePreview";
import { InvoiceForm, type ExtractedData } from "@/components/upload/InvoiceForm";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { FileText, Image, FileSpreadsheet, X, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { uploadInvoiceAction } from "@/app/actions/upload";
import { ExtractionResult } from "@/types";

type Stage = "upload" | "processing" | "review";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("upload");
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [formData, setFormData] = useState<ExtractedData | null>(null);
  const [initialData, setInitialData] = useState<ExtractedData | null>(null);
  const [progress, setProgress] = useState(0);
  const toast = useToast();

  const previewUrl = useMemo(() => {
    if (!file) return null;
    if (/\.(jpe?g|png)$/i.test(file.name)) return URL.createObjectURL(file);
    if (file.name.toLowerCase().endsWith(".pdf")) return URL.createObjectURL(file);
    return null;
  }, [file]);

  const getFileIcon = (name: string) => {
    if (name.endsWith(".pdf")) return <FileText className="w-6 h-6 text-destructive" />;
    if (/\.(jpe?g|png)$/i.test(name)) return <Image className="w-6 h-6 text-success" />;
    if (name.endsWith(".xlsx")) return <FileSpreadsheet className="w-6 h-6 text-primary" />;
    return <FileText className="w-6 h-6 text-muted-foreground" />;
  };

  const handleProcess = async () => {
    if (!file) return;
    setStage("processing");
    setProgress(0);

    // Simulate progress alongside the API call
    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 90) return p;
        return p + Math.random() * 12;
      });
    }, 250);

    try {
      const formDataObj = new FormData();
      formDataObj.append("file", file);

      const res = await uploadInvoiceAction(formDataObj);

      clearInterval(interval);

      if (res.success && res.data) {
        setProgress(100);
        setResult(res.data);
        setFormData({ ...res.data.data });
        setInitialData({ ...res.data.data });
        setTimeout(() => setStage("review"), 400);
      } else {
        throw new Error(res.error || "Failed to process");
      }
    } catch (err) {
      clearInterval(interval);
      setStage("upload");
      toast.errorAlert({
        message: (err as Error).message || "Please try again."
      });
    }
  };

  const reset = () => {
    setFile(null);
    setStage("upload");
    setResult(null);
    setFormData(null);
    setInitialData(null);
    setProgress(0);
  };

  if (stage === "review" && file && formData && result) {
    return (
      <div className="animate-in fade-in duration-500">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-4">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Verify Extracted Data</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Review and correct the AI-extracted information from your document.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={reset}>
              Discard
            </Button>
            <Button size="sm" className="bg-success hover:bg-success/90 text-white">
              Approve & Save
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-14rem)]">
          <InvoicePreview file={file} previewUrl={previewUrl} />
          <InvoiceForm
            data={formData}
            onChange={setFormData}
            originalData={initialData || undefined}
            confidenceScores={result.confidenceScores}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="text-center mb-10">
        <h2 className="text-3xl font-bold text-foreground tracking-tight">Upload Invoice</h2>
        <p className="text-muted-foreground mt-2">
          Upload a single invoice for AI-powered data extraction and verification.
        </p>
      </div>

      {stage === "upload" ? (
        <div className="space-y-6">
          {!file ? (
            <UploadBox onFileSelect={setFile} />
          ) : (
            <div className="bg-card rounded-xl border border-border p-6 shadow-sm animate-in zoom-in-95 duration-300">
              <div className="flex items-center gap-4 mb-8">
                <div className="w-14 h-14 rounded-xl bg-muted flex items-center justify-center shadow-inner">
                  {getFileIcon(file.name)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-foreground truncate">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {(file.size / 1024).toFixed(1)} KB • Ready to process
                  </p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setFile(null)} className="rounded-full hover:bg-destructive/10 hover:text-destructive">
                  <X className="w-5 h-5" />
                </Button>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <Button variant="outline" className="flex-1 h-11" onClick={() => setFile(null)}>
                  Change File
                </Button>
                <Button className="flex-1 h-11 shadow-lg" onClick={handleProcess}>
                  Start Processing
                </Button>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4">
            {[
              { title: "High Accuracy", desc: "95%+ OCR precision", icon: "✨" },
              { title: "Smart Mapping", desc: "Auto-categorization", icon: "🧠" },
              { title: "Quick Export", desc: "Ready for Tally/Excel", icon: "🚀" },
            ].map((feature) => (
              <div key={feature.title} className="p-4 rounded-xl bg-muted/50 border border-transparent hover:border-border transition-colors">
                <span className="text-2xl mb-2 block">{feature.icon}</span>
                <p className="text-sm font-semibold text-foreground">{feature.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-card rounded-2xl border border-border p-12 text-center shadow-xl animate-in zoom-in-95 duration-500">
          <div className="relative w-24 h-24 mx-auto mb-8">
            <div className="absolute inset-0 rounded-full border-4 border-primary/20" />
            <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin" />
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 className="w-10 h-10 text-primary animate-pulse" />
            </div>
          </div>
          <h3 className="text-xl font-bold text-foreground mb-2">Analyzing Document...</h3>
          <p className="text-muted-foreground text-sm max-w-xs mx-auto mb-8">
            Our AI engine is extracting data from your invoice. This usually takes 2-3 seconds.
          </p>
          <div className="max-w-md mx-auto space-y-2">
            <div className="flex justify-between text-xs font-medium">
              <span className="text-primary">Progress</span>
              <span className="text-muted-foreground">{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} className="h-2" />
          </div>
        </div>
      )}
    </div>
  );
}
