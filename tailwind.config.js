module.exports = {
  content: [
    "./src/templates/**/*.html",
    "./src/templates/*.html",
    "./src/static/js/**/*.js"
  ],
  darkMode: 'class',
  theme: {
    extend: {},
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
