// theme/static_src/tailwind.config.js
const colors = require('tailwindcss/colors')

module.exports = {
    darkMode: 'class',   // 👈 enable class-based dark mode

    content: [
        '../templates/**/*.html',
        '../../templates/**/*.html',
        '../../repository/templates/**/*.html',
        '../../magnet/templates/**/*.html',
    ],
    theme: {
        extend: {
            colors: {
                gray: colors.slate,
            },
        },
    },
    plugins: [],
    safelist: [
    'bg-red-200',
    'hover:bg-red-300',
    'bg-green-200',
    'hover:bg-green-300',
  ]
}
