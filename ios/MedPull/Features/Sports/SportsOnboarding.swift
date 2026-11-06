import SwiftUI

/// The MedPull Sports path through onboarding: the sport, the organisation
/// (or "just me"), the team and position, then the athlete's own numbers.
/// The login step before these is shared with MedPull Personal; the Health
/// and wearable steps after them are shared with everyone.

// MARK: - Sport

struct SportStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    private let sports: [(String, String, String, MP.Category, String)] = [
        ("basketball", "Basketball", "basketball.fill", .teal,
         "The combine battery, force-plate jumps, game and practice load, and the knee and ankle plans."),
        ("tennis", "Tennis", "tennis.racket", .blue,
         "Serve speed, agility and shoulder health, match load, and the elbow, wrist and shoulder plans."),
        ("soccer", "Soccer", "soccerball", .indigo,
         "Sprints, Yo-Yo and GPS load, and the hamstring, groin and ACL plans."),
    ]

    var body: some View {
        StepScaffold(eyebrow: model.eyebrow(.sport), title: "What do you play?",
                     subtitle: "The sport sets which tests, benchmarks, injuries and devices you see. You can add another later.") {
            VStack(spacing: 12) {
                ForEach(sports, id: \.0) { key, title, icon, family, detail in
                    let selected = model.sportKey == key
                    Button { model.sportKey = key } label: {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                                .font(.systemGlyphs(22, weight: .regular))
                                .foregroundStyle(selected ? MP.ink : MP.lineStrong)
                                .contentTransition(.symbolEffect(.replace))
                                .padding(.top, 10)
                            IconTile(icon, family: family, size: 40)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text(detail).mpFont(.label).foregroundStyle(MP.body)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(14)
                        .glassSurface(MP.surfaceShape, solid: true)
                        .overlay(MP.surfaceShape.strokeBorder(selected ? MP.ink : .clear, lineWidth: 1.5))
                        .contentShape(MP.surfaceShape)
                    }
                    .buttonStyle(CardPressStyle())
                    .accessibilityAddTraits(selected ? .isSelected : [])
                    .sensoryFeedback(.selection, trigger: selected) { _, new in new }
                }
            }
        } footer: {
            PrimaryButton(title: "Continue", icon: "arrow.right") {
                Task { await model.loadSportsCatalog(api: app.api) }
                model.go(.org)
            }
        }
    }
}

// MARK: - Organisation

struct OrgStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    var body: some View {
        StepScaffold(eyebrow: model.eyebrow(.org), title: "Who do you play for?",
                     subtitle: "Pick your school or club and your staff see your readiness, load and injury plan. On your own, it stays yours.") {
            VStack(spacing: 14) {
                Button {
                    model.org = nil
                    model.team = nil
                    model.go(.athlete)
                } label: {
                    Card {
                        HStack(alignment: .top, spacing: 14) {
                            IconTile("person.fill", family: .teal, size: 44)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Just me").mpFont(.ledeMedium).foregroundStyle(MP.ink)
                                Text("Nobody else sees your numbers. You can link a team later from Profile.")
                                    .mpFont(.copy).mpSecondary().lineSpacing(2)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right")
                                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                .padding(.top, 14).accessibilityHidden(true)
                        }
                    }
                    .contentShape(MP.surfaceShape)
                }
                .buttonStyle(CardPressStyle())
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(.isButton)

                SportsSearchField(text: $model.orgQuery, placeholder: "Search schools and clubs")
                if model.orgs.isEmpty {
                    if let error = model.error { ErrorBanner(text: error) } else { ProgressView().frame(maxWidth: .infinity).padding() }
                } else if model.filteredOrgs.isEmpty {
                    Card { EmptyRow(icon: "building.2", title: "No organisation matches", detail: "Try the city or part of the name. Or go on as just you.") }
                } else {
                    Card(padding: 0) {
                        VStack(spacing: 0) {
                            ForEach(model.filteredOrgs) { o in
                                Button {
                                    model.org = o
                                    model.team = o.teams.first { $0.sport == model.sportKey }
                                    model.go(.team)
                                } label: {
                                    HStack(spacing: 14) {
                                        ZStack(alignment: .bottomTrailing) {
                                            IconTile(o.kind == "pro" ? "trophy.fill" : o.kind == "college" ? "building.columns.fill" : "building.2.fill",
                                                     family: o.kind == "pro" ? .violet : .blue)
                                            if let accent = o.accent {
                                                Circle().fill(accent).frame(width: 12, height: 12)
                                                    .overlay(Circle().strokeBorder(MP.panel, lineWidth: 2))
                                                    .offset(x: 4, y: 4)
                                                    .accessibilityHidden(true)
                                            }
                                        }
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(o.name).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                                .multilineTextAlignment(.leading)
                                            Text([o.kindLabel, "\(o.city), \(o.state)", o.requiresCode ? "join code" : nil]
                                                .compactMap { $0 }.joined(separator: MP.dot))
                                                .mpFont(.label).foregroundStyle(MP.muted)
                                                .multilineTextAlignment(.leading)
                                        }
                                        Spacer(minLength: 8)
                                        Image(systemName: "chevron.right")
                                            .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                            .accessibilityHidden(true)
                                    }
                                    .padding(.horizontal, 16).padding(.vertical, 12)
                                }
                                .buttonStyle(.mpRow)
                                if o.id != model.filteredOrgs.last?.id { InsetDivider() }
                            }
                        }
                    }
                    .clipShape(MP.surfaceShape)
                }
            }
        } footer: {
            EmptyView()
        }
        .task { await model.loadOrgs(api: app.api) }
    }
}

