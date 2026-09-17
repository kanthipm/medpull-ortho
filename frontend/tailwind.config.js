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
    'overlay-menu',
    'panel',
    'clip-surface',
    'card-group',
    'card-row',
    'card-tint',
    'on-tint',
    'row-risk-high',
    'is-interactive',
    'stretched-link',
    'above-stretch',
    'page',
    'page-worklist',
    'page-patient',
    'page-settings',
    'ambient',
    'ambient-host',
    'appbar',
    'appbar-link',
    'nav-rule',
    'field',
    'field-pill',
    'chip',
    'meta',
    'micro',
    // Buttons — the Apple ladder.
    'btn-filled',
    'btn-tinted',
    'btn-gray',
    'btn-plain',
    'btn-plain-muted',
    'btn-danger',
    'btn-on-tint',
    'btn-danger-on-tint',
    'btn-icon',
    'btn-send',
    'btn-sm',
    'btn-lg',
    'tile',
    'tile-lg',
    'tile-blue',
    'tile-teal',
    'tile-indigo',
    'tile-violet',
    'tile-risk-high',
    'avatar',
    'avatar-risk',
    'seg-track',
    'seg-thumb',
    'seg-item',
    'spring-move',
    // State marker read by .seg-item.on and .appbar-link.on.
    'on',
    'shimmer',
    'rise',
    // Atmosphere + glass (Aside-derived). See index.css.
    'sky-stage',
    'sky-window',
    'on-sky',
    'glass',
    'glass-overlay',
    'field-glass',
    'seg-glass',
    'tile-frost',
    'badge-ring',
    'shimmer-text',
    'well',
    'ground-shadow',
    // medpull.org language (index.css).
    'appbar-inner',
    'brand-lockup',
    'app-icon',
    'app-icon-lg',
    'dot-lime',
    'big-num',
    'display-title',
    'gtile',
    'gtile-top',
    'gtile-kicker',
    'gtile-num',
    'gtile-side',
    'gtile-art',
    'gtile-cap',
    'g-sage',
    'g-meadow',
    'g-amber',
    'g-clay',
    'g-dusk',
    'g-lilac',
    'g-mint',
    'g-origin',
    'art',
    'art-line',
    'art-dash',
    'art-grid',
    'art-dot',
    'art-node',
    'meter',
    'meter-fill',
    'meter-on-tile',
    'aurora',
    'av-1',
    'av-2',
    'av-3',
    'av-4',
    'av-5',
    'reveal',
    'is-shown',
    'is-paused',
    'draw-in',
    'comet',
    'pulse-ring',
    'pop-in',
    'grow-y',
    'now-dot',
    'spotlight',
    'dash-flow',
    'gauge-fill',
    'canvas-card',
    'reply',
    'float-y',
  ],
  theme: {
    // WEIGHT — NOT in `extend`, deliberately: this REPLACES Tailwind's weight
    // scale instead of merging with it, so `font-bold`, `font-thin` and the
    // rest do not exist as utilities at all.
    //
    // `semibold` (600) is back, and a real InstrumentSans-SemiBold.woff2 is
    // shipped and declared in index.css, so nothing is synthesised. It is for
    // TITLES ONLY: the page h1, the patient name, the active app-bar tab.
    // Body and meta stay `normal`; row titles and labels stay `medium`.
    // `font-bold` still emits NOTHING (no 700 file exists on the web), so a
    // stray one is a visible no-op in review rather than a faux-bold face.
    // No `<b>`/`<strong>` is used anywhere in src/, so preflight's
    // `font-weight: bolder` never fires.
    fontWeight: {
      light: 'var(--weight-display)',
      normal: 'var(--weight-body)',
      medium: 'var(--weight-emphasis)',
      semibold: 'var(--weight-strong)',
    },
    extend: {
      fontFamily: {
        // One face on both surfaces: Instrument Sans (SIL OFL 1.1), self-hosted
        // from /fonts/ and declared at weights 400, 500 and 600 in index.css.
        // 'Instrument Sans Fallback' is the metric-matched Arial override, so
        // `font-display: swap` reflows nothing when the webfont lands. Arial
        // sits BEHIND Helvetica Neue: Arial is what actually resolves on the
        // Windows clinic machines, so the overrides are tuned to it, but it is
        // the banned body face, so it must not be the first thing anyone sees.
        sans: [
          'Outfit',
          '"Outfit Fallback"',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
        // Identifiers and code only (patient ids, endpoints, template keys).
        // Clinical figures stay in the UI face with tabular digits (R19).
        // Roboto Mono is not shipped, so this resolves to the system mono.
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },

      // TYPE — two regimes. The UI band is frozen px on a linear +2 ladder
      // (no x.5 size exists); the display band is fluid on one 1920 anchor
      // written max(Npx, N/1920*100vw), so it is pixel-stable up to 1920px and
      // proportional above it. These extend Tailwind's defaults rather than
      // replacing them, so `text-xs` (3 live uses) still resolves.
      // Each rung carries its OWN tracking (Apple's optical model): small
      // text opens up, large text closes. See index.css --track-*.
      fontSize: {
        micro: ['var(--step-micro)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-label)' }],
        label: ['var(--step-label)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-label)' }],
        // `copy`, not `body`: `body` is a colour token and Tailwind emits both
        // fontSize and textColor under `text-`, so one name cannot serve both.
        copy: ['var(--step-copy)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-copy)' }],
        'copy-lg': ['var(--step-copy-lg)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-copy-lg)' }],
        lede: ['var(--step-lede)', { lineHeight: 'var(--lead-body)', letterSpacing: 'var(--track-lede)' }],
        subhead: ['var(--step-subhead)', { lineHeight: 'var(--lead-title)', letterSpacing: 'var(--track-title)' }],
        title: ['var(--step-title)', { lineHeight: 'var(--lead-title)', letterSpacing: 'var(--track-title)' }],
        section: ['var(--step-section)', { lineHeight: 'var(--lead-title)', letterSpacing: 'var(--track-display)' }],
        display: ['var(--step-display)', { lineHeight: 'var(--lead-display)', letterSpacing: 'var(--track-display)' }],
        hero: ['var(--step-hero)', { lineHeight: 'var(--lead-display)', letterSpacing: 'var(--track-hero)' }],
      },

      letterSpacing: {
        label: 'var(--track-label)', // 12px   0
        copy: 'var(--track-copy)', // 14px   -0.011em
        'copy-lg': 'var(--track-copy-lg)', // 16px   -0.02em
        lede: 'var(--track-lede)', // 18px   -0.026em
        title: 'var(--track-title)', // 20-26px -0.022em
        display: 'var(--track-display)', // 32-44px -0.028em
        hero: 'var(--track-hero)', // 56px   -0.03em
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
        gutter: 'var(--page-gutter)', // max(24px, 2.5vw)
        stack: 'var(--space-stack)', // 20px — the one gap between cards/blocks
        bar: 'var(--bar-height)', // 56px — `top-bar` for sticky headers under the app bar
      },

      // R3 — per-page content caps (prefer the `.page .page-*` recipe, which
      // also adds the gutter).
      maxWidth: {
        container: 'var(--container-max)', // max(1320px, 68.75vw)
        'page-worklist': 'var(--page-worklist)', // 1080px
        'page-patient': 'var(--page-patient)', // 1240px
        'page-settings': 'var(--page-settings)', // 960px
      },

      borderRadius: {
        canvas: 'var(--r-canvas)', // 34px the fog window, big panels
        surface: 'var(--r-surface)', // 26px cards, tiles, overlays
        control: 'var(--r-control)', // 18px inner rows, menus
        'control-sm': 'var(--r-control-sm)', // 14px fields, compact controls
        tile: 'var(--r-tile)', // 9px icon tile
        pill: 'var(--r-pill)', // 999px every button and chip
      },

      // GLASS — the scrim, the scrolled app bar, and the Aside-derived
      // recipes (`.glass`, `.glass-overlay`, `.seg-glass`, `.field-glass`,
      // `.tile-frost`). Use the recipes: they carry the alpha floors, the
      // degradation blocks and the kill switch. Never on a card, a clinical
      // number or a risk pill, never on /checkin or /t.
      backdropBlur: {
        scrim: 'var(--blur-scrim)', // 2px
        bar: 'var(--bar-blur)', // 24px — only via .appbar
        glass: 'var(--glass-blur)', // 20px — prefer the .glass / .glass-overlay recipes
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
        // The scrolled app bar and the focused ask field. Never a card.
        float: 'var(--shadow-float)',
        // The brand-filled segmented thumb.
        thumb: 'var(--shadow-thumb)',
        // Aside's soft layered shadow (5-7% alpha): floating glass only.
        soft: 'var(--shadow-soft)',
        // Recessed well (inset). `.field` already carries it.
        well: 'var(--shadow-well)',
      },

      colors: {
        // The ramp, addressable directly for the rare case that needs a step
        // rather than a role.
        n: {
          0: 'rgb(var(--n-0) / <alpha-value>)',
          25: 'rgb(var(--n-25) / <alpha-value>)',
          50: 'rgb(var(--n-50) / <alpha-value>)',
          100: 'rgb(var(--n-100) / <alpha-value>)',
          150: 'rgb(var(--n-150) / <alpha-value>)',
          200: 'rgb(var(--n-200) / <alpha-value>)',
          300: 'rgb(var(--n-300) / <alpha-value>)',
          400: 'rgb(var(--n-400) / <alpha-value>)',
          450: 'rgb(var(--n-450) / <alpha-value>)',
          500: 'rgb(var(--n-500) / <alpha-value>)',
          600: 'rgb(var(--n-600) / <alpha-value>)',
          700: 'rgb(var(--n-700) / <alpha-value>)',
          750: 'rgb(var(--n-750) / <alpha-value>)',
          800: 'rgb(var(--n-800) / <alpha-value>)',
          850: 'rgb(var(--n-850) / <alpha-value>)',
          900: 'rgb(var(--n-900) / <alpha-value>)',
          950: 'rgb(var(--n-950) / <alpha-value>)',
        },

        // Roles. Light and dark re-index the same ramp in index.css.
        ink: 'rgb(var(--ink) / <alpha-value>)',
        // The site's accent. Dots and markers only, never text.
        lime: 'rgb(var(--lime) / <alpha-value>)',
        action: 'rgb(var(--action) / <alpha-value>)',
        'on-action': 'rgb(var(--on-action) / <alpha-value>)',
        body: 'rgb(var(--body) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        // R8 — `text-secondary`: --muted normally, --body inside `.on-tint`
        // (and .card-tint / .row-risk-high). Use it for secondary text that
        // might land on a tint.
        secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
        // The one focus-ring colour (#1976D2 light / #63A4FF dark).
        focus: 'rgb(var(--focus) / <alpha-value>)',
        // The 2px active-tab rule. Non-text only.
        'rule-active': 'rgb(var(--rule-active) / <alpha-value>)',
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
          hover: 'rgb(var(--brand-hover) / <alpha-value>)', // filled-button hover
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
          'high-tint-strong': 'rgb(var(--risk-high-tint-strong) / <alpha-value>)', // danger hover
          'med-ink': 'rgb(var(--risk-med-ink) / <alpha-value>)',
          'med-tint': 'rgb(var(--risk-med-tint) / <alpha-value>)',
          'low-ink': 'rgb(var(--risk-low-ink) / <alpha-value>)',
          'low-tint': 'rgb(var(--risk-low-tint) / <alpha-value>)',
          'missing-ink': 'rgb(var(--risk-missing-ink) / <alpha-value>)',
          'missing-tint': 'rgb(var(--risk-missing-tint) / <alpha-value>)',
        },

        // CATEGORY TILES — four non-risk hues (never red/amber/green).
        // `bg-cat-blue-tint text-cat-blue-ink`, etc. Prefer `.tile .tile-*`.
        cat: {
          'blue-ink': 'rgb(var(--cat-blue-ink) / <alpha-value>)',
          'blue-tint': 'rgb(var(--cat-blue-tint) / <alpha-value>)',
          'teal-ink': 'rgb(var(--cat-teal-ink) / <alpha-value>)',
          'teal-tint': 'rgb(var(--cat-teal-tint) / <alpha-value>)',
          'indigo-ink': 'rgb(var(--cat-indigo-ink) / <alpha-value>)',
          'indigo-tint': 'rgb(var(--cat-indigo-tint) / <alpha-value>)',
          'violet-ink': 'rgb(var(--cat-violet-ink) / <alpha-value>)',
          'violet-tint': 'rgb(var(--cat-violet-tint) / <alpha-value>)',
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
          from: { opacity: '0', transform: 'translateY(18px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          from: { backgroundPosition: '-900px 0' },
          to: { backgroundPosition: '900px 0' },
        },
        toastIn: {
          from: { opacity: '0', transform: 'translateX(30px) scale(.96)' },
          to: { opacity: '1', transform: 'none' },
        },
        modalIn: {
          from: { opacity: '0', transform: 'translateY(20px) scale(.94)' },
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
      // MOTION — 150-300ms, ease-out entering, no overshoot anywhere.
      // `spring` is back as a CRITICALLY DAMPED spring (0% overshoot, a
      // linear() curve in index.css) for positional moves only: `ease-spring
      // duration-spring`. The old 56%-overshoot cubic stays deleted. Colour
      // changes use `ease-apple duration-state`. Exits run ~65% of the enter
      // duration on ease-in. All of these collapse under reduced motion
      // because they read CSS variables.
      transitionTimingFunction: {
        smooth: 'cubic-bezier(.22,.61,.36,1)', // ease-out, entering
        exit: 'cubic-bezier(.4,0,1,1)', // ease-in, leaving
        apple: 'var(--ease-apple)', // colour / background
        bar: 'var(--ease-bar)', // app-bar material
        spring: 'var(--ease-spring)', // positional moves
      },
      transitionDuration: {
        state: 'var(--dur-state)', // 200ms
        bar: 'var(--dur-bar)', // 240ms
        spring: 'var(--dur-spring)', // 440ms
        press: 'var(--dur-press)', // 120ms
      },
      // `active:scale-press` — .97, and 1 under reduced motion.
      scale: {
        press: 'var(--press-scale)',
      },
      animation: {
        // Enter.
        rise: 'rise 600ms cubic-bezier(.2,.8,.2,1) backwards', // the site's entrance
        toastIn: 'toastIn 500ms cubic-bezier(.34,1.36,.64,1) both', // spring, like the site's notification
        modalIn: 'modalIn 350ms cubic-bezier(.34,1.36,.64,1) both', // the site's dialog
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
