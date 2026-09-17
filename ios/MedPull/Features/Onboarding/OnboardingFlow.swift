import SwiftUI

/// The first screen a patient sees, and the only one without a session.
///
/// A real `NavigationStack`: Welcome is the root, every step is pushed, and
/// the system back button and edge swipe replace the old "Back" text
/// buttons. The step dots ride in the bar's principal slot. Steps after
/// enrolment hide the back button (a patient must not swipe back into a form
/// that has already created their session).
///
/// Motion comes from `MPMotion` in Theme.swift. SwiftUI does NOT honour
/// `accessibilityReduceMotion` for explicit animations, so every `.animation`
/// here goes through `MPMotion.gated`. Nothing repeats: the only moments are
/// one-shot entrances on Welcome and Done.
///
/// CONTRAST (WCAG, 0.04045 threshold; scratchpad/i5contrast.py), light / dark.
/// The steps sit on the ambient wash, whose densest point is (232,242,251) /
/// (17,30,44):
///   ink on wash 16.24 / 16.84 · body 6.38 / 6.51 · muted 4.77 / 4.81 ·
///   brandInk 5.08 / 6.64 · white on the brand mark 4.60 (both)
/// Everything else sits on `panel`: muted 5.39 / 4.91, lineStrong edge 3.83 /
/// 5.67. Secondary text on the Health card (brandTint) is `body` via
/// `.mpSecondary()` (6.24 / 5.51; R8).
struct OnboardingFlow: View {
    @Environment(AppModel.self) private var app
    @State private var model = OnboardingModel()

    var body: some View {
        @Bindable var model = model
        NavigationStack(path: $model.route) {
            WelcomeStep(model: model)
                .toolbar(.hidden, for: .navigationBar)
                .navigationDestination(for: OnboardingModel.Step.self) { step in
                    destination(step)
                }
        }
        // R10: the flow's system controls include the back button now, which
        // is text, so the tint is `brandInk`. The Toggles pass `MP.brand`
        // themselves because their FILL must stay #1976D2.
        .tint(MP.brandInk)
    }

    @ViewBuilder private func destination(_ step: OnboardingModel.Step) -> some View {
        Group {
            switch step {
            case .welcome: WelcomeStep(model: model)
            case .hospital: HospitalStep(model: model)
            case .path: PathStep(model: model)
            case .identity: IdentityStep(model: model)
            case .join: JoinStep(model: model)
            case .verify: VerifyStep(model: model)
            case .health: HealthStep(model: model)
            case .wearable: WearableStep(model: model)
            case .done: DoneStep(model: model)
            }
        }
        .ambientScreen()
        .navigationTitle(Self.backTitle(step))
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(step.isPastEnrollment)
        .toolbar { dotsItem(step) }
    }

    /// The dots in the principal slot. On iOS 26 the item opts out of the
    /// shared glass capsule: the dots are their own shape, and a capsule
    /// around them would read as a button.
    @ToolbarContentBuilder private func dotsItem(_ step: OnboardingModel.Step) -> some ToolbarContent {
        if step != .done {
            if #available(iOS 26, *) {
                ToolbarItem(placement: .principal) { StepDots(current: step) }
                    .sharedBackgroundVisibility(.hidden)
            } else {
                ToolbarItem(placement: .principal) { StepDots(current: step) }
            }
        }
    }

    /// The title is never drawn (the dots take the principal slot); it is
    /// what the NEXT screen's back button says and what VoiceOver announces.
    static func backTitle(_ step: OnboardingModel.Step) -> String {
        switch step {
        case .welcome: return "Welcome"
        case .hospital: return "Hospital"
        case .path: return "Joining"
        case .identity: return "Your record"
        case .join: return "About you"
        case .verify: return "Code"
        case .health: return "Health"
        case .wearable: return "Wearables"
        case .done: return "All set"
        }
    }
}

/// Progress through the flow. Reached segments are `brand` FILL (4.29:1 light
/// / 3.99:1 dark on canvas, a graphic); the rest are `lineStrong` (3.57 /
/// 6.06), because an unreached dot still carries information. The current
/// step is the long capsule. Hidden from VoiceOver: each screen's eyebrow
/// ("Step 2 of 5") says the same thing in words.
private struct StepDots: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let current: OnboardingModel.Step
    private let shown: [OnboardingModel.Step] = [.hospital, .path, .identity, .verify, .health, .wearable]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(shown, id: \.rawValue) { s in
                MP.capsuleShape
                    .fill(s.rawValue <= current.rawValue ? MP.brand : MP.lineStrong)
                    .frame(width: s == current ? 24 : 8, height: 8)
            }
        }
        .animation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion), value: current)
        .accessibilityHidden(true)
    }
}