// MARK: - Team

struct TeamStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel
    @FocusState private var focus: Field?
    enum Field { case jersey, code }

    private var teams: [SportsTeam] { model.org?.teams.filter { $0.sport == model.sportKey } ?? [] }
    private var positions: [String] { model.sportsCatalog?.positions ?? [] }
    private var classYears: [String] { model.sportsCatalog?.classYears ?? [] }

    var body: some View {
        StepScaffold(eyebrow: model.eyebrow(.team), title: model.org.map { "Your \($0.shortName) team" } ?? "Your team",
                     subtitle: model.org?.requiresCode == true
                        ? "Your staff gave you a join code; it links you to the coach, the trainer and the strength staff. Position and number help them find you."
                        : "Position and number help your staff find you on the roster.") {
            VStack(alignment: .leading, spacing: 16) {
                if teams.isEmpty {
                    Card {
                        EmptyRow(icon: "person.3", title: "No \(model.sportsCatalog?.sportLabel.lowercased() ?? model.sportKey) team listed here yet",
                                 detail: "You can join as an individual now and link the team once your program is set up.")
                    }
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Team").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        WrapChips(options: teams.map(\.id), labels: Dictionary(uniqueKeysWithValues: teams.map { ($0.id, $0.name) }),
                                  value: Binding(get: { model.team.map { .string($0.id) } },
                                                 set: { v in model.team = teams.first { $0.id == v?.stringValue } }))
                    }
                }
                if !positions.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Position").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        WrapChips(options: positions, labels: Dictionary(uniqueKeysWithValues: positions.map { ($0, $0) }),
                                  value: Binding(get: { model.position.isEmpty ? nil : .string(model.position) },
                                                 set: { model.position = $0?.stringValue ?? "" }))
                    }
                }
                HStack(spacing: 10) {
                    TextField("Number", text: $model.jersey, prompt: Text("Number").foregroundColor(MP.muted))
                        .textFieldStyle(FieldStyle()).keyboardType(.numberPad)
                        .focused($focus, equals: .jersey)
                    if !classYears.isEmpty, model.org?.kind == "college" {
                        Menu {
                            ForEach(classYears, id: \.self) { y in Button(y) { model.classYear = y } }
                        } label: {
                            HStack {
                                Text(model.classYear.isEmpty ? "Class year" : model.classYear)
                                    .mpFont(.copyLarge).foregroundStyle(model.classYear.isEmpty ? MP.muted : MP.ink)
                                Spacer()
                                Image(systemName: "chevron.up.chevron.down").font(.systemGlyphs(12)).foregroundStyle(MP.muted)
                            }
                            .padding(.horizontal, 16).frame(minHeight: 52)
                            .background(MP.thumbShape.fill(MP.panel.opacity(0.8)))
                            .overlay(MP.thumbShape.strokeBorder(MP.lineStrong.opacity(0.75), lineWidth: 1))
                        }
                    }
                }
                if model.org?.requiresCode == true {
                    TextField("Join code", text: $model.joinCode, prompt: Text("Join code from your staff").foregroundColor(MP.muted))
                        .textFieldStyle(FieldStyle())
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                        .focused($focus, equals: .code)
                }
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: "Continue", icon: "arrow.right",
                          disabled: model.org?.requiresCode == true && model.joinCode.trimmingCharacters(in: .whitespaces).count < 4) {
                model.go(.athlete)
            }
            QuietAction(title: "Skip the team for now") {
                model.org = nil
                model.team = nil
                model.go(.athlete)
            }
        }
        .task { await model.loadSportsCatalog(api: app.api) }
    }
}

