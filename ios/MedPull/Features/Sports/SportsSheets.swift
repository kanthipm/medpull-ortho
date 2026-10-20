import SwiftUI

/// The morning wellness questions: the five Hooper-style items plus pain,
/// hydration and a note, as compact sliders. Answers land in the wellness
/// log; the server re-scores today and hands back the verdict.
struct WellnessSheet: View {
    var embedded = false
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var values: [String: Double] = [:]
    @State private var urine: Double?
    @State private var cyclePhase: String?
    @State private var unwell = false
    @State private var note = ""
    @State private var saving = false
    @State private var error: String?
    @State private var saved: WellnessLogResponse?

    private var specs: [WellnessSpec] {
        let all = app.sportsCatalog?.wellness ?? []
        let female = app.me?.sports?.sex == "F"
        return all.filter { $0.kind == "scale" && (!$0.femaleOnly || female) }
    }

    private var cycleSpec: WellnessSpec? {
        guard app.me?.sports?.cycleTracking == true else { return nil }
        return app.sportsCatalog?.wellness.first { $0.key == "cycle_phase" }
    }

    private var canSave: Bool { !saving && values.count >= 3 }

    var body: some View {
        Group {
            if embedded { content } else { NavigationStack { content } .presentationDetents([.large]) }
        }
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("How are you this morning?").title(MPSize.displayS)
                Text("Scored against your own four-week average, so an honest answer is the useful one.")
                    .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                if let saved {
                    doneCard(saved)
                } else {
                    Card(padding: 0) {
                        VStack(spacing: 0) {
                            ForEach(specs) { spec in
                                ScaleRow(spec: spec, value: Binding(
                                    get: { values[spec.key] },
                                    set: { v in if let v { values[spec.key] = v } else { values.removeValue(forKey: spec.key) } }))
                                    .padding(.horizontal, 16)
                                if spec.id != specs.last?.id { InsetDivider(leading: 16) }
                            }
                        }
                        .padding(.vertical, 6)
                    }
                    Card(padding: 0) {
                        VStack(alignment: .leading, spacing: 0) {
                            CardHeader("A few more")
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Urine colour this morning").mpFont(.copyMedium).foregroundStyle(MP.ink)
                                HStack(spacing: 6) {
                                    ForEach(1...8, id: \.self) { shade in
                                        Button { urine = Double(shade) } label: {
                                            Circle()
                                                .fill(Color(red: 0.98 - Double(shade) * 0.05, green: 0.93 - Double(shade) * 0.08, blue: 0.55 - Double(shade) * 0.06))
                                                .overlay(Circle().strokeBorder(urine == Double(shade) ? MP.ink : MP.line, lineWidth: urine == Double(shade) ? 2 : 1))
                                                .frame(width: 30, height: 30)
                                        }
                                        .accessibilityLabel("Shade \(shade)")
                                        .accessibilityAddTraits(urine == Double(shade) ? .isSelected : [])
                                    }
                                }
                                Text("1 pale to 8 dark. From 4 up, start on the fluids.").mpFont(.label).foregroundStyle(MP.muted)
                            }
                            .padding(.horizontal, 16).padding(.vertical, 10)
                            InsetDivider(leading: 16)
                            Toggle(isOn: $unwell) {
                                HStack(spacing: 14) {
                                    IconTile("thermometer.medium", family: .violet)
                                    Text("Feeling unwell").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                }
                            }
                            .tint(MP.brand)
                            .padding(.horizontal, 16).padding(.vertical, 10)
                            if let cycleSpec {
                                InsetDivider(leading: 16)
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(cycleSpec.prompt).mpFont(.copyMedium).foregroundStyle(MP.ink)
                                    WrapChips(options: cycleSpec.options,
                                              labels: Dictionary(uniqueKeysWithValues: cycleSpec.options.map { ($0, $0.capitalized) }),
                                              value: Binding(get: { cyclePhase.map { AnswerValue.string($0) } },
                                                             set: { cyclePhase = $0?.stringValue }))
                                }
                                .padding(.horizontal, 16).padding(.vertical, 10)
                            }
                        }
                        .padding(.bottom, 6)
                    }
                    TextField("Anything your staff should know? (optional)", text: $note,
                              prompt: Text("Anything your staff should know? (optional)").foregroundColor(MP.muted), axis: .vertical)
                        .lineLimit(2...5)
                        .textFieldStyle(FieldStyle())
                    if let error { ErrorBanner(text: error) }
                    PrimaryButton(title: "Save check-in", icon: "checkmark", loading: saving, disabled: !canSave) { save() }
                    Text(values.count < 3 ? "Answer at least three to save." : "\(values.count) of \(specs.count) answered.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                }
                SportsGuardrail()
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
        .ambientScreen()
        .navigationTitle("Morning check-in")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if !embedded {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
        }
        .mpCompletionFeedback(saved != nil)
        .mpErrorFeedback(error)
        .task {
            if app.sportsCatalog == nil, let sport = app.me?.sports?.sport {
                app.sportsCatalog = try? await app.api.sportsCatalog(sport: sport)
            }
            // Today's answers, if any, so an edit starts from them.
            if let items = app.sportsHome?.wellness.items, app.sportsHome?.wellness.answeredToday ?? 0 > 0 {
                for i in items where i.date == Dates.dayString(Date()) { values[i.key] = i.value }
            }
        }
    }

