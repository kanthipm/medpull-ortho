import SwiftUI

/// The athlete's card in Profile: status, team, the numbers behind the
/// benchmarks, units and cycle tracking, and the way to join or leave an
/// organisation.
struct SportsProfileCard: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var editing = false
    @State private var joining = false
    @State private var leaving = false
    @State private var confirmLeave = false
    @State private var error: String?

    private var profile: SportsProfile? { app.sportsHome?.profile ?? app.me?.sports }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    CardHeader("MedPull Sports", actionTitle: "Edit") { editing = true }
                    if let p = profile {
                        row("Status", p.statusLabel, tone: Availability.tone(p.status))
                        InsetDivider(leading: 16)
                        row("Sport", p.sportLabel)
                        InsetDivider(leading: 16)
                        row("Team", p.teamLine ?? "Just me")
                        if let pos = p.position {
                            InsetDivider(leading: 16)
                            row("Position", [pos, p.jersey.map { "#\($0)" }, p.classYear].compactMap { $0 }.joined(separator: MP.dot))
                        }
                        InsetDivider(leading: 16)
                        row("Level", p.levelLabel)
                        InsetDivider(leading: 16)
                        row("Height", SportsUnits.height(cm: p.heightCm, imperial: p.isImperial) ?? "—")
                        InsetDivider(leading: 16)
                        row("Weight", SportsUnits.weight(kg: p.weightKg, imperial: p.isImperial) ?? "—")
                        if p.wingspanCm != nil || p.standingReachCm != nil {
                            InsetDivider(leading: 16)
                            row("Wingspan / reach", [SportsUnits.length(cm: p.wingspanCm, imperial: p.isImperial),
                                                     SportsUnits.length(cm: p.standingReachCm, imperial: p.isImperial)]
                                .compactMap { $0 }.joined(separator: " / "))
                        }
                        InsetDivider(leading: 16)
                        row("Units", p.isImperial ? "ft, lb, in" : "cm, kg")
                        if p.sex == "F" {
                            InsetDivider(leading: 16)
                            row("Cycle tracking", p.cycleTracking ? "On" : "Off")
                        }
                        if !p.staff.isEmpty {
                            InsetDivider(leading: 16)
                            VStack(alignment: .leading, spacing: 6) {
                                Text("Your staff").mpFont(.labelMedium).foregroundStyle(MP.muted)
                                ForEach(p.staff) { s in
                                    HStack {
                                        Text(s.name).mpFont(.copyLarge).foregroundStyle(MP.ink)
                                        Spacer()
                                        Text(s.roleLabel).mpFont(.copy).foregroundStyle(MP.muted)
                                    }
                                }
                            }
                            .padding(.horizontal, 16).padding(.vertical, 10)
                        }
                        InsetDivider(leading: 16)
                        if p.org == nil {
                            Button { joining = true } label: {
                                Text("Join a school or club").mpFont(.copyLargeMedium).foregroundStyle(MP.brandInk)
                                    .padding(.horizontal, 16).frame(minHeight: 48)
                            }
                            .buttonStyle(.mpRow)
                        } else {
                            Button { confirmLeave = true } label: {
                                HStack {
                                    Text("Leave \(p.org?.shortName ?? "the team")").mpFont(.copyLargeMedium).foregroundStyle(MP.riskHigh)
                                    Spacer()
                                    if leaving { ProgressView().tint(MP.muted) }
                                }
                                .padding(.horizontal, 16).frame(minHeight: 48)
                            }
                            .buttonStyle(.mpRow)
                        }
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding()
                    }
                }
                .padding(.bottom, 4)
            }
            .clipShape(MP.surfaceShape)
            if let error { ErrorBanner(text: error) }
            Text(profile?.org == nil
                 ? "On your own, nobody else sees your numbers. Join a program and its staff see readiness, load and your injury plan; they never see your messages to the coach."
                 : "Your staff see readiness, load, availability and your injury plan. Leaving keeps your data and stops the sharing.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
        }
        .sheet(isPresented: $editing) { SportsProfileEditSheet() }
        .sheet(isPresented: $joining) { JoinOrgSheet() }
        .confirmationDialog("Leave the organisation?", isPresented: $confirmLeave, titleVisibility: .visible) {
            Button("Leave", role: .destructive) { leave() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Your staff stop seeing your numbers. Your data stays yours.")
        }
        .mpErrorFeedback(error)
    }

    private func row(_ label: String, _ value: String, tone: MP.Tone? = nil) -> some View {
        HStack(spacing: 12) {
            Text(label).mpFont(.copyLarge).foregroundStyle(MP.ink)
            Spacer(minLength: 12)
            if let tone {
                StatusPill(text: value, tone: tone)
            } else {
                Text(value).mpFont(.copyLarge).foregroundStyle(MP.muted).multilineTextAlignment(.trailing)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(minHeight: 48)
        .accessibilityElement(children: .combine)
    }

    private func leave() {
        leaving = true
        error = nil
        Task {
            defer { leaving = false }
            do {
                _ = try await app.api.sportsLeaveOrg()
                await app.refreshMe(surface: false)
                await app.refreshSports(startDay: false)
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// Edit the athlete profile: position, number, level, body numbers, units,
/// dominant side, cycle tracking, and the status note the staff read.
struct SportsProfileEditSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var position = ""
    @State private var jersey = ""
    @State private var classYear = ""
    @State private var level = "club"
    @State private var units = "imperial"
    @State private var heightFt = ""
    @State private var heightIn = ""
    @State private var heightCm = ""
    @State private var weight = ""
    @State private var wingspan = ""
    @State private var reach = ""
    @State private var dominant = "right"
    @State private var cycle = false
    @State private var statusNote = ""
    @State private var saving = false
    @State private var error: String?

    private var catalog: SportsCatalog? { app.sportsCatalog }
    private var imperial: Bool { units == "imperial" }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let positions = catalog?.positions, !positions.isEmpty {
                        labelled("Position") {
                            WrapChips(options: positions, labels: Dictionary(uniqueKeysWithValues: positions.map { ($0, $0) }),
                                      value: Binding(get: { position.isEmpty ? nil : .string(position) }, set: { position = $0?.stringValue ?? "" }))
                        }
                    }
                    HStack(spacing: 10) {
                        field("Number", $jersey, keyboard: .numberPad)
                        if let years = catalog?.classYears, !years.isEmpty {
                            Menu {
                                ForEach(years, id: \.self) { y in Button(y) { classYear = y } }
                                Button("None") { classYear = "" }
                            } label: {
                                HStack {
                                    Text(classYear.isEmpty ? "Class year" : classYear).mpFont(.copyLarge)
                                        .foregroundStyle(classYear.isEmpty ? MP.muted : MP.ink)
                                    Spacer()
                                    Image(systemName: "chevron.up.chevron.down").font(.systemGlyphs(12)).foregroundStyle(MP.muted)
                                }
                                .padding(.horizontal, 16).frame(minHeight: 52)
                                .background(MP.thumbShape.fill(MP.panel.opacity(0.8)))
                                .overlay(MP.thumbShape.strokeBorder(MP.lineStrong.opacity(0.75), lineWidth: 1))
                            }
                        }
                    }
                    if let levels = catalog?.levels {
                        labelled("Level") {
                            WrapChips(options: levels.map(\.key), labels: Dictionary(uniqueKeysWithValues: levels.map { ($0.key, $0.label) }),
                                      value: Binding(get: { .string(level) }, set: { if let l = $0?.stringValue { level = l } }))
                        }
                    }
                    HStack {
                        Text("Units").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        Spacer()
                        Picker("Units", selection: $units) {
                            Text("ft, lb").tag("imperial")
                            Text("cm, kg").tag("metric")
                        }
                        .pickerStyle(.segmented).frame(maxWidth: 180)
                    }
                    HStack(spacing: 10) {
                        if imperial {
                            field("Height ft", $heightFt, keyboard: .numberPad)
                            field("in", $heightIn, keyboard: .numberPad)
                            field("Weight lb", $weight, keyboard: .decimalPad)
                        } else {
                            field("Height cm", $heightCm, keyboard: .decimalPad)
                            field("Weight kg", $weight, keyboard: .decimalPad)
                        }
                    }
                    HStack(spacing: 10) {
                        field(imperial ? "Wingspan in" : "Wingspan cm", $wingspan, keyboard: .decimalPad)
                        field(imperial ? "Reach in" : "Reach cm", $reach, keyboard: .decimalPad)
                    }
                    labelled("Dominant side") {
                        WrapChips(options: ["right", "left"], labels: ["right": "Right", "left": "Left"],
                                  value: Binding(get: { .string(dominant) }, set: { if let s = $0?.stringValue { dominant = s } }))
                    }
                    if app.me?.sports?.sex == "F" {
                        Card(padding: 0) {
                            Toggle(isOn: $cycle) { Text("Track my cycle").mpFont(.copyLarge).foregroundStyle(MP.ink) }
                                .tint(MP.brand).padding(.horizontal, 16).padding(.vertical, 10)
                        }
                    }
                    TextField("A note for your staff (optional)", text: $statusNote,
                              prompt: Text("A note for your staff (optional)").foregroundColor(MP.muted), axis: .vertical)
                        .lineLimit(1...3).textFieldStyle(FieldStyle())
                    if let error { ErrorBanner(text: error) }
                    PrimaryButton(title: "Save", icon: "checkmark", loading: saving) { save() }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientScreen()
            .navigationTitle("Athlete profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium) }
            }
            .onAppear(perform: seed)
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private func labelled<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label).mpFont(.labelMedium).foregroundStyle(MP.muted)
            content()
        }
    }

    private func field(_ label: String, _ text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        TextField(label, text: text, prompt: Text(label).foregroundColor(MP.muted))
            .textFieldStyle(FieldStyle()).keyboardType(keyboard)
    }

    private func seed() {
        guard let p = app.sportsHome?.profile ?? app.me?.sports else { return }
        position = p.position ?? ""
        jersey = p.jersey ?? ""
        classYear = p.classYear ?? ""
        level = p.level
        units = p.units
        dominant = p.dominantSide ?? "right"
        cycle = p.cycleTracking
        statusNote = p.statusNote ?? ""
        if let cm = p.heightCm {
            let inches = cm / 2.54
            heightFt = String(Int(inches / 12))
            heightIn = String(Int((inches - Double(Int(inches / 12)) * 12).rounded()))
            heightCm = String(format: "%.0f", cm)
        }
        if let kg = p.weightKg { weight = p.isImperial ? String(format: "%.0f", kg / 0.4536) : String(format: "%.1f", kg) }
        if let w = p.wingspanCm { wingspan = p.isImperial ? String(format: "%.1f", w / 2.54) : String(format: "%.0f", w) }
        if let r = p.standingReachCm { reach = p.isImperial ? String(format: "%.1f", r / 2.54) : String(format: "%.0f", r) }
    }

    private func save() {
        saving = true
        error = nil
        var body = APIClient.SportsProfilePatch()
        body.position = position.isEmpty ? nil : position
        body.jersey = jersey.isEmpty ? nil : jersey
        body.classYear = classYear.isEmpty ? nil : classYear
        body.level = level
        body.units = units
        body.dominantSide = dominant
        body.cycleTracking = cycle
        body.statusNote = statusNote
        if imperial {
            if let ft = Double(heightFt) { body.heightCm = (ft * 12 + (Double(heightIn) ?? 0)) * 2.54 }
            if let lb = Double(weight) { body.weightKg = lb * 0.4536 }
            if let w = Double(wingspan) { body.wingspanCm = w * 2.54 }
            if let r = Double(reach) { body.standingReachCm = r * 2.54 }
        } else {
            if let cm = Double(heightCm) { body.heightCm = cm }
            if let kg = Double(weight) { body.weightKg = kg }
            if let w = Double(wingspan) { body.wingspanCm = w }
            if let r = Double(reach) { body.standingReachCm = r }
        }
        Task {
            defer { saving = false }
            do {
                _ = try await app.api.sportsPatchProfile(body)
                await app.refreshMe(surface: false)
                await app.refreshSports(startDay: false)
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// Join a school or club from Profile, after signing up as "just me".
struct JoinOrgSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var orgs: [SportsOrg] = []
    @State private var org: SportsOrg?
    @State private var team: SportsTeam?
    @State private var code = ""
    @State private var position = ""
    @State private var saving = false
    @State private var error: String?

    private var sport: String { app.me?.sports?.sport ?? "basketball" }
    private var filtered: [SportsOrg] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return q.isEmpty ? orgs : orgs.filter { $0.name.lowercased().contains(q) || $0.city.lowercased().contains(q) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let org {
                        Text(org.name).title(MPSize.displayS)
                        let teams = org.teams.filter { $0.sport == sport }
                        if !teams.isEmpty {
                            WrapChips(options: teams.map(\.id), labels: Dictionary(uniqueKeysWithValues: teams.map { ($0.id, $0.name) }),
                                      value: Binding(get: { team.map { .string($0.id) } }, set: { v in team = teams.first { $0.id == v?.stringValue } }))
                        }
                        if let positions = app.sportsCatalog?.positions, !positions.isEmpty {
                            WrapChips(options: positions, labels: Dictionary(uniqueKeysWithValues: positions.map { ($0, $0) }),
                                      value: Binding(get: { position.isEmpty ? nil : .string(position) }, set: { position = $0?.stringValue ?? "" }))
                        }
                        if org.requiresCode {
                            TextField("Join code", text: $code, prompt: Text("Join code from your staff").foregroundColor(MP.muted))
                                .textFieldStyle(FieldStyle()).textInputAutocapitalization(.characters).autocorrectionDisabled()
                        }
                        if let error { ErrorBanner(text: error) }
                        PrimaryButton(title: "Join", icon: "link", loading: saving,
                                      disabled: org.requiresCode && code.trimmingCharacters(in: .whitespaces).count < 4) { join() }
                        Button("Different organisation") { self.org = nil }.buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                    } else {
                        SportsSearchField(text: $query, placeholder: "Search schools and clubs")
                        if orgs.isEmpty {
                            ProgressView().frame(maxWidth: .infinity).padding()
                        } else {
                            Card(padding: 0) {
                                VStack(spacing: 0) {
                                    ForEach(filtered) { o in
                                        Button { org = o; team = o.teams.first { $0.sport == sport } } label: {
                                            ListRow(o.name, subtitle: "\(o.kindLabel)\(MP.dot)\(o.city), \(o.state)",
                                                    symbol: o.kind == "pro" ? "trophy.fill" : "building.columns.fill",
                                                    family: o.kind == "pro" ? .violet : .blue) { EmptyView() }
                                        }
                                        .buttonStyle(.mpRow)
                                        if o.id != filtered.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                                    }
                                }
                                .clipShape(MP.surfaceShape)
                            }
                        }
                    }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientScreen()
            .navigationTitle("Join a program")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium) }
            }
            .task { orgs = (try? await app.api.sportsOrgs()) ?? [] }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private func join() {
        guard let org else { return }
        saving = true
        error = nil
        Task {
            defer { saving = false }
            do {
                _ = try await app.api.sportsJoinOrg(.init(orgId: org.id, teamId: team?.id,
                                                          joinCode: code.isEmpty ? nil : code.trimmingCharacters(in: .whitespaces).uppercased(),
                                                          position: position.isEmpty ? nil : position))
                await app.refreshMe(surface: false)
                await app.refreshSports(startDay: false)
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// On a hospital record or a personal space: the way over to MedPull
/// Sports. Both actions sign this account out first; the email and
/// password get back in.
struct SportsEntryCard: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var working = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 14) {
                        IconTile("figure.basketball", family: .indigo, size: 40)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 8) {
                                Text("MedPull Sports").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text("Athletes").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                                    .padding(.horizontal, 8).padding(.vertical, 3)
                                    .background(MP.capsuleShape.fill(MP.brandTint))
                            }
                            Text("Performance tests against your level, game recovery, injury plans with the real return gates, with your team's staff or on your own.")
                                .mpFont(.label).foregroundStyle(MP.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(16)
                    InsetDivider(leading: 16)
                    Button { go(login: true) } label: {
                        HStack {
                            Text("Sign in as an athlete").mpFont(.copyLargeMedium).foregroundStyle(MP.brandInk)
                            Spacer()
                            if working { ProgressView().tint(MP.muted) }
                        }
                        .padding(.horizontal, 16).frame(minHeight: 48)
                    }
                    .buttonStyle(.mpRow)
                    .disabled(working)
                    InsetDivider(leading: 16)
                    Button { go(login: false) } label: {
                        Text("Set up an athlete account").mpFont(.copyLargeMedium).foregroundStyle(MP.brandInk)
                            .padding(.horizontal, 16).frame(minHeight: 48)
                    }
                    .buttonStyle(.mpRow)
                    .disabled(working)
                }
                .padding(.bottom, 4)
            }
            .clipShape(MP.surfaceShape)
            Text("Either one signs this account out first. Your email and password get you back in any time.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
        }
    }

    private func go(login: Bool) {
        working = true
        Task {
            await app.switchToSports(login: login)
            working = false
            dismiss()
        }
    }
}
