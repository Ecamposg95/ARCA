/** Tokens semánticos ARCA — cero colores crudos en componentes (convención Atlas). */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'hsl(var(--bg) / <alpha-value>)',
        surface: 'hsl(var(--surface) / <alpha-value>)',
        'surface-2': 'hsl(var(--surface-2) / <alpha-value>)',
        ink: 'hsl(var(--ink) / <alpha-value>)',
        muted: 'hsl(var(--muted) / <alpha-value>)',
        border: 'hsl(var(--border) / <alpha-value>)',
        accent: 'hsl(var(--accent) / <alpha-value>)',
        'accent-soft': 'hsl(var(--accent-soft) / <alpha-value>)',
        rail: 'hsl(var(--rail) / <alpha-value>)',
        'rail-ink': 'hsl(var(--rail-ink) / <alpha-value>)',
        'rail-muted': 'hsl(var(--rail-muted) / <alpha-value>)',
        pos: 'hsl(var(--pos) / <alpha-value>)',
        neg: 'hsl(var(--neg) / <alpha-value>)',
        warn: 'hsl(var(--warn) / <alpha-value>)',
      },
      fontFamily: {
        display: ['Archivo', 'system-ui', 'sans-serif'],
        body: ['"Public Sans"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(22 33 28 / 0.05)',
        float: '0 8px 24px -6px rgb(22 33 28 / 0.16)',
      },
      borderRadius: {
        DEFAULT: '10px',
      },
    },
  },
  plugins: [],
}
