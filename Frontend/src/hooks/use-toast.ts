import { toast, ToastOptions } from "react-hot-toast";

export type ToastType = "success" | "error" | "info" | "warning" | "loading" | "custom" | "promise";

interface ToastProps {
    message: string;
    duration?: number;
    theme?: "light" | "dark" | "colored";
    isUnique?: boolean;
    icon?: string;
}

interface PromiseToastProps {
    promise: Promise<any>;
    loading: string;
    success?: string | ((data: any) => string);
    error: string | ((error: any) => string);
    duration?: number;
    theme?: "light" | "dark" | "colored";
    isUnique?: boolean;
    icon?: string;
}

const useToast = () => {
    // Helper to get base styling dependent on theme
    const getThemeStyles = (theme?: "light" | "dark" | "colored", type: ToastType = "custom"): React.CSSProperties => {
        const baseStyle: React.CSSProperties = {
            borderRadius: "12px",
            padding: "16px",
            boxShadow: "0 10px 40px -10px rgba(0,0,0,0.2)",
            fontFamily: "inherit",
            fontWeight: 500,
            transition: "all 0.3s ease",
        };

        if (theme === "colored") {
            switch (type) {
                case "success":
                    return { ...baseStyle, background: "#10B981", color: "#FFFFFF" };
                case "error":
                    return { ...baseStyle, background: "#EF4444", color: "#FFFFFF" };
                case "warning":
                    return { ...baseStyle, background: "#F59E0B", color: "#FFFFFF" };
                case "info":
                case "loading":
                case "promise":
                    return { ...baseStyle, background: "#3B82F6", color: "#FFFFFF" };
                default:
                    return { ...baseStyle, background: "#6366F1", color: "#FFFFFF" };
            }
        }

        // Glassmorphism fallback for Light / Dark
        return theme === "light"
            ? { ...baseStyle, background: "rgba(255, 255, 255, 0.9)", color: "#171717", backdropFilter: "blur(10px)", border: "1px solid rgba(0,0,0,0.05)" }
            : { ...baseStyle, background: "rgba(23, 23, 23, 0.9)", color: "#FAFAFA", backdropFilter: "blur(10px)", border: "1px solid rgba(255,255,255,0.1)" };
    };

    const defaultOptions = (props: ToastProps, type: ToastType = "custom"): ToastOptions => ({
        duration: props.duration || 4000,
        position: "top-center",
        style: getThemeStyles(props.theme, type),
        id: props.isUnique !== false ? props.message : undefined,
        icon: props.icon === "" ? undefined : props.icon,
    });

    const success = (props: ToastProps) => toast.success(props.message, { ...defaultOptions(props, "success"), icon: props.icon ?? undefined });
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const error = (props: ToastProps) => {
        // toast.error(props.message, { ...defaultOptions(props, "error"), icon: props.icon ?? undefined });
    };
    const errorAlert = (props: ToastProps) => {
        toast.error(props.message, { ...defaultOptions(props, "error"), icon: props.icon ?? undefined });
    };
    const info = (props: ToastProps) => toast(props.message, { ...defaultOptions(props, "info"), icon: props.icon ?? "ℹ️" });
    const warning = (props: ToastProps) => toast(props.message, { ...defaultOptions(props, "warning"), icon: props.icon ?? "⚠️" });
    const loading = (props: ToastProps) => toast.loading(props.message, { ...defaultOptions(props, "loading"), icon: props.icon ?? "⏳" });
    const custom = (props: ToastProps) => toast(props.message, { ...defaultOptions(props, "custom") });

    const showPromiseToast = ({ promise, loading, success, error, duration, theme = "light", isUnique }: PromiseToastProps) => {
        return toast.promise(
            promise,
            {
                loading,
                success,
                error,
            },
            defaultOptions({ message: loading, duration, theme, isUnique }, "promise")
        );
    };

    return { success, error, info, errorAlert, warning, loading, custom, showPromiseToast };
};

export { useToast, toast };
