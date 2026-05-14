import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        tier: {
          S: "#16a34a",
          A: "#2563eb",
          B: "#d97706",
          C: "#dc2626",
          D: "#6b7280",
        },
      },
    },
  },
  plugins: [],
};
export default config;