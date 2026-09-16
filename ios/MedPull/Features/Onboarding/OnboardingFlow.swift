import SwiftUI

/// Motion comes from `MPMotion` in Theme.swift. SwiftUI does NOT honour
/// `accessibilityReduceMotion` for explicit animations, so every `.animation`
/// here goes through `MPMotion.gated`.
struct OnboardingFlow: View {
    @Environment(AppModel.self) private var app
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var model = OnboardingModel()

    var body: some View {
        VStack(spacing: 0) {
            if model.step != .welcome && model.step != .done {
                StepDots(current: model.step)
                    .padding(.top, 12)
            }
            Group {
                switch model.step {
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
            .transition(reduceMotion
                ? AnyTransition.opacity
                : AnyTransition.asymmetric(
                    insertion: .move(edge: .trailing).combined(with: .opacity),
                    removal: .move(edge: .leading).combined(with: .opacity)))
            .id(model.step)
        }
        .animation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion), value: model.step)
        // Every system control in the flow — both spinners, both DatePickers,
        // the two Toggles, the quiet text buttons — takes this tint.
        .tint(MP.brand)
        .screen()
    }
}

private struct StepDots: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let current: OnboardingModel.Step
    private let shown: [OnboardingModel.Step] = [.hospital, .path, .identity, .verify, .health, .wearable]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(shown, id: \.rawValue) { s in
                // `MP.pillShape`, not a bare `Capsule()`: one pill vocabulary.
                // The unreached dots were `MP.track`, which is a slider
                // trough and measures 1.18:1 on light canvas — six invisible
                // dots, i.e. no step indicator at all in light mode. They
                // carry information (how much of the flow is left), so they
                // take the 3:1 graphic floor: `lineStrong` is 3.57:1 light
                // and 6.06:1 dark on canvas. The reached dots stay `brand`
                // as a FILL (4.29:1 light / 3.99:1 dark on canvas).
                MP.pillShape
                    .fill(s.rawValue <= current.rawValue ? MP.brand : MP.lineStrong)
                    .frame(width: s == current ? 22 : 8, height: 6)
            }
        }
        .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: current)
        .accessibilityHidden(true)
    }
}

private struct StepScaffold<Content: View, Footer: View>: View {
    let eyebrow: String
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var content: () -> Content
    @ViewBuilder var footer: () -> Footer

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text(eyebrow).eyebrow()
                    Text(title).title(MPSize.displayS)
                    if let subtitle {
                        // 16/400 on `body`, not 15 on `muted`: this is the
                        // lede paragraph of the screen, so it takes the same
                        // rung and the same tier as the Welcome and Done
                        // paragraphs (6.73:1 light / 7.11:1 dark on canvas).
                        Text(subtitle).font(.copyLarge).foregroundStyle(MP.body)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    content().padding(.top, 18)
                }
                .padding(.horizontal, 22)
                .padding(.top, 28)
                .padding(.bottom, 16)
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 10) { footer() }
                .padding(.horizontal, 22)
                .padding(.bottom, 18)
        }
    }
}

/// The quiet tertiary action — Back / Skip / Send a new code.
///
/// Components.swift has no recipe for this: `SecondaryButton` is a filled
/// full-width control, and five of those stacked under a `PrimaryButton`
/// would read as five commits. So it stays text, on `brandInk` (5.75:1 light
/// / 6.78:1 dark on panel, 5.35 / 7.25 on canvas) at the 14/500 rung —
/// never on `MP.brand`, which is 3.74:1 as text on dark panel.
///
/// The 44pt frame is the substance of it. These were bare `Button("Back")`
/// labels roughly 17pt tall: under WCAG 2.5.8's 24x24 minimum and well under
/// Apple's 44pt, on the screens where a patient is most likely to need to go
/// back. The frame and `contentShape` are on the label, so the whole strip
/// is the target rather than the glyphs.
private struct QuietAction: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.copyMedium)
                .foregroundStyle(MP.brandInk)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
        }
    }
}

