"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSelector } from "react-redux";
import { RootState } from "@/lib/redux/store";
import { Zap, Mail, ArrowLeft, CheckCircle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";

export default function ForgotPasswordPage() {
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const toast = useToast();
  const router = useRouter();
  const token = useSelector((state: RootState) => state.auth.token);

  useEffect(() => {
    if (token) {
      router.push("/dashboard");
    }
  }, [token, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    // Simulate API call
    await new Promise(r => setTimeout(r, 1500));
    setIsLoading(false);
    setIsSubmitted(true);
    toast.success({
      message: "Check your inbox for password reset instructions.",
    });
  };

  return (
    <div className="flex min-h-screen bg-background">
      <div className="hidden lg:flex lg:w-1/2 bg-primary/10 items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-primary/10 rounded-full blur-3xl animate-pulse" />

        <div className="max-w-md text-center z-10">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/20 backdrop-blur-sm mx-auto mb-8 shadow-xl">
            <Zap className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-4xl font-extrabold text-foreground mb-4 tracking-tight">
            Security First
          </h2>
          <p className="text-muted-foreground text-lg leading-relaxed">
            Your data security is our top priority. We use industry-standard encryption to protect your information.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8 bg-card">
        <div className="w-full max-w-md space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
          {!isSubmitted ? (
            <>
              <div className="text-center lg:text-left">
                <Link href="/login" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary transition-colors mb-8 group">
                  <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
                  Back to Login
                </Link>
                <div className="flex items-center gap-2 justify-center lg:justify-center mb-8 group cursor-default">
                  <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary shadow-lg transition-transform group-hover:scale-110">
                    <Zap className="w-5 h-5 text-primary-foreground" />
                  </div>
                  <span className="text-2xl font-bold text-foreground tracking-tight">LedgerAI</span>
                </div>
                <h1 className="text-3xl font-bold text-foreground tracking-tight">Forgot Password?</h1>
                <p className="text-muted-foreground mt-2">Enter your email and we&apos;ll send you reset instructions.</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-2">
                  <Label htmlFor="email">Email Address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="rajesh@example.com"
                      className="pl-10 h-11"
                      required
                    />
                  </div>
                </div>

                <Button type="submit" className="w-full h-11 text-base font-semibold shadow-lg" disabled={isLoading}>
                  {isLoading ? "Sending..." : "Send Reset Link"}
                </Button>
              </form>
            </>
          ) : (
            <div className="text-center space-y-6">
              <div className="w-20 h-20 rounded-full bg-success/10 flex items-center justify-center mx-auto shadow-inner border-2 border-success/20">
                <CheckCircle className="w-10 h-10 text-success" />
              </div>
              <div className="space-y-2">
                <h2 className="text-3xl font-bold text-foreground">Email Sent!</h2>
                <p className="text-muted-foreground">
                  We&apos;ve sent a password reset link to your email address. Please check your inbox and spam folder.
                </p>
              </div>
              <Button asChild className="w-full h-11 shadow-lg">
                <Link href="/login">Back to Login</Link>
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
