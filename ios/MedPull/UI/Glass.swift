import SwiftUI

// MARK: - The glass layer
//
// THIS IS THE ONLY FILE THAT IS ALLOWED TO BE EXPRESSIVE, AND IT IS THE ONLY
// FILE THAT MAY NAME A GLASS OR MATERIAL API. Everything else in the app is
// flat: a token fill, one hairline, no shadow. If you find yourself typing
// `.glassEffect`, `.ultraThinMaterial`, `GlassEffectContainer` or
// `.buttonStyle(.glass)` in a Features file, you are writing the wrong thing —
// use one of the three helpers below instead, because each of them carries the
// pre-iOS-26 fallback and the accessibility gate that a bare call does not.
//
// FOUR HELPERS. What is here is exactly what the app is allowed to render:
//   * `mpTabBarMinimizeOnScroll()` — RootView's TabView.
//   * `mpHardScrollEdge(_:)`       — the tab roots whose clinical content
//     scrolls under system chrome: HomeView, TasksView, HealthView, and
//     TaskDetailView (inside TasksView.swift). Kept on all of them (R13).
//   * `mpGlassActionBar(isPresented:content:)` — TaskDetailView, the one
//     custom glass surface in the app.
//   * `mpGlassButton(prominent:)` — the buttons INSIDE that bar. On iOS 26
//     the commit action is `.glassProminent` tinted with the site's
//     near-black primary (`MP.action`, white label; inverted in dark), and
//     the disabled pair when disabled; any other glass button is `.glass`
//     with `.primary` ink. Pre-26 they fall back to `.mpFilled` and a
//     material capsule. System toolbars on 26 draw glass buttons inside a
//     glass bar themselves, so this is the platform idiom, not glass-on-glass
//     stacking of two independent surfaces.
// DELETED, deliberately, 2026-09-16:
//   * `mpGlass(in:)` — a free-standing glass surface. Mutually exclusive with
//     the action bar by its own contract, and no screen has a floating thing
//     that is not a bar. If one ever does, it is a design review, not a
//     one-line call.
//   * (`mpGlassButton()` was deleted here and reinstated with a prominence
//     parameter by I1 — see the list above.)
//   * `mpGlassMorph(_:in:)` and `MPGlassGroup` — morphs between two touching
//     glass shapes. The app has one glass shape per screen; there is nothing
//     for it to morph into. The reduce-motion gate they carried is recorded in
//     the bans below so it is not lost if a morph is ever proposed again.
//   * `MPGlass.enter/exit/morph/crossFade/transition(reduceMotion:)` and
//     `MPGlass.isLiquidGlass` — nothing called them. Motion belongs in
//     Theme.swift's vocabulary, not a private copy here.
//
// WHY EVERY CALL SITE IS `if #available(iOS 26, *)` GATED. The SDK is 26.5 and
// the deployment target is 17.0 (ios/project.yml). An ungated call to a 26-only
// symbol still COMPILES — Swift only requires the guard when the symbol is
// referenced in a context whose availability is lower, and a `some View`
// modifier chain inside a 17.0 target is exactly that context, so the compiler
// does flag it — but the failure mode that matters is the one where somebody
// silences the diagnostic with `@available(iOS 26, *)` on a whole view and the
// view then never renders on iOS 17-25. Gate at the modifier, not at the view.
//
// THE BUDGET, and it is small on purpose:
//   * system chrome  — the tab bar and any navigation bar. Free, on 26, and
//     the reason `mpTabBarMinimizeOnScroll()` exists.
//   * ONE custom glass surface per screen — a floating action bar, and that is
//     the only shape this file has a helper for.
//   * at most two blurred surfaces in a viewport, which the system tab bar
//     already spends one of. So: the tab bar plus one bar. That is the screen.
//
// THE BANS. These are not style preferences; each one is a measured failure.
//   * NO `Glass.clear`. Its precondition is content underneath that is dark
//     and busy enough to carry legible ink on its own; a white clinical panel
//     is neither. Apple's clear variant leans on a ~35% dimming layer, which
//     takes #FFFFFF ink on a #FFFFFF panel to 2.44:1 — still an AA failure.
//     `.regular` is the only variant this app uses.
//   * NO glass on repeating content: list cells, message bubbles, task rows,
//     cards. Glass is for a surface that FLOATS OVER content, and a row does
//     not float over anything. Repeating it also blows the two-surface budget
//     on the first scroll.
//   * NO glass carrying a clinical number. A pain score, a heart rate, a dose
//     is read once and acted on; it does not get a background that changes
//     with whatever scrolls behind it.
//   * NO tinted glass with light ink on a SURFACE. `Glass.tint(_:)` exists and
//     this file never calls it for a bar: a tinted surface takes on whatever
//     scrolls behind it, and ink on it stops being predictable. Monochrome
//     `.primary` / `.secondary` ink on untinted `.regular` is the only
//     combination that holds in both appearances.
//   * NO ungated morph. Any future `glassEffectID` / `.matchedGeometry` must
//     read `accessibilityReduceMotion`, pin `glassEffectTransition(.identity)`
//     and cross-fade instead (SwiftUI does not apply reduce-motion to explicit
//     animations). A gel-like morph is a plausible dizziness trigger, and this
//     app's user is a medicated post-operative patient.
//   * NO glass-on-glass SURFACES. `mpGlassActionBar` sits inside the safe
//     area above the tab bar, never on top of it. The only glass inside it is
//     the system glass button style via `mpGlassButton`, which is how iOS 26
//     draws a toolbar's own buttons.
//
// ONE THING THIS FILE DELIBERATELY DOES NOT READ. On iOS 26 the material
// handles `accessibilityReduceTransparency` itself, and it does it better than
// we can — Apple ships a tuned frosted variant for that setting. Reading the
// environment value in the 26 branch and swapping in our own opaque fill would
// throw that away. So the 26 branch never reads it, and the only type in this
// file that declares it is `MPLegacyGlassSurface`, which is the pre-26 path
// where `.ultraThinMaterial` is NOT self-adjusting and a real opaque fallback
// has to be written by hand.

