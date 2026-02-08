module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        ink: "#0f172a",
        slate: "#334155",
        mist: "#f8fafc",
      },
    },
  },
  plugins: [],
};