/// Every form step: eyebrow, a 600 display title, a lede, the content, and a
/// footer pinned above the keyboard / home indicator.
private struct StepScaffold<Content: View, Footer: View>: View {
    let eyebrow: String
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var content: () -> Content
    @ViewBuilder var footer: () -> Footer

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text(eyebrow).eyebrow()
                Text(title).title(MPSize.displayS)
                    .accessibilityAddTraits(.isHeader)
                if let subtitle {
                    // The lede: 16/400 on `body` (6.38 / 6.51 on the wash).
                    Text(subtitle).mpFont(.copyLarge).foregroundStyle(MP.body)
                        .lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                content().padding(.top, 14)
            }
            .padding(.horizontal, 22)
            .padding(.top, 8)
            .padding(.bottom, 16)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            // A step with no footer (the hospital list, the path cards)
            // gets no strip at all, so the list runs to the home indicator.
            if Footer.self != EmptyView.self {
                OnboardingFooter { footer() }
            }
        }
    }
}

/// The pinned footer. The form scrolls UNDER it, and "Skip for now" is bare
/// text, so the strip is opaque `canvas` (the wash only lives in the top
/// 320pt) with a short canvas fade above it: nothing ever reads through the
/// quiet action. The fade is decoration and carries no text.
private struct OnboardingFooter<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(spacing: 6) { content() }
            .padding(.horizontal, 22)
            .padding(.top, 10)
            .padding(.bottom, 10)
            .frame(maxWidth: .infinity)
            .background(alignment: .top) {
                MP.canvas
                    .overlay(alignment: .top) {
                        LinearGradient(colors: [MP.canvas.opacity(0), MP.canvas],
                                       startPoint: .top, endPoint: .bottom)
                            .frame(height: 18)
                            .offset(y: -18)
                            .allowsHitTesting(false)
                    }
                    .ignoresSafeArea(edges: .bottom)
                    .accessibilityHidden(true)
            }
    }
}

/// The quiet tertiary action — Skip / Send a new code. A full-width plain
/// capsule: `brandInk` (5.08 / 6.64 on the wash) with a 44pt target and a
/// soft press fill.
private struct QuietAction: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(title, action: action)
            .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
    }
}

/// A whole card as a button: the gated 0.97 press scale, nothing else.
private struct CardPressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        CardPressBody(configuration: configuration)
    }
}

private struct CardPressBody: View {
    let configuration: ButtonStyleConfiguration
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        configuration.label
            .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}

/// A feature line in the Apple "welcome sheet" pattern: a category tile, a
/// title and one sentence.
private struct FeatureRow: View {
    let icon: String
    let family: MP.Category
    let title: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            IconTile(icon, family: family, size: 44)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                Text(detail).mpFont(.copy).foregroundStyle(MP.body)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}

/// One-shot entrance: rise and fade in, staggered by `order`. Off under
/// Reduce Motion (the content is simply there).
private struct Entrance: ViewModifier {
    let shown: Bool
    let order: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        let on = shown || reduceMotion
        content
            .opacity(on ? 1 : 0)
            .offset(y: on ? 0 : 14)
            .animation(MPMotion.gated(MPMotion.layout.delay(Double(order) * 0.07),
                                      reduceMotion: reduceMotion),
                       value: shown)
    }
}

private extension View {
    func entrance(_ shown: Bool, order: Int) -> some View {
        modifier(Entrance(shown: shown, order: order))
    }
}

/// The MedPull mark: the brand FILL with a white glyph (4.60:1 both modes).
private struct BrandMark: View {
    var side: CGFloat = 64
    @ScaledMetric(relativeTo: .largeTitle) private var scale: CGFloat = 1

    var body: some View {
        let d = (side * min(scale, 1.4)).rounded()
        RoundedRectangle(cornerRadius: d * 0.28, style: .continuous)
            .fill(MP.brand)
            .frame(width: d, height: d)
            .overlay(
                Image(systemName: "waveform.path.ecg")
                    .font(.system(size: (d * 0.44).rounded(), weight: MPFont.systemWeight(for: .semibold)))
                    .foregroundStyle(MP.onBrand)
            )
            .accessibilityHidden(true)
    }
}

