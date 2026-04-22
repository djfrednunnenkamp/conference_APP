/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          blue: {
            50:  '#eef4fb',
            100: '#d5e5f5',
            200: '#abcbeb',
            300: '#7aaed9',
            400: '#4d90c7',
            500: '#2b72af',
            600: '#1f5a8e',
            700: '#17446e',
            800: '#102e4e',
            900: '#091b30',
          },
          green: {
            50:  '#edf7f0',
            100: '#d0ecd8',
            200: '#a1d9b1',
            300: '#6ec48a',
            400: '#42ad65',
            500: '#2d9150',
            600: '#22733f',
            700: '#185630',
            800: '#0f3a20',
            900: '#071e11',
          },
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
