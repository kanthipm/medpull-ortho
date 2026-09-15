import SwiftUI

struct OnboardingFlow: View {
    @Environment(AppModel.self) private var app
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
            .transition(.asymmetric(
                insertion: .move(edge: .trailing).combined(with: .opacity),
                removal: .move(edge: .leading).combined(with: .opacity)))
            .id(model.step)
        }
        .animation(.spring(duration: 0.38), value: model.step)
        .screen()
    }
}

private struct StepDots: View {
    let current: OnboardingModel.Step
    private let shown: [OnboardingModel.Step] = [.hospital, .path, .identity, .verify, .health, .wearable]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(shown, id: \.rawValue) { s in
                Capsule()
                    .fill(s.rawValue <= current.rawValue ? MP.brand : MP.track)
                    .frame(width: s == current ? 22 : 8, height: 6)
            }
        }
        .animation(.spring(duration: 0.3), value: current)
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
                    Text(title).title(28)
                    if let subtitle {
                        Text(subtitle).font(.system(size: 15)).foregroundStyle(MP.muted)
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

// MARK: - Steps

private struct WelcomeStep: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Spacer()
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 10) {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(MP.brand).frame(width: 38, height: 38)
                        .overlay(Image(systemName: "waveform.path.ecg").foregroundStyle(.white).font(.system(size: 18, weight: .semibold)))
                    Text("MedPull").font(.display(20)).foregroundStyle(MP.ink)
                }
                Text("Your health,\nin one place.").title(34).lineSpacing(2)
                Text("Join your hospital, connect your watch, and your care team sees the whole picture — steps, sleep, heart, and how you're feeling. About two minutes to set up.")
                    .font(.system(size: 16)).foregroundStyle(MP.body).lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 22)
            Spacer()
            VStack(spacing: 10) {
                PrimaryButton(title: "Get started", icon: "arrow.right") { model.go(.hospital) }
                Text("Monitoring signals for your care team — not a diagnosis.")
                    .font(.system(size: 12)).foregroundStyle(MP.faint)
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal, 22).padding(.bottom, 18)
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
                TextField("Search hospitals", text: $model.hospitalQuery)
                    .textFieldStyle(FieldStyle())
                    .autocorrectionDisabled()
                if model.hospitals.isEmpty {
                    if let error = model.error { ErrorBanner(text: error) } else { ProgressView().frame(maxWidth: .infinity).padding() }
                }
                VStack(spacing: 0) {
                    ForEach(model.filteredHospitals) { h in
                        Button {
                            model.hospital = h
                            model.candidates = []
                            model.selected = nil
                            model.go(.path)
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "building.2.fill").foregroundStyle(MP.brand).frame(width: 22)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(h.name).font(.system(size: 15.5, weight: .semibold)).foregroundStyle(MP.ink)
                                    Text([h.system, "\(h.city), \(h.state)"].compactMap { $0 }.joined(separator: " · "))
                                        .font(.system(size: 12.5)).foregroundStyle(MP.muted)
                                }
                                Spacer()
                                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(MP.faint)
                            }
                            .padding(.vertical, 13)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        if h.id != model.filteredHospitals.last?.id { Divider().overlay(MP.line) }
                    }
                }
                .padding(.horizontal, 14)
                .background(RoundedRectangle(cornerRadius: MP.cardRadius, style: .continuous).fill(MP.panel))
                .overlay(RoundedRectangle(cornerRadius: MP.cardRadius, style: .continuous).strokeBorder(MP.line))
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
                     subtitle: "Your name as it's on file at \(model.hospital?.name ?? "the hospital"), and the mobile number we can text.") {
            VStack(spacing: 14) {
                TextField("Full name", text: $model.name)
                    .textFieldStyle(FieldStyle())
                    .textContentType(.name).autocorrectionDisabled()
                    .focused($focus, equals: .name)
                    .submitLabel(.next)
                    .onSubmit { focus = .phone }
                TextField("Mobile number", text: $model.phone)
                    .textFieldStyle(FieldStyle())
                    .textContentType(.telephoneNumber).keyboardType(.phonePad)
                    .focused($focus, equals: .phone)

                if model.canSearch {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(model.searching ? "Looking you up…" : model.candidates.isEmpty ? "No match yet" : "Is this you?").eyebrow()
                            if model.searching { ProgressView().controlSize(.small) }
                        }
                        ForEach(model.candidates) { c in
                            Button { model.selected = c } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: model.selected?.id == c.id ? "checkmark.circle.fill" : "circle")
                                        .font(.system(size: 22)).foregroundStyle(model.selected?.id == c.id ? MP.brand : MP.faint)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(c.displayName).font(.system(size: 15.5, weight: .semibold)).foregroundStyle(MP.ink)
                                        Text("\(c.procedureDisplay) · \(c.surgeryMonth)").font(.system(size: 12.5)).foregroundStyle(MP.muted)
                                    }
                                    Spacer()
                                    if c.phoneMatch { StatusPill(text: "Number matches", tone: .low) }
                                }
                                .padding(14)
                                .background(RoundedRectangle(cornerRadius: MP.cardRadius, style: .continuous).fill(MP.panel))
                                .overlay(RoundedRectangle(cornerRadius: MP.cardRadius, style: .continuous)
                                    .strokeBorder(model.selected?.id == c.id ? MP.brand : MP.line, lineWidth: model.selected?.id == c.id ? 1.5 : 1))
                            }
                            .buttonStyle(.plain)
                        }
                        if !model.searching && model.candidates.isEmpty {
                            Text("Check the spelling, or ask the clinic which name they enrolled you under.")
                                .font(.system(size: 13)).foregroundStyle(MP.muted)
                            Button("Not on the list? Join with your details instead") {
                                model.choose(.joinAfterSurgery)
                            }
                            .font(.system(size: 13.5, weight: .semibold)).foregroundStyle(MP.brand)
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
            Button("Back") { model.go(.path) }
                .font(.system(size: 14, weight: .medium)).foregroundStyle(MP.brand)
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
                TextField("6-digit code", text: $model.code)
                    .textFieldStyle(FieldStyle())
                    .keyboardType(.numberPad).textContentType(.oneTimeCode)
                    .font(.system(size: 24, weight: .semibold, design: .monospaced))
                    .focused($focused)
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: "Verify", loading: model.loading, disabled: model.code.count < 4) {
                Task { await model.verify(api: app.api, app: app) }
            }
            Button("Send a new code") { Task { await model.resend(api: app.api, app: app) } }
                .font(.system(size: 14, weight: .medium)).foregroundStyle(MP.brand)
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
                        Label("What we read", systemImage: "heart.text.square.fill").font(.system(size: 14, weight: .semibold)).foregroundStyle(MP.ink)
                        ForEach(["Steps, distance and stairs", "Sleep and resting heart rate", "Walking speed, step length and steadiness", "Workouts and exercise minutes"], id: \.self) { line in
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)).foregroundStyle(MP.brand).padding(.top, 3)
                                Text(line).font(.system(size: 14)).foregroundStyle(MP.body)
                            }
                        }
                        Text("We never write to Health. Turn any type off on the next screen and we simply won't read it.")
                            .font(.system(size: 12.5)).foregroundStyle(MP.muted).padding(.top, 4)
                    }
                }
                if !(app.me?.features.appleHealth ?? true) {
                    ErrorBanner(text: "This server isn't connected to Junction yet, so Health data has nowhere to go. You can skip and connect later.")
                }
                if let failure { ErrorBanner(text: failure) }
                if app.health.state == .connected {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow)
                        Text("Connected — first sync is running").font(.system(size: 14, weight: .semibold)).foregroundStyle(MP.ink)
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
                Button("Skip for now") { model.go(.wearable) }
                    .font(.system(size: 14, weight: .medium)).foregroundStyle(MP.brand)
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
                        Text(b).font(.system(size: 12.5, weight: .semibold)).foregroundStyle(MP.body)
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Capsule().fill(MP.soft))
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
            Button(app.health.state == .connected ? "Not now" : "Skip") { model.go(.done) }
                .font(.system(size: 14, weight: .medium)).foregroundStyle(MP.brand)
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
        VStack(alignment: .leading, spacing: 0) {
            Spacer()
            VStack(alignment: .leading, spacing: 14) {
                Image(systemName: "checkmark.circle.fill").font(.system(size: 44)).foregroundStyle(MP.riskLow)
                Text("You're set, \(app.me?.patient.firstName ?? "there").").title(32)
                Text(app.me?.patient.isRecovery == true
                     ? "When a task is ready we'll text you. Do it right there in Messages, or open the app — either way your care team sees it."
                     : "Your portfolio fills in as your data arrives. When your care team asks for something we'll text you, and you can answer right there or in the app.")
                    .font(.system(size: 16)).foregroundStyle(MP.body).lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 22)
            Spacer()
            PrimaryButton(title: "Open MedPull", icon: "arrow.right") { app.enterHome() }
                .padding(.horizontal, 22).padding(.bottom, 18)
        }
    }
}