// MARK: - Steps

private struct WelcomeStep: View {
    @Bindable var model: OnboardingModel
    @State private var shown = false

    var body: some View {
        // A ScrollView pinned to the viewport: nothing moves at the default
        // size, and at AX5 the screen scrolls instead of clipping.
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Spacer(minLength: 32)
                    VStack(alignment: .leading, spacing: 18) {
                        HStack(spacing: 12) {
                            BrandMark(side: 56)
                            // 20/500 frozen on the UI band: a wordmark, not a title.
                            Text("MedPull").mpFont(.subheadSemibold).foregroundStyle(MP.ink)
                        }
                        .entrance(shown, order: 0)
                        .accessibilityElement(children: .combine)

                        VStack(alignment: .leading, spacing: 10) {
                            Text("Hi there.\nLet's get you set up.")
                                .title(MPSize.displayM)
                                .accessibilityAddTraits(.isHeader)
                            Text("Your hospital, your watch and your care team, together in one place. It takes about two minutes.")
                                .mpFont(.lede).foregroundStyle(MP.body).lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .entrance(shown, order: 1)

                        VStack(alignment: .leading, spacing: 18) {
                            FeatureRow(icon: "figure.walk", family: .teal,
                                       title: "Your everyday signals",
                                       detail: "Steps, sleep and heart rate flow in from Apple Health or your wearable. No typing.")
                                .entrance(shown, order: 2)
                            FeatureRow(icon: "text.bubble.fill", family: .blue,
                                       title: "Quick check-ins",
                                       detail: "Answer a question by text or right here. A few taps, not a form.")
                                .entrance(shown, order: 3)
                            FeatureRow(icon: "person.2.fill", family: .indigo,
                                       title: "A care team that sees it",
                                       detail: "Your nurses and doctors see the same picture you do, and reach out when something changes.")
                                .entrance(shown, order: 4)
                        }
                        .padding(.top, 10)
                    }
                    .padding(.horizontal, 24)
                    Spacer(minLength: 28)
                    VStack(spacing: 12) {
                        PrimaryButton(title: "Get started", icon: "arrow.right") { model.go(.hospital) }
                        // THE DISCLAIMER: `muted` (4.77 / 4.81 at the wash's
                        // densest; this line sits well below it, on canvas,
                        // 5.03 / 5.24). Never `faint`.
                        Text("Monitoring signals for your care team — not a diagnosis.")
                            .mpFont(.label).foregroundStyle(MP.muted)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity)
                    }
                    .entrance(shown, order: 5)
                    .padding(.horizontal, 22).padding(.bottom, 18)
                }
                .frame(minWidth: proxy.size.width, minHeight: proxy.size.height, alignment: .leading)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .ambientScreen(height: 420)
        .onAppear { shown = true }
    }
}

private struct HospitalStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    var body: some View {
        StepScaffold(eyebrow: "Step 1 of 5", title: "Which hospital are you with?",
                     subtitle: "Your care team there will see what you share. You can pick by name, system or city.") {
            VStack(spacing: 14) {
                SearchCapsule(text: $model.hospitalQuery, placeholder: "Search hospitals")
                if model.hospitals.isEmpty {
                    if let error = model.error { ErrorBanner(text: error) } else { ProgressView().frame(maxWidth: .infinity).padding() }
                } else if model.filteredHospitals.isEmpty {
                    Card {
                        EmptyRow(icon: "building.2", title: "No hospitals match",
                                 detail: "Try the city, or just part of the name.")
                    }
                } else {
                    Card(padding: 0) {
                        VStack(spacing: 0) {
                            ForEach(model.filteredHospitals) { h in
                                Button {
                                    model.hospital = h
                                    model.candidates = []
                                    model.selected = nil
                                    model.go(.path)
                                } label: {
                                    HStack(spacing: 14) {
                                        IconTile("building.2.fill", family: .blue)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(h.name).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                                .multilineTextAlignment(.leading)
                                            Text([h.system, "\(h.city), \(h.state)"].compactMap { $0 }.joined(separator: MP.dot))
                                                .mpFont(.label).foregroundStyle(MP.muted)
                                                .multilineTextAlignment(.leading)
                                        }
                                        Spacer(minLength: 8)
                                        Image(systemName: "chevron.right")
                                            .font(.systemGlyphs(13, weight: .semibold))
                                            .foregroundStyle(MP.muted)
                                            .accessibilityHidden(true)
                                    }
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 12)
                                }
                                .buttonStyle(.mpRow)
                                if h.id != model.filteredHospitals.last?.id { InsetDivider() }
                            }
                        }
                    }
                    .clipShape(MP.surfaceShape)
                }
            }
        } footer: {
            EmptyView()
        }
        .task { await model.loadHospitals(api: app.api) }
    }
}

