"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Zap, Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { useDispatch, useSelector } from "react-redux";
import { RootState } from "@/lib/redux/store";
import { loginStart, loginSuccess, loginFailure } from "@/lib/redux/slices/authSlice";
import { loginAction } from "@/app/actions/auth";
import { decodeJWT } from "@/lib/utils";
import { motion } from "framer-motion";

const loginSchema = z.object({
  email: z.string().email({ message: "Invalid email address" }),
  password: z.string().min(6, { message: "Password must be at least 6 characters" }),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [isLoadingLocal, setIsLoadingLocal] = useState(false);
  const router = useRouter();
  const toast = useToast();
  const dispatch = useDispatch();
  const token = useSelector((state: RootState) => state.auth.token);

  useEffect(() => {
    if (token) {
      router.push("/dashboard");
    }
  }, [token, router]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormValues) => {
    setIsLoadingLocal(true);
    dispatch(loginStart());

    const formData = new FormData();
    Object.entries(data).forEach(([key, value]) => {
      formData.append(key, value);
    });

    try {
      const result = await loginAction(formData);
      if (result.success && result.user) {
        dispatch(loginSuccess({ user: result.user, token: result.token as string }));
        toast.success({
          message: "Logged in successfully!",
          theme: "colored"
        });
      router.refresh();  
      } else {
        dispatch(loginFailure(result.error as string));
        toast.errorAlert({
          message: result.error as string,
          theme: "colored"
        });
      }
    } catch (error) {
      dispatch(loginFailure("An unexpected error occurred."));
      toast.errorAlert({
        message: "Something went wrong.",
        theme: "colored"
      });
    } finally {
      setIsLoadingLocal(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-background">
      <div className="hidden lg:flex lg:w-1/2 bg-primary/10 items-center justify-center p-12 relative overflow-hidden">
        {/* Simple decorative elements for modern look */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.5, repeat: Infinity, repeatType: "reverse" }}
          className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/20 rounded-full blur-3xl"
        />
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 2, repeat: Infinity, repeatType: "reverse", delay: 0.5 }}
          className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-primary/10 rounded-full blur-3xl"
        />

        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.8 }}
          className="max-w-md text-center z-10"
        >
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/20 backdrop-blur-sm mx-auto mb-8 shadow-xl">
            <Zap className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-4xl font-extrabold text-foreground mb-4 tracking-tight">
            Smart Invoice Processing
          </h2>
          <p className="text-muted-foreground text-lg leading-relaxed">
            AI-powered invoice extraction, verification, and export — built for modern financial teams.
          </p>
        </motion.div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8 bg-card">
        <motion.div
          initial={{ x: 20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.6 }}
          className="w-full max-w-md space-y-8"
        >
          <div className="text-center lg:text-left">
            <div className="flex items-center gap-2 justify-center mb-8 group cursor-default">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary shadow-lg transition-transform group-hover:scale-110">
                <Zap className="w-5 h-5 text-primary-foreground" />
              </div>
              <span className="text-2xl font-bold text-foreground tracking-tight">LedgerAI</span>
            </div>
            <h1 className="text-3xl font-bold text-foreground tracking-tight">Welcome back</h1>
            <p className="text-muted-foreground mt-2">Sign in to your account to continue</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="rajesh@example.com"
                className="h-11 transition-all focus:ring-2 focus:ring-primary/20"
                {...register("email")}
              />
              {errors.email && <p className="text-sm text-destructive font-medium">{errors.email.message}</p>}
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label htmlFor="password">Password</Label>
                <Link href="/forgot-password" className="text-sm font-medium text-primary hover:text-primary/80 transition-colors">
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  className="h-11 pr-10 transition-all focus:ring-2 focus:ring-primary/20"
                  {...register("password")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              {errors.password && <p className="text-sm text-destructive font-medium">{errors.password.message}</p>}
            </div>

            <Button type="submit" className="w-full h-11 text-base font-semibold shadow-lg transition-all active:scale-[0.98]" disabled={isLoadingLocal}>
              {isLoadingLocal ? (
                <div className="flex items-center gap-2">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                  Signing in...
                </div>
              ) : "Sign in"}
            </Button>

            <div className="text-center">
              <p className="text-sm text-muted-foreground">
                Don&apos;t have an account?{" "}
                <Link href="/register" className="font-semibold text-primary hover:text-primary/80 transition-colors">
                  Create an account
                </Link>
              </p>
            </div>
          </form>
        </motion.div>
      </div>
    </div>
  );
}
