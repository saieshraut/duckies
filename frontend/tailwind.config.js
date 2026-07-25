export default {
  content: ["./index.html", "./src/**/*.{vue,js}",
    "./node_modules/frappe-ui/src/**/*.{vue,js}"],
  theme: {
    extend: {
      colors: {
        duck: {
          50: "#fff8ed", 100: "#ffefd4", 200: "#ffdba8",
          300: "#ffc071", 400: "#ff9d38", 500: "#fe7f11",
          600: "#ef6407", 700: "#c64a08", 800: "#9d3a0f",
          900: "#7e3210", 950: "#441705",
        },
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
