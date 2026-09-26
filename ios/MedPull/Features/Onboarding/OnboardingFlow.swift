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
/// The look is medpull.org's: the fog canvas (taller on Welcome and Done),
/// light display titles, gradient glyph tiles, glass cards and the
/// near-black primary with its lime dot. Text on the fog is `ink` or `body`
/// (5.0 or better at the fog's strongest point); secondary text on glass is
/// `muted`.
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
        // The flow's system controls include the back button, which is
        // text, so the tint is the sage text colour. The Toggles pass the
        // sage fill themselves.
        .tint(MP.brandInk)
        .onAppear { jumpForVerification() }
    }

    /// Simulator verification only: `MP_ONBOARDING_STEP=goals` (or mode,
    /// personalAbout, plan) opens the flow on that step of the personal
    /// path so a screenshot needs no taps. Debug builds only.
    private func jumpForVerification() {
        #if DEBUG
        guard let raw = AppConfig.debugFlag("MP_ONBOARDING_STEP") else { return }
        model.name = "Ada Runner"
        model.phone = "5125559001"
        switch raw {
        case "mode": model.route = [.mode]
        case "consent": model.path = .personal; model.route = [.mode, .consent]
        case "login": model.route = [.login]
        case "personalAbout": model.path = .personal; model.route = [.mode, .consent, .personalAbout]
        case "goals": model.path = .personal; model.goal = "performance"; model.sport = "running"
            model.email = "ada@example.com"; model.password = "run-fast-sleep-well"
            model.route = [.mode, .consent, .personalAbout, .goals]
        default: break
        }
        #endif
    }

    @ViewBuilder private func destination(_ step: OnboardingModel.Step) -> some View {
        Group {
            switch step {
            case .welcome: WelcomeStep(model: model)
            case .mode: ModeStep(model: model)
            case .consent: ConsentStep(model: model)
            case .login: LoginStep(model: model)
            case .hospital: HospitalStep(model: model)
            case .path: PathStep(model: model)
            case .identity: IdentityStep(model: model)
            case .join: JoinStep(model: model)
            case .personalAbout: PersonalAboutStep(model: model)
            case .goals: GoalsStep(model: model)
            case .verify: VerifyStep(model: model)
            case .plan: PlanStep(model: model)
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
        if step != .done && step != .mode && step != .login {
            if #available(iOS 26, *) {
                ToolbarItem(placement: .principal) { StepDots(current: step, shown: model.stepsShown) }
                    .sharedBackgroundVisibility(.hidden)
            } else {
                ToolbarItem(placement: .principal) { StepDots(current: step, shown: model.stepsShown) }
            }
        }
    }

    /// The title is never drawn (the dots take the principal slot); it is
    /// what the NEXT screen's back button says and what VoiceOver announces.
    static func backTitle(_ step: OnboardingModel.Step) -> String {
        switch step {
        case .welcome: return "Welcome"
        case .mode: return "How you’ll use MedPull"
        case .consent: return "Consent"
        case .login: return "Sign in"
        case .hospital: return "Hospital"
        case .path: return "Joining"
        case .identity: return "Your record"
        case .join: return "About you"
        case .personalAbout: return "About you"
        case .goals: return "Your goal"
        case .verify: return "Code"
        case .plan: return "Your plan"
        case .health: return "Health"
        case .wearable: return "Wearables"
        case .done: return "All set"
        }
    }
}

/// Progress through the flow. Reached segments are ink (the site's current
/// item); the rest are `lineStrong` (3:1 or better), because an unreached dot
/// still carries information. The current step is the long capsule. Hidden
/// from VoiceOver: each screen's eyebrow ("Step 2 of 5") says the same thing
/// in words.
private struct StepDots: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let current: OnboardingModel.Step
    let shown: [OnboardingModel.Step]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(shown, id: \.rawValue) { s in
                MP.capsuleShape
                    .fill(s.rawValue <= current.rawValue ? MP.ink : MP.lineStrong.opacity(0.6))
                    .frame(width: s == current ? 24 : 8, height: 8)
            }
        }
        .animation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion), value: current)
        .accessibilityHidden(true)
    }
}

