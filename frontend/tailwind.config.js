/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Roboto', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['"Roboto Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        // Semantic tokens → CSS variables (light/dark flip in index.css).
        ink: 'rgb(var(--ink) / <alpha-value>)',
        body: 'rgb(var(--body) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        faint: 'rgb(var(--faint) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        hairline: 'rgb(var(--hairline) / <alpha-value>)',
        canvas: 'rgb(var(--canvas) / <alpha-value>)',
        soft: 'rgb(var(--soft) / <alpha-value>)',
        panel: 'rgb(var(--panel) / <alpha-value>)',
        track: 'rgb(var(--track) / <alpha-value>)',
        oxy: { DEFAULT: '#1976d2', light: '#63a4ff' },
        brand: {
          DEFAULT: 'rgb(var(--brand) / <alpha-value>)',
          deep: 'rgb(var(--brand-deep) / <alpha-value>)',
          light: 'rgb(var(--brand-light) / <alpha-value>)',
          cyan: 'rgb(var(--brand-cyan) / <alpha-value>)',
          tint: 'rgb(var(--brand-tint) / <alpha-value>)',
          lavender: '#e3f2fd',
          mint: '#b2ebf2',
          periwinkle: '#63a4ff',
        },
        risk: {
          high: 'rgb(var(--risk-high) / <alpha-value>)',
          'high-bg': 'rgb(var(--risk-high-bg) / <alpha-value>)',
          med: 'rgb(var(--risk-med) / <alpha-value>)',
          'med-bg': 'rgb(var(--risk-med-bg) / <alpha-value>)',
          missing: 'rgb(var(--risk-missing) / <alpha-value>)',
          'missing-bg': 'rgb(var(--risk-missing-bg) / <alpha-value>)',
          low: 'rgb(var(--risk-low) / <alpha-value>)',
          'low-bg': 'rgb(var(--risk-low-bg) / <alpha-value>)',
        },
      },
      // Square corners everywhere; the tokens stay so one change re-rounds the app.
      borderRadius: {
        card: '0px',
        row: '0px',
        btn: '0px',
        field: '0px',
      },
      // Material elevation levels. Cards sit at level 1, floating surfaces
      // (popovers, toasts, modals) at level 3.
      boxShadow: {
        card: '0 1px 2px rgb(var(--shadow) / 0.14), 0 1px 3px 1px rgb(var(--shadow) / 0.08)',
        row: 'none',
        lift: '0 1px 3px rgb(var(--shadow) / 0.18), 0 4px 8px 3px rgb(var(--shadow) / 0.10)',
        glass: '0 2px 6px 2px rgb(var(--shadow) / 0.12), 0 8px 24px rgb(var(--shadow) / 0.16)',
        'high-row': 'none',
        segment: '0 1px 2px rgb(var(--shadow) / 0.18)',
      },
      keyframes: {
        rise: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          from: { backgroundPosition: '-900px 0' },
          to: { backgroundPosition: '900px 0' },
        },
        toastIn: {
          from: { opacity: '0', transform: 'translateX(34px) translateY(-6px)' },
          to: { opacity: '1', transform: 'none' },
        },
        modalIn: {
          from: { opacity: '0', transform: 'translateY(8px) scale(.97)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(.34,1.56,.64,1)',
        smooth: 'cubic-bezier(.22,.61,.36,1)',
      },
      animation: {
        rise: 'rise .5s cubic-bezier(.22,.61,.36,1) backwards',
        shimmer: 'shimmer 1.6s linear infinite',
        toastIn: 'toastIn .42s cubic-bezier(.34,1.56,.64,1) both',
        modalIn: 'modalIn .22s cubic-bezier(.34,1.56,.64,1) both',
        fadeIn: 'fadeIn .2s ease-out both',
      },
    },
  },
  plugins: [],
}