/// A capsule search field. Not `.searchable`: the system search field's
/// placeholder is `placeholderText`, about 1.7:1, and cannot be recoloured,
/// so this draws the same shape with a `muted` prompt (5.39 / 4.91 on panel)
/// and keeps the `lineStrong` edge an empty field needs (3.83 / 5.67).
private struct SearchCapsule: View {
    @Binding var text: String
    let placeholder: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.systemGlyphs(15, weight: .medium))
                .foregroundStyle(MP.muted)
                .accessibilityHidden(true)
            TextField(placeholder, text: $text,
                      prompt: Text(placeholder).foregroundStyle(MP.muted))
                .mpFont(.copyLarge)
                .foregroundStyle(MP.ink)
                .autocorrectionDisabled()
                .submitLabel(.search)
            if !text.isEmpty {
                Button { text = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.systemGlyphs(17, weight: .regular))
                        .foregroundStyle(MP.muted)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel("Clear search")
                .padding(.trailing, -12)
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 48)
        .background(MP.capsuleShape.fill(MP.panel))
        .overlay(MP.capsuleShape.strokeBorder(MP.lineStrong, lineWidth: 1))
    }
}

private struct PathStep: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        StepScaffold(eyebrow: "Step 2 of 5", title: "How are you joining?",
                     subtitle: "\(model.hospital?.name ?? "Your hospital") looks after people with and without a surgery. Either way, what your care team sees is what you see here.") {
            VStack(spacing: 12) {
                pathCard(icon: "person.text.rectangle.fill", family: .blue,
                         title: "My care team set me up",
                         detail: "The clinic already has a record for you, or you've used MedPull before. We'll find it so their messages reach this phone.") {
                    model.choose(.findRecord)
                }
                pathCard(icon: "sparkles", family: .violet,
                         title: "I'm new here",
                         detail: "Start a record now, with or without a surgery. Your activity, sleep and vitals build a picture your care team can see.") {
                    model.choose(.joinGeneral)
                }
            }
        } footer: {
            EmptyView()
        }
    }

    private func pathCard(icon: String, family: MP.Category, title: String, detail: String,
                          action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    IconTile(icon, family: family, size: 44)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).mpFont(.lede.weight(.semibold)).foregroundStyle(MP.ink)
                        Text(detail).mpFont(.copy).mpSecondary().lineSpacing(2)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right")
                        .font(.systemGlyphs(13, weight: .semibold))
                        .foregroundStyle(MP.muted)
                        .padding(.top, 14)
                        .accessibilityHidden(true)
                }
            }
            .contentShape(MP.surfaceShape)
        }
        .buttonStyle(CardPressStyle())
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
    }
}