/// Every form step: eyebrow, a light display title, a lede, the content, and
/// a footer pinned above the keyboard / home indicator.
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
                    // The lede: 16/400 on `body`.
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
/// text, so the strip is opaque `canvas` with a short canvas fade above it:
/// nothing ever reads through the quiet action.
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
/// sage capsule with a 44pt target and a soft press fill.
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

/// The MedPull mark on the site's white app-icon tile, lifted. The tile is
/// white in both modes, like the app icon.
private struct BrandMark: View {
    var side: CGFloat = 64
    @ScaledMetric(relativeTo: .largeTitle) private var scale: CGFloat = 1
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        let d = (side * min(scale, 1.4)).rounded()
        let shape = RoundedRectangle(cornerRadius: d * 0.28, style: .continuous)
        shape
            .fill(Color.white)
            .frame(width: d, height: d)
            .overlay(
                Image("MedPullMark")
                    .resizable()
                    .scaledToFit()
                    .padding(d * 0.17)
            )
            .overlay(shape.strokeBorder(contrast == .increased ? MP.line : Color.black.opacity(0.08), lineWidth: 0.5))
            .shadow(color: Color.black.opacity(0.18), radius: 14, x: 0, y: 8)
            .accessibilityHidden(true)
    }
}

/// The site's hero badge above the Welcome headline: a glass capsule with a
/// lime dot and ink text (17 or better on the glass).
private struct SkyBadge: View {
    let text: String

    var body: some View {
        HStack(spacing: 8) {
            LimeDot(size: 7)
            Text(text)
                .mpFont(.copyMedium)
                .foregroundStyle(MP.ink)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .glassSurface(MP.capsuleShape, solid: true)
    }
}

/// The Welcome and Done backdrop: the site's hero canvas, taller — soft
/// drifting colour fog, grain and the dot grid (see `FogBackground`). Text
/// on it is `ink` or `body` only.
private struct OnboardingSky: View {
    var body: some View {
        FogBackground(height: 760)
            .allowsHitTesting(false)
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
                        HStack(spacing: 14) {
                            BrandMark(side: 60)
                            // 20/500 on the UI band: a wordmark, not a title.
                            Text("MedPull").mpFont(.subheadMedium).kerning(-0.6).foregroundStyle(MP.ink)
                        }
                        .entrance(shown, order: 0)
                        .accessibilityElement(children: .combine)

                        VStack(alignment: .leading, spacing: 12) {
                            HStack(spacing: 8) {
                                SkyBadge(text: "Recovery and performance, from your wearable")
                                StatusPill(text: "Beta", tone: .med)
                            }
                            .padding(.bottom, 2)
                            Text("Hi there.\nLet’s get you set up.")
                                .title(MPSize.displayM)
                                .accessibilityAddTraits(.isHeader)
                            Text("Your watch, read properly: with your care team after an operation, or on your own for training, sleep and everyday health. About two minutes.")
                                .mpFont(.lede).foregroundStyle(MP.body).lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .entrance(shown, order: 1)

                        VStack(alignment: .leading, spacing: 18) {
                            FeatureRow(icon: "figure.walk", family: .teal,
                                       title: "Your everyday signals",
                                       detail: "Steps, sleep, HRV and heart rate flow in from Apple Health or your wearable. No typing.")
                                .entrance(shown, order: 2)
                            FeatureRow(icon: "gauge.with.dots.needle.67percent", family: .indigo,
                                       title: "Readouts that mean something",
                                       detail: "Readiness, training load, sleep debt and more, against your own baselines, with the reasons.")
                                .entrance(shown, order: 3)
                            FeatureRow(icon: "person.2.fill", family: .blue,
                                       title: "With a care team, or on your own",
                                       detail: "Recovering from surgery? Your clinicians see the same picture. Training? Your coach is the app.")
                                .entrance(shown, order: 4)
                        }
                        .padding(.top, 10)
                    }
                    .padding(.horizontal, 24)
                    Spacer(minLength: 28)
                    VStack(spacing: 12) {
                        PrimaryButton(title: "Get started", icon: "arrow.right") { model.go(.mode) }
                        Button("Already have an account? Sign in") { model.go(.login) }
                            .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
                        // THE DISCLAIMER: `body`, not `muted`, because at
                        // accessibility sizes it scrolls up over the fog.
                        Text("Monitoring signals for your care team — not a diagnosis.")
                            .mpFont(.label).foregroundStyle(MP.body)
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
        .background { OnboardingSky() }
        .onAppear { shown = true }
    }
}

/// The fork: a hospital's patient, or a subscriber on their own.
private struct ModeStep: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        StepScaffold(eyebrow: "First", title: "How will you use MedPull?",
                     subtitle: "Both read the same watch. One shares the picture with your care team; the other keeps it to you, with readouts built for training, sleep and recovery.") {
            VStack(spacing: 12) {
                modeCard(icon: "building.2.fill", family: .blue,
                         title: "With my care team",
                         detail: "Your hospital set you up, or you’re recovering from an operation they follow. Free with your clinic.") {
                    model.path = .joinGeneral
                    model.go(model.consent == nil ? .consent : .hospital)
                }
                modeCard(icon: "sparkles", family: .teal,
                         title: "On my own",
                         detail: "MedPull Personal: readiness, training load, sleep debt and a coach that knows your numbers. 14 days free, then a subscription.") {
                    model.path = .personal
                    model.candidates = []
                    model.selected = nil
                    model.go(model.consent == nil ? .consent : .personalAbout)
                }
            }
        } footer: {
            EmptyView()
        }
    }