private struct PathStep: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        StepScaffold(eyebrow: "Step 2 of 5", title: "How are you joining?",
                     subtitle: "\(model.hospital?.name ?? "Your hospital") follows patients with and without a surgery.") {
            VStack(spacing: 12) {
                pathCard(icon: "person.crop.circle.badge.plus", title: "I'm a patient here",
                         detail: "Join as a general patient. Your activity, sleep and vitals build a portfolio your care team can see.") {
                    model.choose(.joinGeneral)
                }
                pathCard(icon: "bandage.fill", title: "I'm recovering from surgery",
                         detail: "Find the record your surgical team already created, or add your operation and date.") {
                    model.choose(.findRecord)
                }
            }
        } footer: {
            Button("Different hospital") { model.go(.hospital) }
                .font(.system(size: 14, weight: .medium)).foregroundStyle(MP.brand)
        }
    }

    private func pathCard(icon: String, title: String, detail: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: icon).font(.system(size: 22, weight: .semibold)).foregroundStyle(MP.brand)
                        .frame(width: 40, height: 40)
                        .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(MP.brandTint))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).font(.system(size: 16, weight: .semibold)).foregroundStyle(MP.ink)
                        Text(detail).font(.system(size: 13.5)).foregroundStyle(MP.muted).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(MP.faint).padding(.top, 10)
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

    var body: some View {
        StepScaffold(eyebrow: "Step 3 of 5", title: surgical ? "Your surgery" : "About you",
                     subtitle: surgical
                        ? "We'll create your record at \(model.hospital?.name ?? "the hospital") with the operation you had."
                        : "This creates your record at \(model.hospital?.name ?? "the hospital"). Nothing else is needed to get started.") {
            VStack(spacing: 14) {
                TextField("Full name", text: $model.name)
                    .textFieldStyle(FieldStyle()).textContentType(.name).autocorrectionDisabled()
                TextField("Mobile number", text: $model.phone)
                    .textFieldStyle(FieldStyle()).textContentType(.telephoneNumber).keyboardType(.phonePad)
                Toggle(isOn: $hasDOB) {
                    Text("Add date of birth").font(.system(size: 15, weight: .medium)).foregroundStyle(MP.ink)
                }
                .tint(MP.brand)
                .onChange(of: hasDOB) { _, on in model.dateOfBirth = on ? dob : nil }
                if hasDOB {
                    DatePicker("Date of birth", selection: $dob, in: ...Date(), displayedComponents: .date)
                        .datePickerStyle(.compact)
                        .onChange(of: dob) { _, d in model.dateOfBirth = d }
                }
                if surgical {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Operation").eyebrow()
                        FlowProcedures(procedures: model.procedures, selected: $model.procedure)
                        DatePicker("Surgery date", selection: $model.surgeryDate, in: ...Date(), displayedComponents: .date)
                            .datePickerStyle(.compact)
                            .font(.system(size: 15, weight: .medium))
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
            Button("Back") { model.go(.path) }
                .font(.system(size: 14, weight: .medium)).foregroundStyle(MP.brand)
        }
        .task { if surgical { await model.loadProcedures(api: app.api) } }
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