// MARK: - Diagnostics

enum MPGlass {
    #if DEBUG
    /// Forces every helper in this file down its pre-iOS-26 branch so the
    /// fallback can be looked at on a 26 simulator — there is no iOS 17-25
    /// runtime installed on this machine, and a fallback nobody has ever seen
    /// is a fallback that does not work.
    ///
    /// DEBUG ONLY and off unless the process is launched with
    /// `MP_GLASS_LEGACY=1` in its environment:
    ///   xcrun simctl launch --console-pty <dev> com.medpull.recovery \
    ///     --setenv MP_GLASS_LEGACY=1
    /// In a release build this is a `false` literal the optimiser deletes, so
    /// shipping behaviour is identical with or without it.
    static let legacyOverride = ProcessInfo.processInfo.environment["MP_GLASS_LEGACY"] == "1"
    #else
    static let legacyOverride = false
    #endif
}

// MARK: - 1. The system tab bar (RootView only)

/// Lets the tab bar shrink to a pill as the patient scrolls down, and grow
/// back when they scroll up. One line, the best return-on-risk in the whole
/// redesign: it is the system's own glass, so it costs nothing to maintain,
/// tracks whatever Apple does next, and hands a whole tab bar's worth of
/// height back to the content.
///
/// There is NO pre-26 equivalent and this file does not fake one. The obvious
/// fake — hiding the tab bar on scroll — loses tap-to-restore: the real
/// behaviour keeps a tappable pill on screen the entire time, and a hidden bar
/// leaves a patient with no way back to the tabs except scrolling up. On
/// iOS 17-25 this is a passthrough and the tab bar simply stays put, which is
/// the correct flat behaviour, not a degraded one.
private struct MPTabBarMinimize: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26, *), !MPGlass.legacyOverride {
            content.tabBarMinimizeBehavior(.onScrollDown)
        } else {
            content
        }
    }
}

// MARK: - 2. The scroll edge effect

/// The hard-edged scroll effect under content that scrolls beneath system
/// chrome. `.hard` draws a definite boundary line rather than `.soft`'s long
/// gradient: a clinical list needs a place where the bar stops and the data
/// starts, and a soft fade over a table of numbers makes the top row look
/// washed out at exactly the moment it is being read.
///
/// AT MOST ONE PER VIEW, on the scrolling container. Two of these on nested
/// scroll views fight, and the inner one wins somewhere unpredictable.
///
/// Pre-26 this is a passthrough. iOS 17-25 has no scroll edge effect at all —
/// content scrolls under the opaque-on-scroll UIKit tab bar the way it always
/// has, which already stops at a definite edge, so nothing is lost.
private struct MPHardScrollEdge: ViewModifier {
    let edges: Edge.Set

    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26, *), !MPGlass.legacyOverride {
            content.scrollEdgeEffectStyle(.hard, for: edges)
        } else {
            content
        }
    }
}