    private func modeCard(icon: String, family: MP.Category, title: String, detail: String,
                          action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    IconTile(icon, family: family, size: 44)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).mpFont(.ledeMedium).foregroundStyle(MP.ink)
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
                         detail: "The clinic already has a record for you, or you’ve used MedPull before. We’ll find it so their messages reach this phone.") {
                    model.choose(.findRecord)
                }
                pathCard(icon: "sparkles", family: .violet,
                         title: "I’m new here",
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
                        Text(title).mpFont(.ledeMedium).foregroundStyle(MP.ink)
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
        StepScaffold(eyebrow: "Step 3 of 5", title: "Let’s find your record",
                     subtitle: "Your name as it’s on file at \(model.hospital?.name ?? "the hospital"), and a mobile number we can text. If the clinic already has your number, that finds you on its own.") {
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
            PrimaryButton(title: model.selected == nil ? "Find my record" : "That’s me — continue",
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
                // Unselected: `lineStrong` ring, the only cue the control
                // exists. Selected: an ink check (the site's selected card).
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.systemGlyphs(22, weight: .regular))
                    .foregroundStyle(isSelected ? MP.ink : MP.lineStrong)
                    .contentTransition(.symbolEffect(.replace))
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.displayName).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Text("\(c.procedureDisplay)\(MP.dot)\(c.surgeryMonth)")
                        .mpFont(.label).foregroundStyle(MP.body)
                }
                Spacer(minLength: 8)
                if c.phoneMatch { StatusPill(text: "Number matches", tone: .low) }
            }
            .padding(14)
            // The site's selected card: glass with a 1.5pt ink ring; the glyph
            // changes too, so selection is never colour alone.
            .glassSurface(MP.surfaceShape, solid: true)
            .overlay(MP.surfaceShape.strokeBorder(isSelected ? MP.ink : .clear, lineWidth: 1.5))
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
        StepScaffold(eyebrow: model.eyebrow(.verify), title: "Check your texts",
                     subtitle: "We sent a code to \(model.phoneMasked ?? "your number"). It’s good for 10 minutes.") {
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
        StepScaffold(eyebrow: model.eyebrow(.health), title: "Connect Apple Health",
                     subtitle: model.isPersonal
                        ? "One tap, and your readiness, load and sleep readouts build themselves from overnight HRV, resting heart rate, sleep and workouts."
                        : "One tap, and your activity, sleep and heart data fill in on their own. Nothing to type.") {
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
                        Text("We never write to Health. Turn any type off on the next screen and we simply won’t read it.")
                            .mpFont(.label).mpSecondary()
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16)
                            .padding(.top, 8)
                            .padding(.bottom, 16)
                    }
                }
                if !(app.me?.features.appleHealth ?? true) {
                    ErrorBanner(text: "This server isn’t connected to Junction yet, so Health data has nowhere to go. You can skip and connect later.")
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
                            else if app.health.state == .unavailable { failure = "Health isn’t available on this device." }
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
                        // The site's done mark: a sage gradient disc with a
                        // white check and a lime halo. It pops once on arrival
                        // (off under Reduce Motion).
                        let d = min(discSide, 132)
                        GradientFill(gradient: .sage)
                            .clipShape(Circle())
                            .frame(width: d, height: d)
                            .background(Circle().fill(MP.lime.opacity(0.35)).padding(-10))
                            .overlay(
                                Image(systemName: "checkmark")
                                    .font(.system(size: (d * 0.4).rounded(), weight: .semibold))
                                    .foregroundStyle(.white)
                                    .symbolEffect(.bounce, options: .nonRepeating, value: reduceMotion ? false : shown)
                            )
                            .shadow(color: Color(red: 74 / 255, green: 102 / 255, blue: 62 / 255).opacity(0.45),
                                    radius: 14, y: 8)
                            .scaleEffect(shown || reduceMotion ? 1 : 0.6)
                            .opacity(shown || reduceMotion ? 1 : 0)
                            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion), value: shown)
                            .accessibilityHidden(true)

                        VStack(alignment: .leading, spacing: 10) {
                            Text("You’re all set, \(app.me?.patient.firstName ?? "there").")
                                .title(MPSize.displayM)
                                .accessibilityAddTraits(.isHeader)
                            Text("Welcome to MedPull. Here’s what happens next.")
                                .mpFont(.lede).foregroundStyle(MP.body)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .entrance(shown, order: 1)

                        VStack(alignment: .leading, spacing: 18) {
                            if app.me?.isPersonal == true {
                                FeatureRow(icon: "gauge.with.dots.needle.67percent", family: .teal,
                                           title: "Readiness every morning",
                                           detail: "Wear your watch tonight. Tomorrow you’ll see where you stand and why, against your own baseline.")
                                    .entrance(shown, order: 2)
                                FeatureRow(icon: "checklist", family: .blue,
                                           title: "A plan for the day",
                                           detail: "Written from your numbers each morning: push, hold, ease off or rest, with a check-in that takes a minute.")
                                    .entrance(shown, order: 3)
                            } else if app.me?.patient.isRecovery == true {
                                FeatureRow(icon: "message.fill", family: .blue,
                                           title: "We’ll text you",
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
                                           title: "We’ll text you",
                                           detail: "When your care team asks for something, answer by text or right here in the app.")
                                    .entrance(shown, order: 3)
                            }
                            FeatureRow(icon: "waveform", family: .indigo,
                                       title: "Talk any time",
                                       detail: app.me?.isPersonal == true
                                        ? "Ask your coach why a number moved and get the actual values back. Log how you feel in a sentence."
                                        : "Tell MedPull how you’re doing in your own words. Anything important goes to your care team.")
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
        .background { OnboardingSky() }
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
                     subtitle: "This starts your record at \(model.hospital?.name ?? "the hospital"). Had an operation? Add it and we’ll follow your recovery. If not, we’ll follow your everyday signals.") {
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
                                Text("I’m recovering from an operation").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
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

// MARK: - The personal space

/// The beta consent, read before any account exists. What it records goes
/// out with the call that creates the session.
private struct ConsentStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    var body: some View {
        ConsentLoader(onAgree: { accepted in
            model.consent = accepted
            if model.name.isEmpty, let name = accepted.signature { model.name = name }
            model.go(model.isPersonal ? .personalAbout : .hospital)
        }) {
            EmptyView()
        }
    }
}

/// Back in, on any phone: the email and password. Forgot: a code by text
/// to the number on the account, when the server can send one.
private struct LoginStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @FocusState private var focus: Field?
    @State private var forgetting = false
    enum Field { case email, password, code, newPassword }

    var body: some View {
        StepScaffold(eyebrow: "Welcome back", title: forgetting ? "Reset your password" : "Sign in",
                     subtitle: forgetting
                        ? "We’ll text a code to the number on your account, if there is one, and you choose a new password."
                        : "The email and password you set up MedPull Personal with.") {
            VStack(spacing: 14) {
                TextField("Email", text: $model.loginEmail,
                          prompt: Text("Email").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .textContentType(.emailAddress).keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .focused($focus, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { focus = forgetting ? .email : .password }
                if !forgetting {
                    SecureField("Password", text: $model.loginPassword,
                                prompt: Text("Password").foregroundColor(MP.muted))
                        .textFieldStyle(FieldStyle())
                        .textContentType(.password)
                        .focused($focus, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { if model.canLogin { Task { await model.login(api: app.api, app: app) } } }
                } else if let sent = model.forgotSent {
                    if sent.sent {
                        Card(tint: true) {
                            Text("Code texted to \(sent.phoneMasked ?? "your number"). It’s good for 10 minutes.")
                                .mpFont(.copy).foregroundStyle(MP.ink)
                        }
                        TextField("6-digit code", text: $model.resetCode,
                                  prompt: Text("6-digit code").foregroundColor(MP.muted))
                            .textFieldStyle(FieldStyle()).keyboardType(.numberPad).textContentType(.oneTimeCode)
                            .focused($focus, equals: .code)
                        SecureField("New password (8+ characters)", text: $model.resetPassword,
                                    prompt: Text("New password (8+ characters)").foregroundColor(MP.muted))
                            .textFieldStyle(FieldStyle()).textContentType(.newPassword)
                            .focused($focus, equals: .newPassword)
                    } else {
                        ErrorBanner(text: sent.detail ?? "We couldn’t send a code.")
                    }
                }
                if let error = model.error { ErrorBanner(text: error) }
                Button(forgetting ? "Back to sign in" : "Forgot your password?") {
                    model.error = nil
                    model.forgotSent = nil
                    forgetting.toggle()
                }
                .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                Button("New here? Set up an account") { model.go(.mode) }
                    .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
            }
        } footer: {
            if !forgetting {
                PrimaryButton(title: "Sign in", icon: "arrow.right", loading: model.loading,
                              disabled: !model.canLogin) {
                    Task { await model.login(api: app.api, app: app) }
                }
            } else if model.forgotSent?.sent == true {
                PrimaryButton(title: "Set new password", loading: model.loading,
                              disabled: model.resetCode.count < 4 || model.resetPassword.count < 8) {
                    Task { await model.reset(api: app.api, app: app) }
                }
            } else {
                PrimaryButton(title: "Text me a code", icon: "message.fill", loading: model.loading,
                              disabled: !model.loginEmail.contains("@")) {
                    Task { await model.forgot(api: app.api) }
                }
            }
        }
        .onAppear { focus = .email }
        .mpErrorFeedback(model.error)
    }
}

/// Name, email and password for a new space; the mobile number is optional
/// (texts, and pairing with a hospital record). The phone-only sign-in is
/// the fallback for a person who set up before the email login existed.
private struct PersonalAboutStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @FocusState private var focus: Field?
    enum Field { case name, email, password, phone }

    var body: some View {
        StepScaffold(eyebrow: model.eyebrow(.personalAbout),
                     title: model.personalSignin ? "Welcome back" : "Set up your login",
                     subtitle: model.personalSignin
                        ? "The mobile number on your personal space. We’ll text a code when this server can."
                        : "Your name, an email and a password get you back in on any phone. A mobile number is optional: it turns on the morning brief by text.") {
            VStack(spacing: 14) {
                if !model.personalSignin {
                    TextField("Full name", text: $model.name,
                              prompt: Text("Full name").foregroundColor(MP.muted))
                        .textFieldStyle(FieldStyle())
                        .textContentType(.name).autocorrectionDisabled()
                        .focused($focus, equals: .name)
                        .submitLabel(.next)
                        .onSubmit { focus = .email }
                    TextField("Email", text: $model.email,
                              prompt: Text("Email").foregroundColor(MP.muted))
                        .textFieldStyle(FieldStyle())
                        .textContentType(.emailAddress).keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .focused($focus, equals: .email)
                        .submitLabel(.next)
                        .onSubmit { focus = .password }
                    HStack(spacing: 8) {
                        Group {
                            if model.showPassword {
                                TextField("Password (8+ characters)", text: $model.password,
                                          prompt: Text("Password (8+ characters)").foregroundColor(MP.muted))
                            } else {
                                SecureField("Password (8+ characters)", text: $model.password,
                                            prompt: Text("Password (8+ characters)").foregroundColor(MP.muted))
                            }
                        }
                        .textFieldStyle(FieldStyle())
                        .textContentType(.newPassword)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .focused($focus, equals: .password)
                        .submitLabel(.next)
                        .onSubmit { focus = .phone }
                        Button { model.showPassword.toggle() } label: {
                            Image(systemName: model.showPassword ? "eye.slash" : "eye")
                                .font(.systemGlyphs(17))
                                .foregroundStyle(MP.muted)
                                .frame(width: 44, height: 44)
                        }
                        .accessibilityLabel(model.showPassword ? "Hide password" : "Show password")
                    }
                }
                TextField(model.personalSignin ? "Mobile number" : "Mobile number (optional)", text: $model.phone,
                          prompt: Text(model.personalSignin ? "Mobile number" : "Mobile number (optional)").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .textContentType(.telephoneNumber).keyboardType(.phonePad)
                    .focused($focus, equals: .phone)
                if !model.personalSignin {
                    Card(padding: 0) {
                        Toggle(isOn: $model.smsBriefs) {
                            Label {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Morning brief by text").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                    Text("Your readiness and plan, before you open anything.")
                                        .mpFont(.label).foregroundStyle(MP.muted)
                                }
                            } icon: {
                                IconTile("message.fill", family: .blue)
                            }
                            .labelStyle(TileLabelStyle())
                        }
                        .tint(MP.brand)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                    }
                }
                if model.personalSignin {
                    Button("Set up a new space instead") {
                        model.error = nil
                        model.personalSignin = false
                    }
                    .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                } else {
                    Button("Already have an account? Sign in") { model.go(.login) }
                        .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                }
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: model.personalSignin ? "Text me a code" : "Continue", icon: "arrow.right",
                          loading: model.loading, disabled: !model.canContinuePersonal) {
                if model.personalSignin {
                    Task { await model.personalJoin(api: app.api, app: app) }
                } else {
                    model.go(.goals)
                }
            }
        }
        .onAppear { focus = model.personalSignin ? .phone : (model.name.isEmpty ? .name : .email) }
        .mpErrorFeedback(model.error)
    }
}

/// What the person wants out of MedPull. The goal decides which readouts
/// lead, what the plan writes and how the coach talks.
private struct GoalsStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    private let goals: [(String, String, MP.Category, String, String)] = [
        ("performance", "figure.run", .teal, "Train and perform",
         "Load, form, readiness. For runners, lifters, anyone with a training plan."),
        ("recovery", "cross.case.fill", .violet, "Recover from an injury or surgery",
         "MedPull’s recovery metrics on your own data, plus readiness and load for the return."),
        ("sleep", "bed.double.fill", .indigo, "Sleep and recover better",
         "Need, debt, regularity and what to change tonight."),
        ("everyday", "heart.fill", .blue, "Everyday health",
         "The full picture, balanced. Readiness, sleep, activity, resting heart rate."),
    ]

    var body: some View {
        StepScaffold(eyebrow: model.eyebrow(.goals), title: "What do you want from it?",
                     subtitle: "Pick one to lead. You can change it any time in Profile; everything is still measured.") {
            VStack(spacing: 12) {
                ForEach(goals, id: \.0) { key, icon, family, title, detail in
                    goalCard(key: key, icon: icon, family: family, title: title, detail: detail)
                }
                details.padding(.top, 4)
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: "Create my space", icon: "sparkles", loading: model.loading,
                          disabled: !model.canCreateSpace) {
                Task { await model.personalJoin(api: app.api, app: app) }
            }
        }
        .task(id: model.goal) { if model.goal == "recovery" { await model.loadProcedures(api: app.api) } }
        .mpErrorFeedback(model.error)
    }

    private func goalCard(key: String, icon: String, family: MP.Category, title: String,
                          detail: String) -> some View {
        let isSelected = model.goal == key
        return Button { model.goal = key } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.systemGlyphs(22, weight: .regular))
                    .foregroundStyle(isSelected ? MP.ink : MP.lineStrong)
                    .contentTransition(.symbolEffect(.replace))
                    .padding(.top, 10)
                IconTile(icon, family: family, size: 40)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        .multilineTextAlignment(.leading)
                    Text(detail).mpFont(.label).foregroundStyle(MP.body)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(14)
            .glassSurface(MP.surfaceShape, solid: true)
            .overlay(MP.surfaceShape.strokeBorder(isSelected ? MP.ink : .clear, lineWidth: 1.5))
            .contentShape(MP.surfaceShape)
        }
        .buttonStyle(CardPressStyle())
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .sensoryFeedback(.selection, trigger: isSelected) { _, new in new }
    }

    @ViewBuilder private var details: some View {
        switch model.goal {
        case "performance":
            VStack(alignment: .leading, spacing: 10) {
                Text("Your sport and target").mpFont(.labelMedium).foregroundStyle(MP.muted)
                TextField("Sport (running, cycling, lifting…)", text: $model.sport,
                          prompt: Text("Sport (running, cycling, lifting…)").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).autocorrectionDisabled()
                Card(padding: 0) {
                    Stepper(value: $model.weeklyTargetMinutes, in: 30...1500, step: 30) {
                        HStack {
                            Text("Training a week").mpFont(.copyLarge).foregroundStyle(MP.ink)
                            Spacer()
                            Text("\(model.weeklyTargetMinutes / 60) h \(model.weeklyTargetMinutes % 60 == 0 ? "" : "\(model.weeklyTargetMinutes % 60) min")")
                                .font(.figuresCopyLarge).foregroundStyle(MP.ink)
                        }
                    }
                    .tint(MP.brand)
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .mpSelectionFeedback(model.weeklyTargetMinutes)
                }
            }
        case "sleep":
            Card(padding: 0) {
                Stepper(value: $model.sleepTargetHours, in: 5...10, step: 0.25) {
                    HStack {
                        Text("Sleep you’re aiming for").mpFont(.copyLarge).foregroundStyle(MP.ink)
                        Spacer()
                        Text(String(format: "%.2g h", model.sleepTargetHours))
                            .font(.figuresCopyLarge).foregroundStyle(MP.ink)
                    }
                }
                .tint(MP.brand)
                .padding(.horizontal, 16).padding(.vertical, 10)
                .mpSelectionFeedback(model.sleepTargetHours)
            }
        case "recovery":
            VStack(alignment: .leading, spacing: 10) {
                Text("What are you coming back from?").mpFont(.labelMedium).foregroundStyle(MP.muted)
                if model.procedures.isEmpty {
                    ProgressView().controlSize(.small)
                } else {
                    FlowProcedures(procedures: model.procedures, selected: $model.procedure)
                }
                TextField("Or describe it (ACL, left; stress fracture…)", text: $model.injury,
                          prompt: Text("Or describe it (ACL, left; stress fracture…)").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                DatePicker("When did it happen?", selection: $model.anchorDate, in: ...Date(),
                           displayedComponents: .date)
                    .datePickerStyle(.compact)
                    .mpFont(.copyLargeMedium)
                    .foregroundStyle(MP.ink)
            }
        default:
            EmptyView()
        }
    }
}

/// The trial has started; here are the plans.
private struct PlanStep: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        PaywallView(mode: .onboarding) { model.go(.health) }
    }
}

extension URL: @retroactive Identifiable {
    public var id: String { absoluteString }
}
