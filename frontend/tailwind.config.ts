import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#060B18",
          surface: "#0D1528",
          card: "rgba(255,255,255,0.03)",
        },
        gold: {
          DEFAULT: "#F5A623",
          light: "#F7B84E",
          dark: "#D4901E",
        },
        status: {
          green: "#22C55E",
          yellow: "#EAB308",
          red: "#EF4444",
        },
      },
      fontFamily: {
        outfit: ["Outfit", "sans-serif"],
        mono: ["DM Mono", "monospace"],
      },
      backdropBlur: {
        glass: "12px",
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease-out",
        "fade-in-up": "fadeInUp 0.5s ease-out",
        "pulse-dot": "pulseDot 2s ease-in-out infinite",
        "counter": "counter 1s ease-out",
        "gradient-orb": "gradientOrb 15s ease-in-out infinite alternate",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseDot: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.5", transform: "scale(1.5)" },
        },
        gradientOrb: {
          "0%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(30px, -20px) scale(1.1)" },
          "100%": { transform: "translate(-20px, 10px) scale(0.95)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