// MARK: - Steps

private struct WelcomeStep: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        // The Spacer/hero/Spacer/footer distribution is unchanged, but it now
        // lives inside a ScrollView pinned to the viewport height, so it
        // SCROLLS instead of clipping. At AX5 this screen used to push its
        // own wordmark off the top and the disclaimer off the bottom, because
        // 16pt body copy grows 2.81x on the `.body` curve and there was
        // nowhere for it to go. `.basedOnSize` means no rubber-banding at the
        // default size, so nothing changes until the content overflows.
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Spacer(minLength: 24)
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 10) {
                            MP.controlShape
                                .fill(MP.brand).frame(width: 38, height: 38)
                                // `.white` was RIGHT here and the pixels do
                                // not move: white on #1976D2 is 4.60:1 in
                                // both modes and is the single sanctioned
                                // white-on-brand pairing. Only the NAME
                                // changes — `MP.onBrand` is #FFFFFF in both
                                // modes — so a repalette of on-brand ink
                                // reaches this glyph instead of skipping it.
                                // It is emphatically not `brandInk`: that
                                // would put 5.75:1 blue on a blue fill.
                                .overlay(Image(systemName: "waveform.path.ecg")
                                    .font(.ledeMedium)
                                    .foregroundStyle(MP.onBrand))
                            // 20/500 FROZEN, not `display(20)`: 20 is a UI
                            // rung, and putting it on the fluid `.largeTitle`
                            // curve made the wordmark a display element that
                            // grew past the hero beside it.
                            Text("MedPull").font(.subheadMedium).foregroundStyle(MP.ink)
                        }
                        Text("Your health,\nin one place.").title(MPSize.displayM).lineSpacing(2)
                        Text("Join your hospital, connect your watch, and your care team sees the whole picture — steps, sleep, heart, and how you're feeling. About two minutes to set up.")
                            .font(.copyLarge).foregroundStyle(MP.body).lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, 22)
                    Spacer(minLength: 24)
                    VStack(spacing: 10) {
                        PrimaryButton(title: "Get started", icon: "arrow.right") { model.go(.hospital) }
                        // THE DISCLAIMER. It was `MP.faint` at 2.409:1 on
                        // canvas — a WCAG 1.4.3 failure on the one line of
                        // legal copy in the app, and `faint` is non-text by
                        // definition. `muted` is 5.03:1 light / 5.24:1 dark
                        // on canvas. Centred because the frame it sits in is
                        // full-width, so a wrapped second line used to hang
                        // ragged under a centred first line.
                        Text("Monitoring signals for your care team — not a diagnosis.")
                            .font(.label).foregroundStyle(MP.muted)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity)
                    }
                    .padding(.horizontal, 22).padding(.bottom, 18)
                }
                .frame(minWidth: proxy.size.width, minHeight: proxy.size.height, alignment: .leading)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
    }
}

