import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    container: {
      center: true,
      padding: {
        DEFAULT: "1.25rem",
        sm: "1.5rem",
        lg: "2rem",
      },
      screens: {
        sm: "640px",
        md: "768px",
        lg: "1024px",
        xl: "1200px",
        "2xl": "1320px",
      },
    },
    extend: {
      colors: {
        // Brand palette (fixed by the project brief)
        primary: {
          DEFAULT: "#3E7D32",
          dark: "#2E5D25",
          light: "#E7F1E5",
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "#F4B400",
          dark: "#C99000",
          light: "#FDF3D6",
          foreground: "#1E2A1A",
        },
        accent: {
          DEFAULT: "#FF7043",
          dark: "#E65A2E",
          light: "#FFE7DD",
          foreground: "#FFFFFF",
        },
        // Warm neutrals that sit around the brand colors
        background: "#FBFAF6",
        foreground: "#1E2A1A",
        muted: {
          DEFAULT: "#F2EFE6",
          foreground: "#5B6B55",
        },
        border: "#E4DFD1",
        card: {
          DEFAULT: "#FFFFFF",
          foreground: "#1E2A1A",
        },
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem",
        "3xl": "2rem",
        blob: "63% 37% 54% 46% / 43% 47% 53% 57%",
      },
      boxShadow: {
        soft: "0 8px 30px -8px rgba(30, 42, 26, 0.15)",
        card: "0 4px 20px -6px rgba(30, 42, 26, 0.12)",
        lift: "0 20px 40px -12px rgba(62, 125, 50, 0.25)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s ease-out both",
        float: "float 6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
