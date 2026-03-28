/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        dino: {
          green: "#22c55e",
          dark: "#0a0a0a",
        },
      },
    },
  },
  plugins: [],
};