private struct HospitalStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    var body: some View {
        StepScaffold(eyebrow: "Step 1 of 5", title: "Which hospital are you with?",
                     subtitle: "Your health portfolio is shared with this hospital's care team.") {
            VStack(spacing: 12) {
                // EVERY PLACEHOLDER ON THIS SCREEN CARRIES A `prompt:`.
                // SwiftUI's default placeholder is `UIColor.placeholderText`,
                // which I measured off the screenshot at #C5C5C7 on #FFFFFF
                // = 1.72:1 — a 1.4.3 failure on the first thing a patient
                // types into. `FieldStyle` has no hook for it (SwiftUI gives
                // the style no access to the prompt), so the call site is
                // where it has to be set, and `muted` is the placeholder tier
                // (5.39:1 on panel light / 4.91:1 dark) — never `faint`.
                TextField("Search hospitals", text: $model.hospitalQuery,
                          prompt: Text("Search hospitals").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .autocorrectionDisabled()
                if model.hospitals.isEmpty {
                    if let error = model.error { ErrorBanner(text: error) } else { ProgressView().frame(maxWidth: .infinity).padding() }
                }
                // `Card(padding: 0)` instead of a hand-rolled
                // fill + `strokeBorder` on the deprecated `MP.cardRadius`:
                // same geometry, one edge, and the surface radius comes from
                // the token rather than from a name that now warns.
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        ForEach(model.filteredHospitals) { h in
                            Button {
                                model.hospital = h
                                model.candidates = []
                                model.selected = nil
                                model.go(.path)
                            } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: "building.2.fill")
                                        .font(.copyLarge)
                                        .foregroundStyle(MP.brandInk)
                                        .frame(width: 22)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(h.name).font(.copyLargeMedium).foregroundStyle(MP.ink)
                                        Text([h.system, "\(h.city), \(h.state)"].compactMap { $0 }.joined(separator: MP.dot))
                                            .font(.label).foregroundStyle(MP.muted)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right").font(.copyMedium).foregroundStyle(MP.muted)
                                }
                                .padding(.vertical, 13)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            if h.id != model.filteredHospitals.last?.id { Divider().overlay(MP.line) }
                        }
                    }
                    .padding(.horizontal, 14)
                }
            }
        } footer: {
            EmptyView()
        }
        .task { await model.loadHospitals(api: app.api) }
    }
}