// MARK: - 3. The glass material (private; the action bar is its only user)

/// Real Liquid Glass on iOS 26, untinted `.regular`, in the shape you name.
/// Never `.interactive()`: the only surface is a bar holding several buttons,
/// and a press response on the container makes the wrong thing feel pressed.
private struct MPGlassSurface<S: Shape>: ViewModifier {
    let shape: S
    let fallback: Material

    // No @Environment properties here, on purpose: this type is the iOS 26
    // path and it must not read accessibilityReduceTransparency. See the file
    // header. The legacy modifier below is where that value is read.

    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26, *), !MPGlass.legacyOverride {
            content.glassEffect(.regular, in: shape)
        } else {
            content.modifier(MPLegacyGlassSurface(shape: shape, fallback: fallback))
        }
    }
}

/// The pre-iOS-26 surface: a UIKit-era material, and a real opaque fill when
/// the patient has asked for less transparency.
///
/// `.ultraThinMaterial` and `.regularMaterial` do NOT become opaque under
/// Reduce Transparency the way iOS 26's glass does — they lighten a little and
/// stay see-through. So this path reads the setting and substitutes the panel
/// token outright.
///
/// Separation: the material is a FILL, so it gets no stroke — one edge, never
/// two. The opaque substitute DOES get a hairline, because `MP.panel` is
/// 1.13:1 against `MP.canvas` and without an edge a floating bar over a pale
/// screen loses its shape entirely. `MP.lineStrong` is 3.83:1 light / 5.67:1
/// dark on panel, so the edge clears the 3:1 non-text floor of WCAG 1.4.11.
private struct MPLegacyGlassSurface<S: Shape>: ViewModifier {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    let shape: S
    let fallback: Material

    @ViewBuilder func body(content: Content) -> some View {
        if reduceTransparency {
            content
                .background(MP.panel, in: shape)
                .overlay { shape.stroke(MP.lineStrong, lineWidth: 1) }
        } else {
            content.background(fallback, in: shape)
        }
    }
}

// MARK: - 4. The floating glass action bar

/// The action bar's outline: a capsule while the bar is one row (52pt
/// control + insets, with room for a scaled one-line label), a 28pt
/// continuous rounded rectangle once it is taller (the stacked layout at
/// accessibility sizes), so it never becomes a near-circle over the form.
private let mpActionBarShape = MPAdaptiveCapsule(rowCeiling: 88, stackedRadius: 28)

/// The one floating glass surface a screen is allowed: a bar pinned to the
/// bottom safe area, above the tab bar, carrying the screen's primary actions.
///
/// `safeAreaBar(edge: .bottom)` (iOS 26) is the right primitive rather than
/// `safeAreaInset`, because it tells the system this is BAR chrome: the scroll
/// edge effect, the tab bar's minimize behaviour and the keyboard all account
/// for it, and the content underneath gets the correct inset for free.
/// Pre-26 there is no such signal, so the fallback is `safeAreaInset` plus
/// `.ultraThinMaterial`, which insets the content correctly and looks like a
/// competent iOS 17 toolbar. It is not trying to look like glass.
///
/// INK IS MONOCHROME AND THAT IS LOAD-BEARING. The bar sets
/// `foregroundStyle(.primary)` and `tint(.primary)`, which override the
/// app-wide `.tint(MP.brandInk)` from MedPullApp for the bar's subtree only,
/// so a glass label never takes a colour against a ground that changes with
/// the scroll. The one exception is `mpGlassButton(prominent: true)`, which
/// re-tints ITSELF with the primary fill and draws its label on it. Use
/// `.secondary` ONLY on a glyph that should recede, never on words: system
/// secondaryLabel is 3.44:1 on the light panel (clears the 3:1 graphic floor,
/// fails 4.5:1 text). Do not reach for a token colour in here.
private struct MPGlassActionBar<Bar: View>: ViewModifier {
    let isPresented: Bool
    let alignment: HorizontalAlignment
    @ViewBuilder let bar: () -> Bar

    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26, *), !MPGlass.legacyOverride {
            content.safeAreaBar(edge: .bottom, alignment: alignment) {
                if isPresented {
                    bar()
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .modifier(MPGlassSurface(shape: mpActionBarShape, fallback: .regular))
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                        .foregroundStyle(.primary)
                        .tint(Color.primary)
                }
            }
        } else {
            content.safeAreaInset(edge: .bottom, alignment: alignment) {
                if isPresented {
                    bar()
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .modifier(MPLegacyGlassSurface(shape: mpActionBarShape, fallback: .ultraThin))
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                        .foregroundStyle(.primary)
                        .tint(Color.primary)
                }
            }
        }
    }
}

