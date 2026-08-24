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
        surface: {
          DEFAULT: "#1c1c1f",
          card:    "#28282f",
          raised:  "#31313c",
          border:  "#3f3f4a",
        },
        accent: {
          DEFAULT: "#00bba3",
          muted:   "#0a8f7f",
        },
        gold: {
          DEFAULT: "#d7b792",
          muted:   "#907659",
        },
        tier: {
          S: "#00bba3",
          A: "#3b82f6",
          B: "#eb9c00",
          C: "#ef4444",
          D: "#6b7280",
        },
      },
    },
  },
  plugins: [],
};
export default config;