private struct IdentityStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @FocusState private var focus: Field?
    enum Field { case name, phone }

    var body: some View {
        StepScaffold(eyebrow: "Step 3 of 5", title: "Let's find your record",
                     subtitle: "Your name as it's on file at \(model.hospital?.name ?? "the hospital"), and a mobile number we can text. If the clinic already has your number, that finds you on its own.") {
            VStack(spacing: 14) {
                // Every placeholder carries a `muted` prompt: SwiftUI's own
                // placeholder colour is 1.72:1.
                TextField("Full name", text: $model.name,
                          prompt: Text("Full name").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .textContentType(.name).autocorrectionDisabled()
                    .focused($focus, equals: .name)
                    .submitLabel(.next)
                    .onSubmit { focus = .phone }
                TextField("Mobile number", text: $model.phone,
                          prompt: Text("Mobile number").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .textContentType(.telephoneNumber).keyboardType(.phonePad)
                    .focused($focus, equals: .phone)

                if model.canSearch {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 8) {
                            // Sentence case: "Step 3 of 5" spends the
                            // screen's one uppercase element.
                            Text(model.searching ? "Looking you up…" : model.candidates.isEmpty ? "No match yet" : "Is this you?")
                                .mpFont(.labelMedium).foregroundStyle(MP.muted)
                            if model.searching { ProgressView().controlSize(.small) }
                        }
                        ForEach(model.candidates) { c in
                            candidateRow(c)
                        }
                        if !model.searching && model.candidates.isEmpty {
                            Text("Check the spelling, or ask the clinic which name they used. If they have your number, typing it above finds you too.")
                                .mpFont(.copy).foregroundStyle(MP.body)
                                .fixedSize(horizontal: false, vertical: true)
                            Button("Not on the list? Join as a new patient") {
                                model.choose(.joinGeneral)
                            }
                            .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                        }
                    }
                    .padding(.top, 6)
                }
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: model.selected == nil ? "Find my record" : "That's me — continue",
                          loading: model.loading, disabled: !model.canEnroll) {
                Task { await model.enroll(api: app.api, app: app) }
            }
        }
        .task(id: "\(model.name)|\(model.phone)") {
            try? await Task.sleep(for: .milliseconds(350))
            guard !Task.isCancelled else { return }
            await model.search(api: app.api)
        }
        .onAppear { focus = .name }
        .mpErrorFeedback(model.error)
    }

    private func candidateRow(_ c: Candidate) -> some View {
        let isSelected = model.selected?.id == c.id
        return Button { model.selected = c } label: {
            HStack(spacing: 12) {
                // Unselected: `lineStrong` ring (3.83 / 5.67 on panel), the
                // only cue the control exists. Selected: `brandInk` on the
                // tint it then sits on (4.96 / 5.62).
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.systemGlyphs(22, weight: .regular))
                    .foregroundStyle(isSelected ? MP.brandInk : MP.lineStrong)
                    .contentTransition(.symbolEffect(.replace))
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.displayName).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    // `body`: the ground becomes `brandTint` when selected,
                    // where `muted` is 4.07 dark (R8). 6.24 / 5.51 there.
                    Text("\(c.procedureDisplay)\(MP.dot)\(c.surgeryMonth)")
                        .mpFont(.label).foregroundStyle(MP.body)
                }
                Spacer(minLength: 8)
                if c.phoneMatch { StatusPill(text: "Number matches", tone: .low) }
            }
            .padding(14)
            // Selection changes the fill AND the stroke colour, never colour
            // alone (the glyph changes too), at a constant 1pt width.
            .background(MP.surfaceShape.fill(isSelected ? MP.brandTint : MP.panel))
            .overlay(MP.surfaceShape.strokeBorder(isSelected ? MP.brand : MP.line, lineWidth: 1))
            .contentShape(MP.surfaceShape)
        }
        .buttonStyle(CardPressStyle())
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .sensoryFeedback(.selection, trigger: isSelected) { _, new in new }
    }
}

private struct VerifyStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @FocusState private var focused: Bool

    var body: some View {
        StepScaffold(eyebrow: "Step 4 of 5", title: "Check your texts",
                     subtitle: "We sent a code to \(model.phoneMasked ?? "your number"). It's good for 10 minutes.") {
            VStack(spacing: 14) {
                // `FieldStyle` sets the font on the configuration, so a
                // monospaced override here would be inert.
                TextField("6-digit code", text: $model.code,
                          prompt: Text("6-digit code").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .keyboardType(.numberPad).textContentType(.oneTimeCode)
                    .focused($focused)
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: "Verify", loading: model.loading, disabled: model.code.count < 4) {
                Task { await model.verify(api: app.api, app: app) }
            }
            QuietAction(title: "Send a new code") { Task { await model.resend(api: app.api, app: app) } }
        }
        .onAppear { focused = true }
        .mpErrorFeedback(model.error)
    }
}

