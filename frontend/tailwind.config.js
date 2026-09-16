/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        // One face on both surfaces: Instrument Sans (SIL OFL 1.1), self-hosted
        // from /fonts/ and declared at weights 400 and 500 only in index.css.
        // 'Instrument Sans Fallback' is the metric-matched Arial override, so
        // `font-display: swap` reflows nothing when the webfont lands. Arial
        // sits BEHIND Helvetica Neue: Arial is what actually resolves on the
        // Windows clinic machines, so the overrides are tuned to it, but it is
        // the banned body face, so it must not be the first thing anyone sees.
        sans: [
          '"Instrument Sans"',
          '"Instrument Sans Fallback"',
          '"Helvetica Neue"',
          'Helvetica',
          'Arial',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
        // Roboto Mono carries every figure in a table or chart, where
        // proportional digit widths stop columns lining up. It also carries
        // U+00B1 and U+00B5, which Instrument Sans does not.
        mono: ['"Roboto Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },

      // TYPE — two regimes. The UI band is frozen px on a linear +2 ladder
      // (no x.5 size exists); the display band is fluid on one 1920 anchor
      // written max(Npx, N/1920*100vw), so it is pixel-stable up to 1920px and
      // proportional above it. These extend Tailwind's defaults rather than
      // replacing them, so `text-xs` (3 live uses) still resolves.
      fontSize: {
        micro: ['var(--step-micro)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-ui)' }],
        label: ['var(--step-label)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-ui)' }],
        // `copy`, not `body`: `body` is a colour token and Tailwind emits both
        // fontSize and textColor under `text-`, so one name cannot serve both.
        copy: ['var(--step-copy)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-ui)' }],
        'copy-lg': ['var(--step-copy-lg)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-ui)' }],
        lede: ['var(--step-lede)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-ui)' }],
        subhead: ['var(--step-subhead)', { lineHeight: 'var(--lead-title)', letterSpacing: 'var(--track-ui)' }],
        title: ['var(--step-title)', { lineHeight: 'var(--lead-title)', letterSpacing: 'var(--track-title)' }],
        section: ['var(--step-section)', { lineHeight: 'var(--lead-title)', letterSpacing: 'var(--track-title)' }],
        display: ['var(--step-display)', { lineHeight: 'var(--lead-display)', letterSpacing: 'var(--track-display)' }],
        hero: ['var(--step-hero)', { lineHeight: 'var(--lead-display)', letterSpacing: 'var(--track-display)' }],
      },

      letterSpacing: {
        ui: 'var(--track-ui)',
        title: 'var(--track-title)',
        display: 'var(--track-display)',
        eyebrow: 'var(--track-eyebrow)',
      },

      lineHeight: {
        body: 'var(--lead-body)',
        title: 'var(--lead-title)',
        display: 'var(--lead-display)',
        // Pair this with an explicit min-height and centring. Never reading leading.
        label: 'var(--lead-label)',
      },

      // Ceiling is 500 and only 400/500 files are shipped. `semibold` and
      // `bold` are clamped to 500 so the 79 surviving font-semibold/font-bold
      // sites cannot make the browser synthesise a bold face.
      fontWeight: {
        normal: 'var(--weight-body)',
        medium: 'var(--weight-emphasis)',
        semibold: 'var(--weight-emphasis)', // TEMPORARY ALIAS — retire the class, then this
        bold: 'var(--weight-emphasis)', // TEMPORARY ALIAS — retire the class, then this
      },

      // SPACING — one primitive, one 1920 anchor. Named rather than numeric so
      // these cannot collide with Tailwind's own 0.25rem scale.
      spacing: {
        el: 'var(--space-1)', // 4px  inline/element
        seam: 'var(--space-2)', // 8px  shell seam + grid gutter
        tight: 'var(--space-3)', // max(12px, .625vw)
        snug: 'var(--space-4)', // max(16px, .83333vw)
        block: 'var(--space-5)', // max(20px, 1.04167vw) block gap inside a region
        region: 'var(--space-6)', // max(28px, 1.45833vw) section separator
        gutter: 'var(--page-gutter)', // max(12px, .625vw)
      },

      // The console has no container cap today, so a patient table renders
      // 2472px wide on a 2560px display.
      maxWidth: {
        container: 'var(--container-max)', // max(1440px, 75vw)
      },

      borderRadius: {
        surface: 'var(--r-surface)', // 0px
        control: 'var(--r-control)', // 3px — control <= surface, so the role reads
        pill: 'var(--r-pill)', // 999px
        // TEMPORARY ALIASES — 39 rounded-btn, 19 rounded-card, 15 rounded-row and
        // 6 rounded-field are live right now. A later phase migrates them.
        card: 'var(--r-surface)',
        row: 'var(--r-surface)',
        btn: 'var(--r-control)',
        field: 'var(--r-control)',
      },

      // ELEVATION — exactly two real shadows. `hairline` is a 0-blur 1px ring,
      // which IS the hairline: it layers with nothing and costs no layout box.
      // `overlay` is the single ambient wash, for floating overlays only.
      boxShadow: {
        hairline: 'var(--shadow-hairline)',
        overlay: 'var(--shadow-overlay)',
        // TEMPORARY ALIASES for the 23 live shadow-* uses.
        card: 'var(--shadow-hairline)', // 15 uses, all cards
        lift: 'var(--shadow-hairline)', // 3 uses, all chart cards — not floating
        glass: 'var(--shadow-overlay)', // 4 uses: Toast, popover, Modal, PlanModal
        row: 'none',
        'high-row': 'none',
        // NOT elevation: the NotificationSettingsPage toggle knob. Keeps its own
        // contact shadow so a blanket elevation sweep cannot flatten the switch.
        segment: '0 1px 2px rgb(var(--shadow) / 0.18)',
      },

      colors: {
        // The ramp, addressable directly for the rare case that needs a step
        // rather than a role.
        n: {
          0: 'rgb(var(--n-0) / <alpha-value>)',
          50: 'rgb(var(--n-50) / <alpha-value>)',
          100: 'rgb(var(--n-100) / <alpha-value>)',
          200: 'rgb(var(--n-200) / <alpha-value>)',
          300: 'rgb(var(--n-300) / <alpha-value>)',
          400: 'rgb(var(--n-400) / <alpha-value>)',
          425: 'rgb(var(--n-425) / <alpha-value>)',
          450: 'rgb(var(--n-450) / <alpha-value>)',
          460: 'rgb(var(--n-460) / <alpha-value>)',
          475: 'rgb(var(--n-475) / <alpha-value>)',
          500: 'rgb(var(--n-500) / <alpha-value>)',
          600: 'rgb(var(--n-600) / <alpha-value>)',
          700: 'rgb(var(--n-700) / <alpha-value>)',
          800: 'rgb(var(--n-800) / <alpha-value>)',
          900: 'rgb(var(--n-900) / <alpha-value>)',
          950: 'rgb(var(--n-950) / <alpha-value>)',
        },

        // Roles. Light and dark re-index the same ramp in index.css.
        ink: 'rgb(var(--ink) / <alpha-value>)',
        body: 'rgb(var(--body) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        // NON-TEXT ONLY, and only where WCAG 1.4.11 does not apply (disabled
        // controls, pure decoration). 2.585:1 on light panel. Placeholders are
        // text and take `muted`.
        faint: 'rgb(var(--faint) / <alpha-value>)',
        hairline: 'rgb(var(--hairline) / <alpha-value>)',
        line: {
          DEFAULT: 'rgb(var(--line) / <alpha-value>)',
          strong: 'rgb(var(--line-strong) / <alpha-value>)',
        },
        canvas: 'rgb(var(--canvas) / <alpha-value>)',
        soft: 'rgb(var(--soft) / <alpha-value>)',
        panel: 'rgb(var(--panel) / <alpha-value>)',

        brand: {
          DEFAULT: 'rgb(var(--brand) / <alpha-value>)', // FILL ONLY
          ink: 'rgb(var(--brand-ink) / <alpha-value>)', // the foreground blue
          deep: 'rgb(var(--brand-deep) / <alpha-value>)',
          tint: 'rgb(var(--brand-tint) / <alpha-value>)',
          'tint-strong': 'rgb(var(--brand-tint-strong) / <alpha-value>)',
          // TEMPORARY ALIASES — brand-cyan is a chart stroke (now teal-graphic,
          // 3.509:1 rather than 2.738:1); brand-light was the old dark brand.
          cyan: 'rgb(var(--brand-cyan) / <alpha-value>)',
          light: 'rgb(var(--brand-light) / <alpha-value>)',
        },
        'on-brand': 'rgb(var(--on-brand) / <alpha-value>)',
        'on-brand-tint': 'rgb(var(--on-brand-tint) / <alpha-value>)',

        teal: {
          DEFAULT: 'rgb(var(--teal) / <alpha-value>)', // FILL ONLY (2.738:1 on white)
          ink: 'rgb(var(--teal-ink) / <alpha-value>)', // the only teal allowed as text
          graphic: 'rgb(var(--teal-graphic) / <alpha-value>)', // strokes, rules, accent bars
          tint: 'rgb(var(--teal-tint) / <alpha-value>)',
        },
        'on-teal': 'rgb(var(--on-teal) / <alpha-value>)',

        risk: {
          'high-ink': 'rgb(var(--risk-high-ink) / <alpha-value>)',
          'high-tint': 'rgb(var(--risk-high-tint) / <alpha-value>)',
          'med-ink': 'rgb(var(--risk-med-ink) / <alpha-value>)',
          'med-tint': 'rgb(var(--risk-med-tint) / <alpha-value>)',
          'low-ink': 'rgb(var(--risk-low-ink) / <alpha-value>)',
          'low-tint': 'rgb(var(--risk-low-tint) / <alpha-value>)',
          'missing-ink': 'rgb(var(--risk-missing-ink) / <alpha-value>)',
          'missing-tint': 'rgb(var(--risk-missing-tint) / <alpha-value>)',
          // TEMPORARY ALIASES — 104 live risk-* class references (39 risk-high,
          // 33 risk-med, 32 risk-low, 18 risk-missing plus 55 -bg).
          high: 'rgb(var(--risk-high) / <alpha-value>)',
          'high-bg': 'rgb(var(--risk-high-bg) / <alpha-value>)',
          med: 'rgb(var(--risk-med) / <alpha-value>)',
          'med-bg': 'rgb(var(--risk-med-bg) / <alpha-value>)',
          missing: 'rgb(var(--risk-missing) / <alpha-value>)',
          'missing-bg': 'rgb(var(--risk-missing-bg) / <alpha-value>)',
          low: 'rgb(var(--risk-low) / <alpha-value>)',
          'low-bg': 'rgb(var(--risk-low-bg) / <alpha-value>)',
        },

        // A non-flipping black. NEVER --ink, which inverts to #FFFFFF in dark
        // and brightens the page behind the modal.
        scrim: 'rgb(var(--scrim) / var(--scrim-alpha))',
        overlay: {
          panel: 'rgb(var(--overlay-panel) / <alpha-value>)',
          border: 'rgb(var(--overlay-border) / <alpha-value>)',
        },

        disabled: {
          fill: 'rgb(var(--disabled-fill) / <alpha-value>)',
          ink: 'rgb(var(--disabled-ink) / <alpha-value>)',
        },

        chart: {
          s1: 'rgb(var(--chart-s1) / <alpha-value>)',
          s2: 'rgb(var(--chart-s2) / <alpha-value>)',
          'seq-1': 'rgb(var(--chart-seq-1) / <alpha-value>)',
          'seq-2': 'rgb(var(--chart-seq-2) / <alpha-value>)',
          'seq-3': 'rgb(var(--chart-seq-3) / <alpha-value>)',
          'seq-4': 'rgb(var(--chart-seq-4) / <alpha-value>)',
          'seq-5': 'rgb(var(--chart-seq-5) / <alpha-value>)',
          grid: 'rgb(var(--chart-grid) / <alpha-value>)',
          'axis-label': 'rgb(var(--chart-axis-label) / <alpha-value>)',
          'ref-line': 'rgb(var(--chart-ref-line) / <alpha-value>)',
          'cell-stroke': 'rgb(var(--chart-cell-stroke) / <alpha-value>)',
        },

        // TEMPORARY ALIASES — declared in index.css so the arbitrary-value
        // reads in src/ keep resolving.
        track: 'rgb(var(--track) / <alpha-value>)',
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