// MARK: - Athlete

struct AthleteStep: View {
    @Environment(AppModel.self) private var app
    @Bindable var model: OnboardingModel

    private var levels: [SportsCatalog.Keyed] { model.sportsCatalog?.levels ?? [] }
    private var imperial: Bool { model.units == "imperial" }

    var body: some View {
        StepScaffold(eyebrow: model.eyebrow(.athlete), title: "About you as an athlete",
                     subtitle: "Height, reach and level set your benchmarks; the rest sharpens the readouts. Everything is optional and editable later.") {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Level").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    WrapChips(options: levels.map(\.key), labels: Dictionary(uniqueKeysWithValues: levels.map { ($0.key, $0.label) }),
                              value: Binding(get: { .string(model.level) }, set: { if let l = $0?.stringValue { model.level = l } }))
                }
                HStack(spacing: 8) {
                    Text("Units").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    Spacer()
                    Picker("Units", selection: $model.units) {
                        Text("ft, lb").tag("imperial")
                        Text("cm, kg").tag("metric")
                    }
                    .pickerStyle(.segmented).frame(maxWidth: 180)
                }
                HStack(spacing: 10) {
                    if imperial {
                        field("Height ft", $model.heightFt, keyboard: .numberPad)
                        field("in", $model.heightIn, keyboard: .numberPad)
                        field("Weight lb", $model.weightText, keyboard: .decimalPad)
                    } else {
                        field("Height cm", $model.heightCm, keyboard: .decimalPad)
                        field("Weight kg", $model.weightText, keyboard: .decimalPad)
                    }
                }
                HStack(spacing: 10) {
                    field(imperial ? "Wingspan in" : "Wingspan cm", $model.wingspanText, keyboard: .decimalPad)
                    field(imperial ? "Standing reach in" : "Standing reach cm", $model.reachText, keyboard: .decimalPad)
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text("Dominant side").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    WrapChips(options: ["right", "left"], labels: ["right": "Right", "left": "Left"],
                              value: Binding(get: { .string(model.dominantSide) }, set: { if let s = $0?.stringValue { model.dominantSide = s } }))
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text("Benchmarks and cycle tracking").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    WrapChips(options: ["M", "F", ""], labels: ["M": "Men's", "F": "Women's", "": "Prefer not to say"],
                              value: Binding(get: { .string(model.sex) }, set: { if let s = $0?.stringValue { model.sex = s } }))
                }
                if model.sex == "F" {
                    Card(padding: 0) {
                        Toggle(isOn: $model.cycleTracking) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Track my cycle").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text("Phase shows beside readiness; the luteal phase explains a warmer night and a higher resting heart rate.")
                                    .mpFont(.label).foregroundStyle(MP.muted)
                            }
                        }
                        .tint(MP.brand)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                    }
                }
                DatePicker("Date of birth", selection: Binding(get: { model.dateOfBirth ?? Calendar.current.date(byAdding: .year, value: -20, to: Date())! },
                                                               set: { model.dateOfBirth = $0 }),
                           in: ...Date(), displayedComponents: .date)
                    .datePickerStyle(.compact).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                if let error = model.error { ErrorBanner(text: error) }
            }
        } footer: {
            PrimaryButton(title: "Create my account", icon: "sparkles", loading: model.loading, disabled: !model.canCreateAthlete) {
                Task { await model.sportsJoin(api: app.api, app: app) }
            }
        }
        .task { await model.loadSportsCatalog(api: app.api) }
        .mpErrorFeedback(model.error)
    }

    private func field(_ label: String, _ text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        TextField(label, text: text, prompt: Text(label).foregroundColor(MP.muted))
            .textFieldStyle(FieldStyle()).keyboardType(keyboard)
    }
}

// MARK: - The mode card

/// The third card on the "how will you use MedPull" step.
struct SportsModeCard: View {
    @Bindable var model: OnboardingModel

    var body: some View {
        Button {
            model.path = .sports
            model.candidates = []
            model.selected = nil
            model.go(model.consent == nil ? .consent : .personalAbout)
        } label: {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    IconTile("figure.basketball", family: .indigo, size: 44)
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text("As an athlete").mpFont(.ledeMedium).foregroundStyle(MP.ink)
                            Text("Sports").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                                .padding(.horizontal, 8).padding(.vertical, 3)
                                .background(MP.capsuleShape.fill(MP.brandTint))
                        }
                        Text("MedPull Sports: every wearable and team system in one place, performance tests against your level, game recovery, and injury plans with the real return gates. With your team's staff, or on your own.")
                            .mpFont(.copy).mpSecondary().lineSpacing(2)
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