private struct HealthStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @State private var working = false
    @State private var failure: String?

    private let reads: [(icon: String, family: MP.Category, text: String)] = [
        ("figure.walk", .teal, "Steps, distance and stairs"),
        ("bed.double.fill", .indigo, "Sleep and resting heart rate"),
        ("figure.walk.motion", .blue, "Walking speed, step length and steadiness"),
        ("flame.fill", .violet, "Workouts and exercise minutes"),
    ]

    var body: some View {
        StepScaffold(eyebrow: "Step 5 of 5", title: "Connect Apple Health",
                     subtitle: "One tap, and your activity, sleep and heart data fill in on their own. Nothing to type.") {
            VStack(spacing: 12) {
                Card(padding: 0, tint: true) {
                    VStack(alignment: .leading, spacing: 0) {
                        CardHeader("What we read")
                        ForEach(Array(reads.enumerated()), id: \.offset) { i, r in
                            HStack(spacing: 14) {
                                // On the brand tint a blue tile would vanish,
                                // so the tiles sit on a panel chip here.
                                IconTile(r.icon, family: r.family)
                                    .background(MP.tileShape.fill(MP.panel).padding(-2))
                                Text(r.text).mpFont(.copy).foregroundStyle(MP.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 0)
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 9)
                            .accessibilityElement(children: .combine)
                            if i < reads.count - 1 { InsetDivider() }
                        }
                        // `.mpSecondary()` is `body` on this tint (R8).
                        Text("We never write to Health. Turn any type off on the next screen and we simply won't read it.")
                            .mpFont(.label).mpSecondary()
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16)
                            .padding(.top, 8)
                            .padding(.bottom, 16)
                    }
                }
                if !(app.me?.features.appleHealth ?? true) {
                    ErrorBanner(text: "This server isn't connected to Junction yet, so Health data has nowhere to go. You can skip and connect later.")
                }
                if let failure { ErrorBanner(text: failure) }
                if app.health.state == .connected {
                    HStack(spacing: 10) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.systemGlyphs(20, weight: .semibold))
                            .foregroundStyle(MP.riskLow)
                            .accessibilityHidden(true)
                        Text("Connected. Your first sync is running.")
                            .mpFont(.copyMedium).foregroundStyle(MP.ink)
                    }
                    .padding(.top, 4)
                    .transition(.opacity)
                }
            }
        } footer: {
            if app.health.state == .connected {
                PrimaryButton(title: "Continue", icon: "arrow.right") { model.go(.wearable) }
            } else {
                PrimaryButton(title: "Connect Apple Health", icon: "heart.fill", loading: working,
                              disabled: !(app.me?.features.appleHealth ?? false)) {
                    working = true
                    failure = nil
                    Task {
                        let ok = await app.connectAppleHealth()
                        working = false
                        if !ok {
                            if case .failed(let m) = app.health.state { failure = m }
                            else if app.health.state == .unavailable { failure = "Health isn't available on this device." }
                        }
                    }
                }
                QuietAction(title: "Skip for now") { model.go(.wearable) }
            }
        }
        .mpCompletionFeedback(app.health.state == .connected)
        .mpErrorFeedback(failure)
    }
}

