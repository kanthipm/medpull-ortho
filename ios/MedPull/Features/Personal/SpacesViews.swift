import SwiftUI

/// Profile's personal-tier cards: the spaces a person can switch between
/// (a hospital record and their own), and the personal space's own
/// settings: plan, goal, morning text, data export.

// MARK: - Spaces

struct SpacesCard: View {
    @Environment(AppModel.self) private var app
    @State private var addingSpace = false
    @State private var linkingHospital = false

    private var profiles: [SpaceProfile] { app.me?.profiles ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    CardHeader("Spaces")
                    ForEach(profiles) { p in
                        Button {
                            Task { await app.switchSpace(to: p) }
                        } label: {
                            HStack(spacing: 14) {
                                IconTile(p.isPersonal ? "sparkles" : "building.2.fill",
                                         family: p.isPersonal ? .teal : .blue)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(p.label).mpFont(.copyLarge).foregroundStyle(MP.ink)
                                    Text(p.detail).mpFont(.label).foregroundStyle(MP.muted)
                                }
                                Spacer(minLength: 8)
                                if p.current {
                                    StatusPill(text: "Here now", tone: .brand)
                                } else if app.switching {
                                    ProgressView().controlSize(.small)
                                } else {
                                    Text("Switch").mpFont(.copyMedium).foregroundStyle(MP.brandInk)
                                }
                            }
                            .padding(.horizontal, 16).padding(.vertical, 10)
                            .frame(minHeight: 48)
                        }
                        .buttonStyle(.mpRow)
                        .disabled(p.current || app.switching)
                        .accessibilityElement(children: .combine)
                        InsetDivider()
                    }
                    if let me = app.me, me.otherSpace == nil {
                        if me.isPersonal {
                            actionRow("Add my hospital", icon: "building.2.fill", family: .blue) {
                                linkingHospital = true
                            }
                        } else {
                            actionRow("Add a personal space", icon: "sparkles", family: .teal) {
                                addingSpace = true
                            }
                        }
                    }
                }
                .padding(.bottom, 4)
            }
            .clipShape(MP.surfaceShape)
            Text(app.isPersonal
                 ? "Your personal space is yours alone. Add your hospital and its care team sees their record, never this one; your watch feeds both."
                 : "A personal space adds readiness, training load, sleep debt and a coach on the same watch data. Your care team never sees it.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
        }
        .sheet(isPresented: $addingSpace) { AddSpaceSheet() }
        .sheet(isPresented: $linkingHospital) { LinkHospitalSheet() }
    }

    private func actionRow(_ title: String, icon: String, family: MP.Category,
                           action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                IconTile(icon, family: family)
                Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.brandInk)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 48)
        }
        .buttonStyle(.mpRow)
    }
}

