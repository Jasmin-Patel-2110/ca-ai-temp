import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
    darkMode: "class",
    content: [
        "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                background: "#FFFFFF",
                "dashboard-bg": "#e8ebf5",
                BLUE: "#c8ddfc",
                foreground: "hsl(var(--foreground))",
                card: {
                    DEFAULT: "hsl(var(--card))",
                    foreground: "hsl(var(--card-foreground))",
                },
                popover: {
                    DEFAULT: "hsl(var(--popover))",
                    foreground: "hsl(var(--popover-foreground))",
                },
                input: {
                    border: "black",
                    placeholder: "#808080",
                },
                primary: {
                    "50": "#e6f0ff",
                    "100": "#cce0ff",
                    "200": "#99c2ff",
                    "300": "#66a3ff",
                    "400": "#3385ff",
                    "500": "#0066ff",
                    "600": "#0052cc",
                    "700": "#003d99",
                    "800": "#002966",
                    "900": "#001433",
                    DEFAULT: "#c8ddfc",
                    foreground: "#114391",
                },
                selectedText: "#114391",
                tabBg: "#e9f2ff",
                tabTextColor: "#114391",
                secondary: {
                    DEFAULT: "hsl(var(--secondary))",
                    foreground: "hsl(var(--secondary-foreground))",
                },
                muted: {
                    DEFAULT: "hsl(var(--muted))",
                    foreground: "hsl(var(--muted-foreground))",
                },
                accent: {
                    DEFAULT: "#c8ddfc",
                    foreground: "hsl(var(--accent-foreground))",
                },
                destructive: {
                    DEFAULT: "hsl(var(--destructive))",
                    foreground: "hsl(var(--destructive-foreground))",
                },
                border: "hsl(var(--border))",
                ring: "hsl(var(--ring))",
                chart: {
                    "1": "hsl(var(--chart-1))",
                    "2": "hsl(var(--chart-2))",
                    "3": "hsl(var(--chart-3))",
                    "4": "hsl(var(--chart-4))",
                    "5": "hsl(var(--chart-5))",
                },
                sidebar: {
                    DEFAULT: "hsl(var(--sidebar-background))",
                    foreground: "hsl(var(--sidebar-foreground))",
                    primary: "hsl(var(--sidebar-primary))",
                    accent: "#c8ddfc",
                    border: "hsl(var(--sidebar-border))",
                    ring: "hsl(var(--sidebar-ring))",
                    "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
                    "accent-foreground": "#114391",
                },
            },
            borderRadius: {
                lg: "var(--radius)",
                md: "calc(var(--radius) - 2px)",
                sm: "calc(var(--radius) - 4px)",
            },
            fontFamily: {
                sans: [
                    "Inter",
                    "ui-sans-serif",
                    "system-ui",
                    "-apple-system",
                    "BlinkMacSystemFont",
                    "Roboto",
                    "Arial",
                    "sans-serif",
                    "Apple Color Emoji",
                ],
            },
            fontSize: {
                xs: [
                    "0.75rem",
                    {
                        lineHeight: "1rem",
                    },
                ],
                sm: [
                    "0.875rem",
                    {
                        lineHeight: "1.25rem",
                    },
                ],
                base: [
                    "1rem",
                    {
                        lineHeight: "1.5rem",
                    },
                ],
                lg: [
                    "1.125rem",
                    {
                        lineHeight: "1.75rem",
                    },
                ],
                xl: [
                    "1.25rem",
                    {
                        lineHeight: "1.75rem",
                    },
                ],
                "2xl": [
                    "1.5rem",
                    {
                        lineHeight: "2rem",
                    },
                ],
                "3xl": [
                    "1.875rem",
                    {
                        lineHeight: "2.25rem",
                    },
                ],
                "4xl": [
                    "2.25rem",
                    {
                        lineHeight: "2.5rem",
                    },
                ],
                "5xl": [
                    "3rem",
                    {
                        lineHeight: "1",
                    },
                ],
                "6xl": [
                    "3.75rem",
                    {
                        lineHeight: "1",
                    },
                ],
                poppins: ["Poppins", "sans-serif"],
            },
            screens: {
                xxs: "23.4375rem",
                xs: "29.688rem",
                sm: "40rem",
                md: "48rem",
                lg: "64rem",
                xl: "77.5rem",
                "2xl": "87.5rem",
                "3xl": "100.5rem",
                tab: "113.5rem",
                "4xl": "120.5rem",
            },
            boxShadow: {
                "soft-sm": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
                soft: "0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)",
                "soft-md": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
                "soft-lg": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
                "soft-xl": "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
                "custom-box": "rgba(9, 30, 66, 0.25) 0px 4px 8px -2px, rgba(9, 30, 66, 0.08) 0px 0px 0px 1px",
                "custom-dark": "rgba(255, 255, 255, 0.25) 0px 4px 8px -2px, rgba(255, 255, 255, 0.08) 0px 0px 0px 1px",
                primary: "0 4px 10px rgba(200, 221, 252, 0.5)",
                "dashboard-card": "0 0 35px 0px rgba(154, 161, 171, 0.15)",
            },
            keyframes: {
                "accordion-down": {
                    from: {
                        height: "0",
                    },
                    to: {
                        height: "var(--radix-accordion-content-height)",
                    },
                },
                "accordion-up": {
                    from: {
                        height: "var(--radix-accordion-content-height)",
                    },
                    to: {
                        height: "0",
                    },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.2s ease-out",
                "accordion-up": "accordion-up 0.2s ease-out",
            },
        },
    },
    plugins: [tailwindcssAnimate],
};

export default config;