private struct WearableStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @State private var link: URL?
    @State private var working = false
    @State private var failure: String?

    private let brands = ["Oura", "Garmin", "WHOOP", "Fitbit", "Withings", "Polar"]

    var body: some View {
        StepScaffold(eyebrow: "Almost done", title: "Wear something else?",
                     subtitle: "Sign in once and it syncs on its own. Apple Watch is already covered by Health.") {
            VStack(alignment: .leading, spacing: 12) {
                // Non-interactive tags: 14/500 `body` on `panel` (7.22 /
                // 6.65) with a `line` edge, so they read as labels, not chips.
                BrandFlow(spacing: 8) {
                    ForEach(brands, id: \.self) { b in
                        Text(b).mpFont(.copyMedium).foregroundStyle(MP.body)
                            .padding(.horizontal, 14).padding(.vertical, 8)
                            .background(MP.capsuleShape.fill(MP.panel))
                            .overlay(MP.capsuleShape.strokeBorder(MP.line, lineWidth: 1))
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Works with \(brands.joined(separator: ", "))")
                if let failure { ErrorBanner(text: failure) }
            }
        } footer: {
            PrimaryButton(title: "Add a wearable", icon: "link", loading: working,
                          disabled: !(app.me?.features.appleHealth ?? false)) {
                working = true
                Task {
                    defer { working = false }
                    do { link = URL(string: try await app.api.wearableLink().linkUrl) }
                    catch { failure = error.localizedDescription }
                }
            }
            QuietAction(title: app.health.state == .connected ? "Not now" : "Skip") { model.go(.done) }
        }
        .sheet(item: $link) { url in
            SafariView(url: url).ignoresSafeArea()
        }
        .onOpenURL { url in
            // medpull://wearables/connected from Junction's hosted page.
            if url.host == "wearables" {
                link = nil
                Task { await app.refreshWearables(force: true) }
                model.go(.done)
            }
        }
        .mpErrorFeedback(failure)
    }
}

/// A wrapping row of tags (iOS 16 `Layout`), so six brand names never
/// overflow a narrow or AX-sized screen.
private struct BrandFlow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let height = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(rows.count - 1, 0))
        let width = rows.map(\.width).max() ?? 0
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for i in row.indices {
                let size = subviews[i].sizeThatFits(.init(width: bounds.width, height: nil))
                subviews[i].place(at: CGPoint(x: x, y: y), proposal: .init(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row { var indices: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = [Row()]
        for i in subviews.indices {
            let size = subviews[i].sizeThatFits(.init(width: width, height: nil))
            let needed = rows[rows.count - 1].indices.isEmpty ? size.width : rows[rows.count - 1].width + spacing + size.width
            if needed > width, !rows[rows.count - 1].indices.isEmpty {
                rows.append(Row())
            }
            var r = rows[rows.count - 1]
            r.width = r.indices.isEmpty ? size.width : r.width + spacing + size.width
            r.height = max(r.height, size.height)
            r.indices.append(i)
            rows[rows.count - 1] = r
        }
        return rows
    }
}

private struct DoneStep: View {
    @Environment(AppModel.self) private var app
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Bindable var model: OnboardingModel
    @State private var shown = false
    @ScaledMetric(relativeTo: .largeTitle) private var discSide: CGFloat = 88

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Spacer(minLength: 24)
                    VStack(alignment: .leading, spacing: 18) {
                        // The brand disc with a white check (4.60:1): a
                        // celebration, not a risk state, so no risk green. It
                        // bounces ONCE on arrival (off under Reduce Motion).
                        let d = min(discSide, 132)
                        Circle()
                            .fill(MP.brand)
                            .frame(width: d, height: d)
                            .overlay(
                                Image(systemName: "checkmark")
                                    .font(.system(size: (d * 0.42).rounded(), weight: MPFont.systemWeight(for: .semibold)))
                                    .foregroundStyle(MP.onBrand)
                                    .symbolEffect(.bounce, options: .nonRepeating, value: reduceMotion ? false : shown)
                            )
                            .scaleEffect(shown || reduceMotion ? 1 : 0.6)
                            .opacity(shown || reduceMotion ? 1 : 0)
                            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion), value: shown)
                            .accessibilityHidden(true)

                        VStack(alignment: .leading, spacing: 10) {
                            Text("You're all set, \(app.me?.patient.firstName ?? "there").")
                                .title(MPSize.displayM)
                                .accessibilityAddTraits(.isHeader)
                            Text("Welcome to MedPull. Here's what happens next.")
                                .mpFont(.lede).foregroundStyle(MP.body)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .entrance(shown, order: 1)

                        VStack(alignment: .leading, spacing: 18) {
                            if app.me?.patient.isRecovery == true {
                                FeatureRow(icon: "message.fill", family: .blue,
                                           title: "We'll text you",
                                           detail: "When a task is ready, answer right in Messages or open the app. Either way your care team sees it.")
                                    .entrance(shown, order: 2)
                                FeatureRow(icon: "checklist", family: .teal,
                                           title: "Small steps each day",
                                           detail: "Exercises, walks and quick check-ins, sized for where you are in your recovery.")
                                    .entrance(shown, order: 3)
                            } else {
                                FeatureRow(icon: "chart.line.uptrend.xyaxis", family: .teal,
                                           title: "Your picture fills in",
                                           detail: "Your portfolio grows as your data arrives. Give it a day or two.")
                                    .entrance(shown, order: 2)
                                FeatureRow(icon: "message.fill", family: .blue,
                                           title: "We'll text you",
                                           detail: "When your care team asks for something, answer by text or right here in the app.")
                                    .entrance(shown, order: 3)
                            }
                            FeatureRow(icon: "waveform", family: .indigo,
                                       title: "Talk any time",
                                       detail: "Tell MedPull how you're doing in your own words. Anything important goes to your care team.")
                                .entrance(shown, order: 4)
                        }
                        .padding(.top, 6)
                    }
                    .padding(.horizontal, 24)
                    Spacer(minLength: 28)
                    PrimaryButton(title: "Open MedPull", icon: "arrow.right") { app.enterHome() }
                        .padding(.horizontal, 22).padding(.bottom, 18)
                        .entrance(shown, order: 5)
                }
                .frame(minWidth: proxy.size.width, minHeight: proxy.size.height, alignment: .leading)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .onAppear { shown = true }
        .sensoryFeedback(.success, trigger: shown) { old, new in !old && new }
    }
}

