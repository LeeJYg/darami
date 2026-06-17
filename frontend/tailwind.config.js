/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#FAF3E7",
        sand: "#F3E7D3",
        acorn: "#6B4226",
        bark: "#4A2F1B",
        nut: { DEFAULT: "#E8862E", soft: "#F4A85B", deep: "#D2691E" },
        leaf: "#7BA05B",
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "-apple-system",
          "system-ui",
          "Apple SD Gothic Neo",
          "sans-serif",
        ],
      },
      boxShadow: {
        phone: "0 30px 60px -20px rgba(74,47,27,0.45)",
      },
    },
  },
  plugins: [],
};