    private func doneCard(_ r: WellnessLogResponse) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Card(tint: true) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) {
                        Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow)
                        Text("Saved. \(r.wellness.statusText).").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    }
                    Text(r.wellness.finding.typeset).mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 8) {
                        StatusPill(text: r.verdict.title, tone: r.verdict.tone)
                        if let h = r.wellness.hooper {
                            Text("Hooper \(String(format: "%.0f", h))").mpFont(.label).mpSecondary()
                        }
                    }
                }
            }
            ForEach(r.suggestions.prefix(2)) { s in SuggestionCard(suggestion: s, expanded: false) }
            PrimaryButton(title: "Done") { dismiss() }
        }
    }

    private func save() {
        saving = true
        error = nil
        var answers: [String: AnswerValue] = [:]
        for (k, v) in values { answers[k] = .int(Int(v)) }
        if let urine { answers["hydration"] = .int(Int(urine)) }
        answers["illness"] = .string(unwell ? "yes" : "no")
        if let cyclePhase { answers["cycle_phase"] = .string(cyclePhase) }
        let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { answers["note"] = .string(trimmed) }
        Task {
            defer { saving = false }
            do {
                let r = try await app.api.sportsLogWellness(answers)
                saved = r
                await app.refreshSports(startDay: false)
                await app.refreshTasks(surface: false)
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// Log a session: what it was, minutes, RPE (Foster's session load), jumps
/// when they are counted, a note. The weekly load reads off these.
struct SportsSessionSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var kind = "practice"
    @State private var minutes = 90
    @State private var rpe: AnswerValue? = .int(6)
    @State private var jumpsOn = false
    @State private var jumps = 60
    @State private var note = ""
    @State private var date = Date()
    @State private var saving = false
    @State private var error: String?
    @State private var saved: SessionLogResponse?

    private var kinds: [(String, String)] {
        let sport = app.me?.sports?.sport ?? "basketball"
        switch sport {
        case "tennis": return [("practice", "Hitting"), ("match", "Match"), ("lift", "Gym"), ("conditioning", "Conditioning"), ("individual", "Serves"), ("rehab", "Rehab")]
        case "soccer": return [("practice", "Training"), ("match", "Match"), ("lift", "Gym"), ("conditioning", "Conditioning"), ("individual", "Individual"), ("rehab", "Rehab")]
        default: return [("practice", "Practice"), ("game", "Game"), ("lift", "Lift"), ("shootaround", "Shootaround"), ("conditioning", "Conditioning"), ("individual", "Individual"), ("rehab", "Rehab")]
        }
    }

    private var rpeWord: String {
        switch rpe?.intValue ?? 0 {
        case 0...2: return "Very easy"
        case 3...4: return "Easy"
        case 5...6: return "Moderate"
        case 7...8: return "Hard"
        default: return "Maximal"
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("What did you do?").title(MPSize.displayS)
                    Text("Minutes times effort is your session load. Log every session and the weekly load, monotony and tomorrow's readiness read run on it.")
                        .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if let saved {
                        Card(tint: true) {
                            HStack(spacing: 10) {
                                Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow)
                                Text("Logged. Load \(String(format: "%.0f", saved.loadAu ?? 0)) AU.").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            }
                        }
                        PrimaryButton(title: "Done") { dismiss() }
                    } else {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Session").mpFont(.labelMedium).foregroundStyle(MP.muted)
                            WrapChips(options: kinds.map(\.0), labels: Dictionary(uniqueKeysWithValues: kinds),
                                      value: Binding(get: { .string(kind) }, set: { if let k = $0?.stringValue { kind = k } }))
                        }
                        Card(padding: 0) {
                            VStack(spacing: 0) {
                                Stepper(value: $minutes, in: 5...300, step: 5) {
                                    HStack {
                                        Text("Minutes").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                        Spacer()
                                        Text("\(minutes)").font(.figuresCopyLarge).foregroundStyle(MP.ink)
                                    }
                                }
                                .tint(MP.brand)
                                .padding(.horizontal, 16).padding(.vertical, 10)
                                .mpSelectionFeedback(minutes)
                                InsetDivider(leading: 16)
                                DatePicker("Day", selection: $date, in: ...Date(), displayedComponents: .date)
                                    .datePickerStyle(.compact)
                                    .mpFont(.copyLarge).foregroundStyle(MP.ink)
                                    .padding(.horizontal, 16).padding(.vertical, 6)
                            }
                        }
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text("Effort, 0 to 10").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Spacer()
                                Text(rpeWord).mpFont(.label).foregroundStyle(MP.muted)
                            }
                            ScaleAnswer(value: $rpe, painting: false)
                        }
                        Card(padding: 0) {
                            VStack(spacing: 0) {
                                Toggle(isOn: $jumpsOn) {
                                    HStack(spacing: 14) {
                                        IconTile("figure.jumprope", family: .teal)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text("Jumps counted").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                            Text("From VERT, Catapult or a count").mpFont(.label).foregroundStyle(MP.muted)
                                        }
                                    }
                                }
                                .tint(MP.brand)
                                .padding(.horizontal, 16).padding(.vertical, 10)
                                if jumpsOn {
                                    InsetDivider()
                                    Stepper(value: $jumps, in: 0...600, step: 5) {
                                        HStack {
                                            Text("Jumps").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                            Spacer()
                                            Text("\(jumps)").font(.figuresCopyLarge).foregroundStyle(MP.ink)
                                        }
                                    }
                                    .tint(MP.brand)
                                    .padding(.horizontal, 16).padding(.vertical, 10)
                                }
                            }
                        }
                        TextField("Anything worth noting (optional)", text: $note,
                                  prompt: Text("Anything worth noting (optional)").foregroundColor(MP.muted), axis: .vertical)
                            .lineLimit(2...5)
                            .textFieldStyle(FieldStyle())
                        if let error { ErrorBanner(text: error) }
                        PrimaryButton(title: "Log session", icon: "checkmark", loading: saving, disabled: rpe?.intValue == nil) { save() }
                    }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientScreen()
            .navigationTitle("Log a session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
            .mpCompletionFeedback(saved != nil)
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private func save() {
        guard let effort = rpe?.intValue else { return }
        saving = true
        error = nil
        Task {
            defer { saving = false }
            do {
                let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
                saved = try await app.api.sportsLogSession(.init(
                    date: Dates.dayString(date), kind: kind, minutes: Double(minutes), rpe: Double(effort),
                    jumps: jumpsOn ? jumps : nil, note: trimmed.isEmpty ? nil : trimmed, source: "manual"))
                await app.refreshSports(startDay: false)
                await app.refreshTasks(surface: false)
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}