/// From a hospital record: open a personal space paired with it.
struct AddSpaceSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var goal = "everyday"
    @State private var sport = ""
    @State private var working = false
    @State private var error: String?

    private let goals: [(String, String, MP.Category, String)] = [
        ("performance", "figure.run", .teal, "Train and perform"),
        ("recovery", "cross.case.fill", .violet, "Recover from an injury or surgery"),
        ("sleep", "bed.double.fill", .indigo, "Sleep and recover better"),
        ("everyday", "heart.fill", .blue, "Everyday health"),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Your own space").title(MPSize.displayS)
                    Text("Readiness, training load, sleep debt and a coach, on the same watch data your care team follows. Fourteen days free, then a subscription. Your clinicians never see this space.")
                        .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("What do you want from it?").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    VStack(spacing: 8) {
                        ForEach(goals, id: \.0) { key, icon, family, title in
                            Chip(label: title, selected: goal == key) { goal = key }
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    if goal == "performance" {
                        TextField("Sport", text: $sport, prompt: Text("Sport (running, cycling…)").foregroundColor(MP.muted))
                            .textFieldStyle(FieldStyle()).autocorrectionDisabled()
                    }
                    if let error { ErrorBanner(text: error) }
                    PrimaryButton(title: "Open my space", icon: "sparkles", loading: working) { create() }
                    PersonalGuardrail()
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .ambientScreen()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private func create() {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                try await app.addPersonalSpace(.init(
                    goal: goal, sport: goal == "performance" ? sport : nil, weeklyTargetMinutes: nil,
                    sleepTargetHours: nil, injury: nil,
                    units: Locale.current.measurementSystem == .metric ? "metric" : "imperial",
                    smsBriefs: true, deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// From a personal space: join a hospital's programme, keeping the space.
/// Find the record the clinic made, or start a new one there.
struct LinkHospitalSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var hospitals: [Hospital] = []
    @State private var hospital: Hospital?
    @State private var mode = "enroll"
    @State private var name = ""
    @State private var candidates: [Candidate] = []
    @State private var selected: Candidate?
    @State private var hadSurgery = false
    @State private var procedures: [Procedure] = []
    @State private var procedure: Procedure?
    @State private var surgeryDate = Calendar.current.date(byAdding: .day, value: -7, to: Date())!
    @State private var working = false
    @State private var error: String?
    @State private var codeNeeded: (Int, String)?
    @State private var code = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Add your hospital").title(MPSize.displayS)
                    Text("Your care team sees their record of you and your watch data, never this space. Pick the hospital, then find the record they made or start one.")
                        .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if let codeNeeded {
                        codeCard(codeNeeded)
                    } else {
                        hospitalPicker
                        if hospital != nil { recordForm }
                    }
                    if let error { ErrorBanner(text: error) }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .ambientScreen()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
            .task {
                hospitals = (try? await app.api.hospitals()) ?? []
                name = app.me?.patient.name ?? ""
            }
            .task(id: "\(hospital?.id ?? "")|\(name)|\(mode)") {
                guard mode == "enroll", let hospital, name.count >= 2 else { candidates = []; return }
                try? await Task.sleep(for: .milliseconds(350))
                guard !Task.isCancelled else { return }
                candidates = (try? await app.api.search(hospitalId: hospital.id, name: name, phone: nil)) ?? []
                if candidates.count == 1 { selected = candidates[0] }
            }
            .task(id: hadSurgery) {
                if hadSurgery, procedures.isEmpty { procedures = (try? await app.api.procedures()) ?? [] }
            }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private var hospitalPicker: some View {
        Card(padding: 0) {
            VStack(spacing: 0) {
                if hospitals.isEmpty {
                    ProgressView().frame(maxWidth: .infinity).padding()
                }
                ForEach(hospitals) { h in
                    Button { hospital = h; selected = nil } label: {
                        HStack(spacing: 14) {
                            IconTile("building.2.fill", family: .blue)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(h.name).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text("\(h.city), \(h.state)").mpFont(.label).foregroundStyle(MP.muted)
                            }
                            Spacer()
                            Image(systemName: hospital?.id == h.id ? "checkmark.circle.fill" : "circle")
                                .font(.systemGlyphs(20)).foregroundStyle(hospital?.id == h.id ? MP.ink : MP.lineStrong)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)
                    }
                    .buttonStyle(.mpRow)
                    if h.id != hospitals.last?.id { InsetDivider() }
                }
            }
        }
        .clipShape(MP.surfaceShape)
    }

    @ViewBuilder private var recordForm: some View {
        Picker("How", selection: $mode) {
            Text("Find my record").tag("enroll")
            Text("I’m new there").tag("join")
        }
        .pickerStyle(.segmented)
        if mode == "enroll" {
            TextField("Name on the record", text: $name,
                      prompt: Text("Name on the record").foregroundColor(MP.muted))
                .textFieldStyle(FieldStyle()).autocorrectionDisabled()
            ForEach(candidates) { c in
                Button { selected = c } label: {
                    HStack(spacing: 12) {
                        Image(systemName: selected?.id == c.id ? "checkmark.circle.fill" : "circle")
                            .font(.systemGlyphs(22)).foregroundStyle(selected?.id == c.id ? MP.ink : MP.lineStrong)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(c.displayName).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Text("\(c.procedureDisplay)\(MP.dot)\(c.surgeryMonth)").mpFont(.label).foregroundStyle(MP.body)
                        }
                        Spacer()
                    }
                    .padding(14)
                    .glassSurface(MP.surfaceShape, solid: true)
                    .overlay(MP.surfaceShape.strokeBorder(selected?.id == c.id ? MP.ink : .clear, lineWidth: 1.5))
                }
                .buttonStyle(.plain)
            }
            if candidates.isEmpty, name.count >= 2 {
                Text("No record under that name yet. Ask the clinic which name they used, or start a new record.")
                    .mpFont(.copy).foregroundStyle(MP.body)
            }
            PrimaryButton(title: "That’s me — link it", icon: "link", loading: working, disabled: selected == nil) { submit() }
        } else {
            Card(padding: 0) {
                Toggle(isOn: $hadSurgery) {
                    Text("I’m recovering from an operation").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                }
                .tint(MP.brand)
                .padding(.horizontal, 16).padding(.vertical, 10)
            }
            if hadSurgery {
                FlowChips(options: procedures.map(\.id),
                          labels: Dictionary(uniqueKeysWithValues: procedures.map { ($0.id, $0.label) }),
                          value: Binding(get: { procedure.map { AnswerValue.string($0.id) } },
                                         set: { v in procedure = procedures.first { $0.id == v?.stringValue } }))
                DatePicker("Surgery date", selection: $surgeryDate, in: ...Date(), displayedComponents: .date)
                    .datePickerStyle(.compact).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
            }
            PrimaryButton(title: "Join \(hospital?.name.split(separator: " ").first.map(String.init) ?? "the hospital")",
                          icon: "arrow.right", loading: working, disabled: hadSurgery && procedure == nil) { submit() }
        }
    }

    private func codeCard(_ pending: (Int, String)) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("The record has a different number on file. We texted a code to \(pending.1); enter it to prove the record is yours.")
                .mpFont(.copy).foregroundStyle(MP.body).fixedSize(horizontal: false, vertical: true)
            TextField("6-digit code", text: $code, prompt: Text("6-digit code").foregroundColor(MP.muted))
                .textFieldStyle(FieldStyle()).keyboardType(.numberPad).textContentType(.oneTimeCode)
            PrimaryButton(title: "Verify and link", loading: working, disabled: code.count < 4) {
                verifyCode(pending.0)
            }
        }
    }

    private func submit() {
        guard let hospital else { return }
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                let r = try await app.api.linkHospital(.init(
                    mode: mode, hospitalId: hospital.id, patientId: selected?.patientId,
                    hadSurgery: hadSurgery, procedureType: hadSurgery ? procedure?.id : nil,
                    surgeryDate: hadSurgery ? Dates.dayString(surgeryDate) : nil,
                    deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
                if r.status == "verification_required", let id = r.verificationId {
                    codeNeeded = (id, r.phoneMasked ?? "the number on file")
                } else if let token = r.sessionToken, let me = r.me {
                    // Linked. The person lands in the hospital record; their
                    // personal space is one switch away.
                    app.adoptSession(token: token, me: me)
                    await app.refreshAll()
                    dismiss()
                }
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    private func verifyCode(_ id: Int) {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                // The code proves the chart; the clinic verify route issues a
                // session on it, after which linking is an open-record call.
                let r = try await app.api.verify(verificationId: id, code: code)
                guard let token = r.sessionToken, let me = r.me, let hospital else { return }
                let personalToken = app.api.token
                app.api.token = token
                _ = me
                app.api.token = personalToken
                let linked = try await app.api.linkHospital(.init(
                    mode: "enroll", hospitalId: hospital.id, patientId: selected?.patientId,
                    hadSurgery: false, procedureType: nil, surgeryDate: nil,
                    deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
                if let t = linked.sessionToken, let m = linked.me {
                    app.adoptSession(token: t, me: m)
                    await app.refreshAll()
                }
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

// MARK: - The personal space's own card

struct PersonalCard: View {
    @Environment(AppModel.self) private var app
    @State private var managing = false
    @State private var exporting = false
    @State private var exportURL: URL?
    @State private var error: String?
    @State private var smsBriefs: Bool = true
    @State private var loadedPrefs = false

    private var profile: PersonalProfile? { app.dashboard?.profile }
    private var state: SubscriptionState? { app.dashboard?.subscription ?? app.me?.subscription }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    CardHeader("MedPull Personal")
                    if let state {
                        row("Plan", state.headline, icon: "creditcard.fill", family: .blue)
                        InsetDivider()
                    }
                    if let profile {
                        Menu {
                            ForEach([("performance", "Train and perform"), ("recovery", "Recover from an injury or surgery"),
                                     ("sleep", "Sleep and recover better"), ("everyday", "Everyday health")], id: \.0) { key, label in
                                Button(label) { setGoal(key) }
                            }
                        } label: {
                            rowLabel("Goal", profile.goalLabel, icon: "target", family: .teal, chevron: true)
                        }
                        InsetDivider()
                        Toggle(isOn: $smsBriefs) {
                            HStack(spacing: 14) {
                                IconTile("message.fill", family: .blue)
                                Text("Morning brief by text").mpFont(.copyLarge).foregroundStyle(MP.ink)
                            }
                        }
                        .tint(MP.brand)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                        .onChange(of: smsBriefs) { _, on in
                            guard loadedPrefs else { return }
                            Task { _ = try? await app.api.patchPersonalProfile(.init(smsBriefs: on)) }
                        }
                        .onAppear {
                            smsBriefs = profile.smsBriefs
                            loadedPrefs = true
                        }
                        InsetDivider()
                    }
                    Button { managing = true } label: {
                        rowLabel("Manage subscription", nil, icon: "arrow.up.forward.app", family: .violet, chevron: true)
                    }
                    .buttonStyle(.mpRow)
                    InsetDivider()
                    Button { export() } label: {
                        HStack(spacing: 14) {
                            IconTile("square.and.arrow.up", family: .indigo)
                            Text("Export my data").mpFont(.copyLarge).foregroundStyle(MP.brandInk)
                            Spacer()
                            if exporting { ProgressView().controlSize(.small) }
                        }
                        .padding(.horizontal, 16).frame(minHeight: 48)
                    }
                    .buttonStyle(.mpRow)
                    .disabled(exporting)
                }
                .padding(.bottom, 4)
            }
            .clipShape(MP.surfaceShape)
            if let error { ErrorBanner(text: error) }
            Text("Your data is yours: the export is a JSON file with your profile, readouts, log and a year of readings. Personal files live in their own storage, apart from any hospital’s.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
        }
        .sheet(isPresented: $managing) { PaywallView(mode: .manage) }
        .sheet(item: $exportURL) { url in
            ShareSheet(items: [url])
        }
    }

    private func row(_ label: String, _ value: String, icon: String, family: MP.Category) -> some View {
        rowLabel(label, value, icon: icon, family: family, chevron: false)
    }

    private func rowLabel(_ label: String, _ value: String?, icon: String, family: MP.Category,
                          chevron: Bool) -> some View {
        HStack(spacing: 14) {
            IconTile(icon, family: family)
            Text(label).mpFont(.copyLarge).foregroundStyle(MP.ink)
            Spacer(minLength: 12)
            if let value {
                Text(value).mpFont(.copyLarge).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.trailing)
            }
            if chevron {
                Image(systemName: "chevron.right").font(.systemGlyphs(13, weight: .semibold))
                    .foregroundStyle(MP.muted).accessibilityHidden(true)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(minHeight: 48)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private func setGoal(_ key: String) {
        Task {
            do {
                _ = try await app.api.patchPersonalProfile(.init(goal: key))
                await app.refreshDashboard(startDay: true)
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    private func export() {
        exporting = true
        error = nil
        Task {
            defer { exporting = false }
            do {
                let r = try await app.api.exportPersonalData()
                if let link = r.url, let url = URL(string: link) {
                    exportURL = url
                } else {
                    // Inline data (no object store): write it to a temp file
                    // for the share sheet.
                    let data = try await app.api.exportPersonalDataRaw()
                    let file = FileManager.default.temporaryDirectory
                        .appendingPathComponent("medpull-export-\(Int(Date().timeIntervalSince1970)).json")
                    try data.write(to: file)
                    exportURL = file
                }
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// UIKit's share sheet, for the export file.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
