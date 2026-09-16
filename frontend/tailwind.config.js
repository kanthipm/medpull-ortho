/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',

  // Tailwind removes any rule in @layer components whose class never appears in
  // the scanned content, and several of these recipes have no call site YET —
  // the migration agents are about to add them. Without this list `.scrim` and
  // `.overlay` are simply absent from the built CSS and a modal renders with no
  // backdrop at all. These are the shared recipe names, not utilities; nothing
  // is generated for them, they are only protected from the removal pass.
  safelist: [
    'scrim',
    'overlay',
    'panel',
    'field',
    'chip',
    'micro',
    'zone-label',
    'qa-btn',
    'btn-primary',
    'segment',
    'on',
    'shimmer',
    'rise',
  ],
  theme: {
    // WEIGHT — NOT in `extend`, deliberately: this REPLACES Tailwind's weight
    // scale instead of merging with it, so `font-semibold`, `font-bold`,
    // `font-thin` and the rest do not exist as utilities at all.
    //
    // The clamp that used to map semibold/bold down to 500 is GONE, because
    // nothing names them any more. A live-code scan of src/ (comments and
    // prose excluded) finds font-medium x218, font-normal x10 and ZERO above
    // 500; the count was 79 when the clamp went in. The two strings `grep
    // font-semibold` still returns are prose in index.css's own font header.
    //
    // Replacing rather than clamping is the point: a future `font-semibold`
    // now emits NOTHING and the element keeps its inherited 400/500 — a
    // visible no-op in review — instead of emitting `font-weight: 600` and
    // making the browser synthesise a bold face out of the 500 file, which is
    // exactly what the clamp existed to prevent. No `<b>`/`<strong>` is used
    // anywhere in src/, so preflight's `font-weight: bolder` never fires.
    fontWeight: {
      normal: 'var(--weight-body)',
      medium: 'var(--weight-emphasis)',
    },
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
      },

      // GLASS — the console gets exactly ONE blurred surface, the modal scrim,
      // and `backdrop-blur-scrim` is the only blur utility anyone should reach
      // for. Prefer the `.scrim` recipe, which also carries the three
      // degradation blocks. Never on a clinical number, never on /checkin or
      // /t, never glass-on-glass, max two blurred surfaces per viewport.
      backdropBlur: {
        scrim: 'var(--blur-scrim)', // 2px
      },

      // ELEVATION — one ambient wash (`overlay`, floating overlays only) and
      // one contact shadow (`knob`, the toggle knob on its track). A card gets
      // a border or a fill, never a shadow: `.panel` is `border border-line`.
      // `hairline` (a 6%/8% alpha ring, 1.216:1 light / 1.138:1 dark) is
      // deleted along with --shadow-hairline; `.panel` was its only consumer.
      // All five aliases (`card`, `lift`, `glass`, `row`, `high-row`) are
      // deleted: zero live class uses between them. The `shadow-card` strings
      // a grep still finds are prose inside three doc comments
      // (MetricCluster.tsx:28, NotificationsPopover.tsx:13, EmptyState.tsx:4)
      // describing the double edge that was removed — Tailwind's content
      // scanner cannot tell a comment from a className, which is why the count
      // has to come from a live-code scan and not from `grep -c`.
      // Note for whoever wrote `lift: // 3 uses, all chart cards — not
      // floating`: that was wrong. All three were chart TOOLTIP containers,
      // which ARE floating overlays, and they are on `.overlay` now.
      boxShadow: {
        // The one ambient wash, floating overlays only — modal, popover,
        // toast, chart tooltip. `.overlay` is the recipe.
        overlay: 'var(--shadow-overlay)',
        // NOT elevation: the toggle knob's contact shadow, so the knob lifts
        // off its track. Routed through --shadow-knob so dark has its own
        // value (the old literal was byte-identical in both modes and dead on
        // dark). One live use, features/settings/NotificationSettingsPage.tsx.
        knob: 'var(--shadow-knob)',
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
          // `cyan` and `light` deleted: the charts read --chart-s1/--chart-s2
          // and --teal-graphic now, and nothing reads either name.
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
          // THE LAST SIX ALIASES IN THE TOKEN SET, and they exist for ONE
          // component: components/ConfidenceChip.tsx:4-6, whose STYLES map is
          // still `bg-risk-low-bg text-risk-low`, `bg-risk-med-bg
          // text-risk-med` and `bg-risk-missing-bg text-risk-missing`. Rewrite
          // those three strings to the `-tint`/`-ink` pairs and these six keys
          // plus the six matching custom properties in index.css all go.
          // `high` and `high-bg` are ALREADY deleted — nothing consumed them.
          // (The two strings a grep finds are prose in WorklistPage.tsx:218
          // and Toast.tsx:56, describing alpha washes that were removed.)
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
        toastOut: {
          from: { opacity: '1', transform: 'none' },
          to: { opacity: '0', transform: 'translateX(16px)' },
        },
        modalOut: {
          from: { opacity: '1', transform: 'translateY(0) scale(1)' },
          to: { opacity: '0', transform: 'translateY(4px) scale(.98)' },
        },
        fadeOut: {
          from: { opacity: '1' },
          to: { opacity: '0' },
        },
      },
      // MOTION — 150-300ms, ease-out entering, no overshoot on clinical
      // content. `spring` (cubic-bezier(.34,1.56,.64,1), a 56% overshoot) is
      // deleted: zero live `ease-spring` uses, and its two keyframe users
      // (toastIn, modalIn) now enter on `smooth`. Exits run ~65% of the enter
      // duration on ease-in, so a dismissal never lingers.
      transitionTimingFunction: {
        smooth: 'cubic-bezier(.22,.61,.36,1)', // ease-out, entering
        exit: 'cubic-bezier(.4,0,1,1)', // ease-in, leaving
      },
      animation: {
        // Enter.
        rise: 'rise 240ms cubic-bezier(.22,.61,.36,1) backwards', // was 500ms
        toastIn: 'toastIn 240ms cubic-bezier(.22,.61,.36,1) both', // was 420ms + spring
        modalIn: 'modalIn 220ms cubic-bezier(.22,.61,.36,1) both', // was spring
        fadeIn: 'fadeIn 200ms cubic-bezier(.22,.61,.36,1) both',
        // Exit — ~65% of the matching enter.
        toastOut: 'toastOut 160ms cubic-bezier(.4,0,1,1) both',
        modalOut: 'modalOut 150ms cubic-bezier(.4,0,1,1) both',
        fadeOut: 'fadeOut 130ms cubic-bezier(.4,0,1,1) both',
        // Not an entrance: a skeleton's loading loop. Linear and continuous by
        // nature; prefers-reduced-motion stops it.
        shimmer: 'shimmer 1.6s linear infinite',
      },
    },
  },
  plugins: [],
}
