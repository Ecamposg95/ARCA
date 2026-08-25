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
        'on-accent': 'hsl(var(--on-accent) / <alpha-value>)',
        'accent-soft': 'hsl(var(--accent-soft) / <alpha-value>)',
        rail: 'hsl(var(--rail) / <alpha-value>)',
        'rail-ink': 'hsl(var(--rail-ink) / <alpha-value>)',
        'rail-muted': 'hsl(var(--rail-muted) / <alpha-value>)',
        pos: 'hsl(var(--pos) / <alpha-value>)',
        neg: 'hsl(var(--neg) / <alpha-value>)',
        warn: 'hsl(var(--warn) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        body: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
        float: '0 10px 40px -10px rgba(0,0,0,0.12)',
        accent: '0 0 20px rgba(44, 154, 166, 0.15)',
      },
      borderRadius: {
        DEFAULT: '8px',
      },
    },
  },
  plugins: [],
}