private struct IdentityStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @FocusState private var focus: Field?
    enum Field { case name, phone }

    var body: some View {
        StepScaffold(eyebrow: "Step 3 of 5", title: "Find your record",
                     subtitle: "Your name as it's on file at \(model.hospital?.name ?? "the hospital"), and the mobile number we can text. A number the clinic already has finds you on its own.") {
            VStack(spacing: 14) {
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
                        HStack {
                            // Demoted from `.eyebrow()`: the uppercase
                            // budget is ONE element per screen and the
                            // scaffold's "Step 3 of 5" is spending it. Same
                            // rung and tier as an eyebrow, sentence case.
                            Text(model.searching ? "Looking you up…" : model.candidates.isEmpty ? "No match yet" : "Is this you?")
                                .font(.labelMedium).foregroundStyle(MP.muted)
                            if model.searching { ProgressView().controlSize(.small) }
                        }
                        ForEach(model.candidates) { c in
                            Button { model.selected = c } label: {
                                HStack(spacing: 12) {
                                    // Unselected is `lineStrong`, not
                                    // `faint`: an empty radio is the only cue
                                    // the control exists, so 1.4.11's 3:1
                                    // applies and `faint` is 2.59:1 on panel.
                                    // 3.83:1 light / 5.67:1 dark. Selected is
                                    // `brandInk` (4.96:1 light / 5.62:1 dark
                                    // on the tint it then sits on), never
                                    // `brand`, which is 3.10:1 there.
                                    Image(systemName: model.selected?.id == c.id ? "checkmark.circle.fill" : "circle")
                                        .font(.subhead)
                                        .foregroundStyle(model.selected?.id == c.id ? MP.brandInk : MP.lineStrong)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(c.displayName).font(.copyLargeMedium).foregroundStyle(MP.ink)
                                        // `body`, not `muted`: when this row
                                        // is selected the ground becomes
                                        // `brandTint`, where `muted` measures
                                        // 4.07:1 dark — an AA failure that
                                        // only appears in one state of one
                                        // mode. `body` is 6.24:1 light /
                                        // 5.51:1 dark on the tint and
                                        // 7.22 / 6.65 on panel.
                                        Text("\(c.procedureDisplay)\(MP.dot)\(c.surgeryMonth)").font(.label).foregroundStyle(MP.body)
                                    }
                                    Spacer()
                                    if c.phoneMatch { StatusPill(text: "Number matches", tone: .low) }
                                }
                                .padding(14)
                                // Selection changes the FILL as well as the
                                // stroke, so it is never colour alone, and
                                // the stroke stays 1pt in both states — the
                                // 1.5pt selected border moved the row's
                                // content by half a point as it was chosen.
                                .background(MP.surfaceShape.fill(model.selected?.id == c.id ? MP.brandTint : MP.panel))
                                .overlay(MP.surfaceShape
                                    .strokeBorder(model.selected?.id == c.id ? MP.brand : MP.line, lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                        if !model.searching && model.candidates.isEmpty {
                            Text("Check the spelling, or ask the clinic which name they enrolled you under. If they have your number, typing it above finds you too.")
                                .font(.copy).foregroundStyle(MP.muted)
                                .fixedSize(horizontal: false, vertical: true)
                            Button {
                                model.choose(.joinGeneral)
                            } label: {
                                // The inline twin of `QuietAction`, left
                                // leading-aligned because it sits in a
                                // leading column rather than a footer. Same
                                // rung, same `brandInk`, same 44pt target.
                                Text("Not on the list? Join as a new patient instead")
                                    .font(.copyMedium)
                                    .foregroundStyle(MP.brandInk)
                                    .frame(minHeight: 44, alignment: .leading)
                                    .contentShape(Rectangle())
                            }
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
            QuietAction(title: "Back") { model.go(.path) }
        }
        .task(id: "\(model.name)|\(model.phone)") {
            try? await Task.sleep(for: .milliseconds(350))
            guard !Task.isCancelled else { return }
            await model.search(api: app.api)
        }
        .onAppear { focus = .name }
    }
}

private struct VerifyStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @FocusState private var focused: Bool

    var body: some View {
        StepScaffold(eyebrow: "Step 4 of 5", title: "Enter the code we texted",
                     subtitle: "Sent to \(model.phoneMasked ?? "your number"). It expires in 10 minutes.") {
            VStack(spacing: 14) {
                TextField("6-digit code", text: $model.code,
                          prompt: Text("6-digit code").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .keyboardType(.numberPad).textContentType(.oneTimeCode)
                    // THE MONOSPACE ESCAPE IS GONE FROM HERE BECAUSE IT WAS
                    // INERT, NOT BECAUSE A CODE DOESN'T WANT ONE. This line
                    // was `.font(.system(size: 24, weight: .semibold, design:
                    // .monospaced))` — off the ladder and above the weight
                    // ceiling — and it never drew: `FieldStyle` applies
                    // `.font(.copyLarge)` directly to the configuration,
                    // which beats any font inherited from outside the style.
                    // Measured on the screenshot with the code prefilled,
                    // glyph advances came out 8.67 / 6.33 / 9.33 / 9.67 /
                    // 10.33pt — proportional Instrument Sans 16, not a
                    // monospace column. Keeping a dead `.font(.figuresSubhead)`
                    // here would just be the same lie in newer words; the
                    // hook has to come from Components.swift (see `handoff`).
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
    }
}

private struct HealthStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @State private var working = false
    @State private var failure: String?

    var body: some View {
        StepScaffold(eyebrow: "Step 5 of 5", title: "Connect Apple Health",
                     subtitle: "One tap. Your steps, sleep, heart rate and walking data flow into your portfolio automatically — no typing anything in.") {
            VStack(spacing: 12) {
                Card(tint: true) {
                    VStack(alignment: .leading, spacing: 10) {
                        // Split so the glyph can be `brandInk` while the
                        // words stay `ink`: a single `foregroundStyle` on a
                        // `Label` paints both, and a solid black square
                        // outweighed every checkmark under it.
                        Label {
                            Text("What we read").foregroundStyle(MP.ink)
                        } icon: {
                            Image(systemName: "heart.text.square.fill").foregroundStyle(MP.brandInk)
                        }
                        .font(.copyMedium)
                        ForEach(["Steps, distance and stairs", "Sleep and resting heart rate", "Walking speed, step length and steadiness", "Workouts and exercise minutes"], id: \.self) { line in
                            HStack(alignment: .top, spacing: 8) {
                                // `brandInk` on the tint: 4.96:1 light /
                                // 5.62:1 dark, where `brand` itself is
                                // 3.10:1 dark. `.bold` was a weight above
                                // the 500 ceiling that only rendered because
                                // `MPFont.name(for:)` clamps it.
                                Image(systemName: "checkmark").font(.labelMedium).foregroundStyle(MP.brandInk).padding(.top, 3)
                                Text(line).font(.copy).foregroundStyle(MP.body)
                            }
                        }
                        // `body` at the 12 rung, not `muted`: this sits on
                        // `brandTint` (Card(tint: true)), where `muted` is
                        // 4.07:1 in dark. Size carries the demotion instead
                        // of colour — 6.24:1 light / 5.51:1 dark.
                        Text("We never write to Health. Turn any type off on the next screen and we simply won't read it.")
                            .font(.label).foregroundStyle(MP.body).padding(.top, 4)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if !(app.me?.features.appleHealth ?? true) {
                    ErrorBanner(text: "This server isn't connected to Junction yet, so Health data has nowhere to go. You can skip and connect later.")
                }
                if let failure { ErrorBanner(text: failure) }
                if app.health.state == .connected {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.seal.fill").font(.copyLarge).foregroundStyle(MP.riskLow)
                        Text("Connected — first sync is running").font(.copyMedium).foregroundStyle(MP.ink)
                    }
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
    }
}

private struct WearableStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @State private var link: URL?
    @State private var working = false
    @State private var failure: String?

    var body: some View {
        StepScaffold(eyebrow: "Almost done", title: "Wear something else?",
                     subtitle: "Oura, Garmin, WHOOP, Fitbit, Withings, Polar — sign in once and it syncs on its own. Apple Watch is already covered by Health.") {
            VStack(spacing: 12) {
                HStack(spacing: 8) {
                    ForEach(["Oura", "Garmin", "WHOOP", "Fitbit", "Withings"], id: \.self) { b in
                        // A non-interactive tag: 12/500 on `body` (6.37:1
                        // light / 6.21:1 dark on `soft`), `MP.pillShape`
                        // rather than a bare `Capsule()`, and a `line`
                        // hairline so the pill is still a pill on light
                        // canvas, where `soft` is only 1.13:1 against it.
                        // One edge, no shadow.
                        Text(b).font(.labelMedium).foregroundStyle(MP.body)
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(MP.pillShape.fill(MP.soft))
                            .overlay(MP.pillShape.strokeBorder(MP.line, lineWidth: 1))
                    }
                }
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
    }
}

private struct DoneStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    var body: some View {
        // Same viewport-pinned ScrollView as Welcome, for the same reason:
        // this screen is Spacer/content/Spacer with no scroll region, and at
        // AX5 the paragraph alone is taller than the phone.
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Spacer(minLength: 24)
                    VStack(alignment: .leading, spacing: 14) {
                        // 44 is a display rung, so it goes on the display
                        // band's curve (1.69x at AX5) rather than the UI
                        // band's 2.81x.
                        Image(systemName: "checkmark.circle.fill").font(.displayL).foregroundStyle(MP.riskLow)
                        Text("You're set, \(app.me?.patient.firstName ?? "there").").title(MPSize.displayM)
                        Text(app.me?.patient.isRecovery == true
                             ? "When a task is ready we'll text you. Do it right there in Messages, or open the app — either way your care team sees it."
                             : "Your portfolio fills in as your data arrives. When your care team asks for something we'll text you, and you can answer right there or in the app.")
                            .font(.copyLarge).foregroundStyle(MP.body).lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, 22)
                    Spacer(minLength: 24)
                    PrimaryButton(title: "Open MedPull", icon: "arrow.right") { app.enterHome() }
                        .padding(.horizontal, 22).padding(.bottom, 18)
                }
                .frame(minWidth: proxy.size.width, minHeight: proxy.size.height, alignment: .leading)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
    }
}

private struct PathStep: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        StepScaffold(eyebrow: "Step 2 of 5", title: "How are you joining?",
                     subtitle: "\(model.hospital?.name ?? "Your hospital") follows patients with and without a surgery. Either way, one record: what your care team sees is what you see here.") {
            VStack(spacing: 12) {
                pathCard(icon: "person.text.rectangle", title: "My care team set me up",
                         detail: "The clinic already has a record for you (or you've used MedPull before). Find it so their messages and tasks reach this phone.") {
                    model.choose(.findRecord)
                }
                pathCard(icon: "person.crop.circle.badge.plus", title: "I'm new here",
                         detail: "Create your record now — with or without a surgery. Your activity, sleep and vitals build a portfolio your care team can see.") {
                    model.choose(.joinGeneral)
                }
            }
        } footer: {
            QuietAction(title: "Different hospital") { model.go(.hospital) }
        }
    }

    private func pathCard(icon: String, title: String, detail: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: icon).font(.subheadMedium).foregroundStyle(MP.brandInk)
                        .frame(width: 40, height: 40)
                        .background(MP.controlShape.fill(MP.brandTint))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).font(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(detail).font(.copy).foregroundStyle(MP.muted).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.copyMedium).foregroundStyle(MP.muted).padding(.top, 10)
                }
            }
        }
        .buttonStyle(.plain)
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
        StepScaffold(eyebrow: "Step 3 of 5", title: "About you",
                     subtitle: "This creates your record at \(model.hospital?.name ?? "the hospital"). If you had an operation, add it and we follow your recovery; otherwise we follow your everyday signals.") {
            VStack(spacing: 14) {
                TextField("Full name", text: $model.name,
                          prompt: Text("Full name").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).textContentType(.name).autocorrectionDisabled()
                TextField("Mobile number", text: $model.phone,
                          prompt: Text("Mobile number").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).textContentType(.telephoneNumber).keyboardType(.phonePad)
                Toggle(isOn: $hasDOB) {
                    Text("Add date of birth").font(.copyLargeMedium).foregroundStyle(MP.ink)
                }
                .tint(MP.brand)
                .onChange(of: hasDOB) { _, on in model.dateOfBirth = on ? dob : nil }
                if hasDOB {
                    // This picker carried no font at all, so its label drew
                    // in San Francisco 17 next to Instrument Sans 16. The
                    // value chip is UIKit-drawn and stays system — see
                    // `problems`.
                    DatePicker("Date of birth", selection: $dob, in: ...Date(), displayedComponents: .date)
                        .datePickerStyle(.compact)
                        .font(.copyLargeMedium)
                        .onChange(of: dob) { _, d in model.dateOfBirth = d }
                }
                Toggle(isOn: surgicalBinding) {
                    Text("I'm recovering from an operation").font(.copyLargeMedium).foregroundStyle(MP.ink)
                }
                .tint(MP.brand)
                if surgical {
                    VStack(alignment: .leading, spacing: 8) {
                        // Demoted from `.eyebrow()` — same budget, same
                        // reason as IdentityStep: "Step 3 of 5" above it is
                        // this screen's one uppercase element.
                        Text("Operation").font(.labelMedium).foregroundStyle(MP.muted)
                        if model.procedures.isEmpty {
                            ProgressView().controlSize(.small)
                        } else {
                            FlowProcedures(procedures: model.procedures, selected: $model.procedure)
                        }
                        DatePicker("Surgery date", selection: $model.surgeryDate, in: ...Date(), displayedComponents: .date)
                            .datePickerStyle(.compact)
                            .font(.copyLargeMedium)
                    }
                    .padding(.top, 4)
                }
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: surgical ? "Create my record" : "Join \(model.hospital?.name.split(separator: " ").first.map(String.init) ?? "hospital")",
                          loading: model.loading, disabled: !model.canJoin) {
                Task { await model.join(api: app.api, app: app) }
            }
            QuietAction(title: "Back") { model.go(.path) }
        }
        .task(id: surgical) { if surgical { await model.loadProcedures(api: app.api) } }
    }
}

private struct FlowProcedures: View {
    let procedures: [Procedure]
    @Binding var selected: Procedure?

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
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