// MARK: - 5. Glass buttons (inside the action bar only)

/// iOS 26: `.glassProminent` (the near-black primary) or `.glass` (`.primary`
/// ink). iOS 17-25, or `MP_GLASS_LEGACY=1`: `.mpFilled`, or a material
/// capsule. The prominent variant sets its own tint, which wins over the
/// bar's `.tint(.primary)` and over the root `MP.brandInk` tint.
private struct MPGlassButton: ViewModifier {
    let prominent: Bool
    @Environment(\.isEnabled) private var isEnabled

    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26, *), !MPGlass.legacyOverride {
            if prominent {
                // The site's primary: near-black (light capsule in dark).
                // Disabled, the tint drops to the disabled pair, so the
                // commit action cannot look ready when it is not.
                content
                    .buttonStyle(.glassProminent)
                    .tint(isEnabled ? MP.action : MP.disabledFill)
                    .foregroundStyle(isEnabled ? MP.onAction : MP.disabledInk)
            } else {
                content
                    .buttonStyle(.glass)
                    .tint(Color.primary)
                    .foregroundStyle(.primary)
            }
        } else if prominent {
            content.buttonStyle(.mpFilled)
        } else {
            content.buttonStyle(MPMaterialButtonStyle())
        }
    }
}

/// The pre-26 non-prominent glass button: a material capsule (opaque panel
/// plus `lineStrong` under Reduce Transparency, via `MPLegacyGlassSurface`),
/// `.primary` ink, the gated press scale.
private struct MPMaterialButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        MPMaterialButtonBody(configuration: configuration)
    }
}

private struct MPMaterialButtonBody: View {
    let configuration: ButtonStyleConfiguration
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.controlSize) private var controlSize

    var body: some View {
        let compact = controlSize == .small || controlSize == .mini
        configuration.label
            .mpFont(compact ? .copyMedium : .copyLargeMedium)
            .foregroundStyle(.primary)
            .padding(.horizontal, compact ? 14 : 18)
            .frame(minHeight: compact ? 34 : 44)
            .modifier(MPLegacyGlassSurface(shape: MP.capsuleShape, fallback: .regular))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .padding(.vertical, compact ? 5 : 0)
            .contentShape(Rectangle())
            .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}

// MARK: - The call sites this file publishes


extension View {
    /// RootView's TabView, and nowhere else. See `MPTabBarMinimize`.
    func mpTabBarMinimizeOnScroll() -> some View {
        modifier(MPTabBarMinimize())
    }

    /// Exactly once per view, on the scrolling container. See `MPHardScrollEdge`.
    /// Tab roots pass `.vertical`: the top edge meets the navigation bar (or
    /// the status bar while Home's bar is hidden) and the bottom edge meets
    /// the tab bar. Keep it on Home, Tasks and Health (R13).
    func mpHardScrollEdge(_ edges: Edge.Set = .vertical) -> some View {
        modifier(MPHardScrollEdge(edges: edges))
    }

    /// The floating glass action bar — the screen's one custom glass surface.
    /// One per screen; lay the content out yourself — one row normally, and a
    /// stacked column at accessibility text sizes (the bar's outline turns
    /// from a capsule into a 28pt rounded rectangle when it grows tall) — and use
    /// `.plain` buttons with `.primary` / `.secondary` ink only. When
    /// `isPresented` is false the bar and its inset collapse to nothing, and
    /// the content view keeps its identity (the condition is inside the bar,
    /// not around the modifier).
    func mpGlassActionBar<Bar: View>(
        isPresented: Bool = true,
        alignment: HorizontalAlignment = .center,
        @ViewBuilder content: @escaping () -> Bar
    ) -> some View {
        modifier(MPGlassActionBar(isPresented: isPresented, alignment: alignment, bar: content))
    }

    /// A button inside `mpGlassActionBar`. `prominent: true` for the bar's one
    /// commit action (Liquid Glass prominent in the near-black primary on
    /// iOS 26, `.mpFilled` before); `false` for a secondary glass button. A
    /// quiet text action ("Skip this one") stays `.plain` with `.primary` ink.
    func mpGlassButton(prominent: Bool = false) -> some View {
        modifier(MPGlassButton(prominent: prominent))
    }
}
