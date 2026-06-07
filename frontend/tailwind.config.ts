import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0a0a0f",
        surface: "#111118",
        "surface-2": "#1a1a24",
        border: "#2a2a3a",
        gold: {
          DEFAULT: "#f5a623",
          light: "#ffd07b",
          dark: "#c47d0e",
        },
        green: { trade: "#00c853" },
        red: { trade: "#ff1744" },
        blue: { accent: "#2979ff" },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
