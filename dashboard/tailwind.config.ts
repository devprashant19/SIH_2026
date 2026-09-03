import type { Config } from "tailwindcss";

// Colours reference CSS variables from src/styles/tokens.css so light/dark and the
// "severity colours only for risk" rule are enforced in one place.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        muted: "var(--color-text-muted)",
        accent: { DEFAULT: "var(--color-accent)", bg: "var(--color-accent-bg)" },
        risk: {
          critical: "var(--color-risk-critical)",
          "critical-bg": "var(--color-risk-critical-bg)",
          high: "var(--color-risk-high)",
          "high-bg": "var(--color-risk-high-bg)",
          elevated: "var(--color-risk-elevated)",
          "elevated-bg": "var(--color-risk-elevated-bg)",
          low: "var(--color-risk-low)",
          "low-bg": "var(--color-risk-low-bg)",
          none: "var(--color-risk-none)",
          "none-bg": "var(--color-risk-none-bg)",
        },
        uncertain: { DEFAULT: "var(--color-uncertain)", bg: "var(--color-uncertain-bg)" },
        cat: {
          1: "var(--color-cat-1)",
          2: "var(--color-cat-2)",
          3: "var(--color-cat-3)",
          4: "var(--color-cat-4)",
          5: "var(--color-cat-5)",
          6: "var(--color-cat-6)",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "Menlo", "monospace"],
      },
      fontSize: {
        xs: ["12px", "16px"],
        sm: ["13px", "18px"],
        base: ["14px", "20px"],
        md: ["16px", "24px"],
        lg: ["18px", "26px"],
        xl: ["22px", "28px"],
        num: ["28px", "32px"],
      },
      borderRadius: { sm: "4px", md: "6px" },
      boxShadow: { drawer: "0 4px 16px rgba(0,0,0,0.08)" },
      // One named stacking order for every overlay in the app. The guide layers sit above
      // the drawer and the toasts so a tour can spotlight a control inside an open drawer.
      zIndex: {
        nav: "10",
        sticky: "20",
        drawer: "40",
        toast: "50",
        "guide-scrim": "60",
        "guide-ring": "61",
        "guide-popover": "62",
      },
    },
  },
  plugins: [],
} satisfies Config;
