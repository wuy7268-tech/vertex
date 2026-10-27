import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#efeae2",
        paper: "#fbf8f3",
        ink: "#1c1916",
        muted: "#6e675f",
        faint: "#948d84",
        line: "#e3dcd2",
        forest: { DEFAULT: "#1e4a3a", soft: "#e6f2ec" },
        clay: { DEFAULT: "#a24b2d", soft: "#f8ebe4" },
        gold: { DEFAULT: "#8a6420", soft: "#f8f0dc" },
        sidebar: "#17211c",
      },
      fontFamily: {
        sans: ["var(--font-outfit)", "sans-serif"],
        serif: ["var(--font-serif)", "serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(28, 25, 22, 0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