private struct JoinStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @State private var hasDOB = false
    @State private var dob = Calendar.current.date(byAdding: .year, value: -40, to: Date())!

    private var surgical: Bool { model.path == .joinAfterSurgery }
    private var surgicalBinding: Binding<Bool> {
        Binding(get: { model.path == .joinAfterSurgery },
                set: { model.path = $0 ? .joinAfterSurgery : .joinGeneral })
    }

    var body: some View {
        StepScaffold(eyebrow: "Step 3 of 5", title: "Tell us about you",
                     subtitle: "This starts your record at \(model.hospital?.name ?? "the hospital"). Had an operation? Add it and we'll follow your recovery. If not, we'll follow your everyday signals.") {
            VStack(spacing: 14) {
                TextField("Full name", text: $model.name,
                          prompt: Text("Full name").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).textContentType(.name).autocorrectionDisabled()
                TextField("Mobile number", text: $model.phone,
                          prompt: Text("Mobile number").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).textContentType(.telephoneNumber).keyboardType(.phonePad)

                // The two switches share one grouped card, the Settings way.
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        Toggle(isOn: $hasDOB) {
                            Label {
                                Text("Add date of birth").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            } icon: {
                                IconTile("calendar", family: .indigo)
                            }
                            .labelStyle(TileLabelStyle())
                        }
                        .tint(MP.brand)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                        .onChange(of: hasDOB) { _, on in model.dateOfBirth = on ? dob : nil }
                        if hasDOB {
                            InsetDivider()
                            // The value chip is UIKit-drawn and stays system.
                            DatePicker("Date of birth", selection: $dob, in: ...Date(), displayedComponents: .date)
                                .datePickerStyle(.compact)
                                .mpFont(.copyLarge)
                                .foregroundStyle(MP.ink)
                                .padding(.leading, 60).padding(.trailing, 16).padding(.vertical, 6)
                                .onChange(of: dob) { _, d in model.dateOfBirth = d }
                        }
                        InsetDivider()
                        Toggle(isOn: surgicalBinding) {
                            Label {
                                Text("I'm recovering from an operation").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            } icon: {
                                IconTile("cross.case.fill", family: .violet)
                            }
                            .labelStyle(TileLabelStyle())
                        }
                        .tint(MP.brand)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                    }
                }
                if surgical {
                    VStack(alignment: .leading, spacing: 10) {
                        // Sentence case, same uppercase budget as IdentityStep.
                        Text("Which operation?").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        if model.procedures.isEmpty {
                            ProgressView().controlSize(.small)
                        } else {
                            FlowProcedures(procedures: model.procedures, selected: $model.procedure)
                        }
                        DatePicker("Surgery date", selection: $model.surgeryDate, in: ...Date(), displayedComponents: .date)
                            .datePickerStyle(.compact)
                            .mpFont(.copyLargeMedium)
                            .foregroundStyle(MP.ink)
                            .padding(.top, 4)
                    }
                    .padding(.top, 4)
                    .transition(.opacity)
                }
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: surgical ? "Create my record" : "Join \(model.hospital?.name.split(separator: " ").first.map(String.init) ?? "hospital")",
                          loading: model.loading, disabled: !model.canJoin) {
                Task { await model.join(api: app.api, app: app) }
            }
        }
        .task(id: surgical) { if surgical { await model.loadProcedures(api: app.api) } }
        .mpErrorFeedback(model.error)
    }
}

/// Tile + title, vertically centred, 14pt apart (the InsetDivider indent).
private struct TileLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 14) {
            configuration.icon
            configuration.title
        }
    }
}

private struct FlowProcedures: View {
    let procedures: [Procedure]
    @Binding var selected: Procedure?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let columns = dynamicTypeSize.isAccessibilitySize
            ? [GridItem(.flexible())]
            : [GridItem(.flexible()), GridItem(.flexible())]
        LazyVGrid(columns: columns, spacing: 8) {
            ForEach(procedures) { p in
                Chip(label: p.label, selected: selected?.id == p.id) {
                    selected = (selected?.id == p.id) ? nil : p
                }
            }
        }
    }
}

extension URL: @retroactive Identifiable {
    public var id: String { absoluteString }
}
