import Foundation
import Observation

@Observable
@MainActor
final class OnboardingModel {
    /// Every screen the flow can show. The order is load-bearing for
    /// `isPastEnrollment` only; which steps a person actually visits is
    /// decided by `Path`.
    enum Step: Int, CaseIterable, Hashable {
        case welcome, mode, consent, login, hospital, path, identity, join, personalAbout, goals,
             verify, plan, health, wearable, done

        /// Steps after the session exists. Going back from these would land
        /// on a form that has already done its job, so they hide the system
        /// back button (which also turns off the edge swipe).
        var isPastEnrollment: Bool { rawValue >= Step.plan.rawValue }
    }

    /// How the person is joining: on a hospital's roster already (find the
    /// record), new to it (create one — with or without a surgery), or on
    /// their own as a MedPull Personal subscriber.
    enum Path { case findRecord, joinGeneral, joinAfterSurgery, personal }

    /// The NavigationStack path. Welcome is the root and never appears in
    /// it; `step` is whatever is on top.
    var route: [Step] = []
    var step: Step { route.last ?? .welcome }
    var path: Path = .joinGeneral

    var isPersonal: Bool { path == .personal }

    var hospitals: [Hospital] = []
    var hospitalQuery = ""
    var hospital: Hospital?

    var name = ""
    var phone = ""
    var candidates: [Candidate] = []
    var searching = false
    var selected: Candidate?

    // join form
    var dateOfBirth: Date? = nil
    var procedures: [Procedure] = []
    var procedure: Procedure?
    var surgeryDate: Date = Calendar.current.date(byAdding: .day, value: -7, to: Date())!

    // the beta consent, accepted before any account exists and carried into
    // whichever call creates the session
    var consent: ConsentAcceptance?

    // the login (email + password), for a personal space
    var email = ""
    var password = ""
    var showPassword = false
    /// Sign-in screen state, for a person who already has a space.
    var loginEmail = ""
    var loginPassword = ""
    var forgotSent: ForgotResponse?
    var resetCode = ""
    var resetPassword = ""

    // the personal space
    /// Signing back into an existing space rather than opening one (by phone
    /// code; the email login is the usual door).
    var personalSignin = false
    var goal = "everyday"
    var sport = ""
    var weeklyTargetMinutes = 180
    var sleepTargetHours = 8.0
    var injury = ""
    var anchorDate: Date = Calendar.current.date(byAdding: .day, value: -14, to: Date())!
    var smsBriefs = true

    var verificationId: Int?
    var phoneMasked: String?
    var code = ""
    /// Which verify route finishes the code: the personal one when the
    /// space (or sign-in) started it.
    private var verifyPersonal = false

    var loading = false
    var error: String?

    var canSearch: Bool { name.trimmingCharacters(in: .whitespaces).count >= 2 }
    var phoneLooksValid: Bool { phone.filter(\.isNumber).count >= 10 }
    var canEnroll: Bool { selected != nil && phoneLooksValid && !loading }
    var canJoin: Bool {
        canSearch && phoneLooksValid && !loading
            && (path != .joinAfterSurgery || procedure != nil)
    }
    var emailLooksValid: Bool {
        let e = email.trimmingCharacters(in: .whitespaces)
        return e.contains("@") && e.contains(".") && e.count >= 6
    }
    var passwordLooksValid: Bool { password.count >= 8 }
    /// The phone is optional on a personal space; given, it must look real.
    var phoneOkOrEmpty: Bool { phone.filter(\.isNumber).isEmpty || phoneLooksValid }
    var canContinuePersonal: Bool {
        !loading && (personalSignin ? phoneLooksValid
                     : (canSearch && emailLooksValid && passwordLooksValid && phoneOkOrEmpty))
    }
    var canCreateSpace: Bool {
        canSearch && emailLooksValid && passwordLooksValid && phoneOkOrEmpty && !loading
            && (goal != "recovery" || procedure != nil || !injury.isEmpty)
    }
    var canLogin: Bool {
        !loading && loginEmail.contains("@") && loginPassword.count >= 8
    }

    /// The dots in the bar, for the path the person is on.
    var stepsShown: [Step] {
        isPersonal ? [.consent, .personalAbout, .goals, .plan, .health, .wearable]
            : [.consent, .hospital, .path, .identity, .verify, .health, .wearable]
    }

    /// "Step 3 of 5" for the screen, counted along the person's own path.
    func eyebrow(_ step: Step) -> String {
        let shown = stepsShown
        guard let i = shown.firstIndex(of: step) else { return "Almost done" }
        return "Step \(i + 1) of \(shown.count)"
    }

    /// Forward pushes; a step already on the stack pops back to it (so
    /// "Different hospital" is a pop, and re-sending a code is a no-op).
    func go(_ next: Step) {
        error = nil
        if next == .welcome {
            route = []
        } else if let i = route.firstIndex(of: next) {
            route = Array(route[...i])
        } else {
            route.append(next)
        }
    }

    func choose(_ path: Path) {
        self.path = path
        candidates = []
        selected = nil
        let next: Step = path == .findRecord ? .identity : path == .personal ? .personalAbout : .join
        // Switching between the two record forms (a 409 on join sends the
        // patient to find-my-record) replaces the form rather than stacking
        // one on the other, so Back still means "how are you joining?".
        if let last = route.last, last == .join || last == .identity, last != next {
            error = nil
            var r = route
            r.removeLast()
            r.append(next)
            route = r
        } else {
            go(next)
        }
    }

    func loadHospitals(api: APIClient) async {
        do {
            hospitals = try await api.hospitals()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadProcedures(api: APIClient) async {
        guard procedures.isEmpty else { return }
        procedures = (try? await api.procedures()) ?? []
    }

    var filteredHospitals: [Hospital] {
        let q = hospitalQuery.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return hospitals }
        return hospitals.filter {
            $0.name.lowercased().contains(q) || ($0.system ?? "").lowercased().contains(q)
                || $0.city.lowercased().contains(q)
        }
    }

    /// Runs as the name is typed (the view debounces). Keeps a chosen
    /// candidate only while it is still in the results.
    func search(api: APIClient) async {
        guard let hospital, canSearch else {
            candidates = []
            selected = nil
            return
        }
        searching = true
        defer { searching = false }
        do {
            let found = try await api.search(hospitalId: hospital.id, name: name,
                                             phone: phoneLooksValid ? phone : nil)
            candidates = found
            if let selected, !found.contains(where: { $0.patientId == selected.patientId }) {
                self.selected = nil
            }
            if found.count == 1 { selected = found[0] }
        } catch {
            candidates = []
        }
    }

    func enroll(api: APIClient, app: AppModel) async {
        guard let selected, let hospital else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let r = try await api.enroll(patientId: selected.patientId, hospitalId: hospital.id, phone: phone,
                                         consent: consent)
            try handle(r, app: app)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func join(api: APIClient, app: AppModel) async {
        guard let hospital else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let r = try await api.join(
                hospitalId: hospital.id, name: name, phone: phone, dateOfBirth: dateOfBirth,
                hadSurgery: path == .joinAfterSurgery, procedureType: procedure?.id,
                surgeryDate: surgeryDate, consent: consent)
            try handle(r, app: app)
        } catch let e as APIError where e.status == 409 {
            // The number is already on a record here (the clinic created it,
            // or this person enrolled before). Don't dead-end: take them to
            // find-my-record, where the phone match lists that record.
            choose(.findRecord)
            self.error = "This number is already on a record at \(hospital.name). Pick it below and you’re in."
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: the personal space

    /// Open a personal space (or sign back into one). A code may be asked
    /// for; the `.plan` step follows the session.
    func personalJoin(api: APIClient, app: AppModel) async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            let r: EnrollResponse
            if personalSignin {
                r = try await api.personalSignin(phone: phone)
            } else {
                guard let consent else {
                    throw APIError(status: 422, detail: "Read and agree to the beta consent first.")
                }
                let cleanPhone = phone.filter(\.isNumber).isEmpty ? nil : phone
                r = try await api.personalJoin(.init(
                    name: name, email: email.trimmingCharacters(in: .whitespaces).lowercased(),
                    password: password, consent: consent,
                    phone: cleanPhone, dateOfBirth: dateOfBirth.map(Dates.dayString),
                    sex: nil, goal: goal,
                    sport: goal == "performance" ? sport.trimmingCharacters(in: .whitespaces) : nil,
                    weeklyTargetMinutes: goal == "performance" ? weeklyTargetMinutes : nil,
                    sleepTargetHours: goal == "sleep" ? sleepTargetHours : nil,
                    injury: goal == "recovery" ? (injury.isEmpty ? procedure?.label : injury) : nil,
                    anchorDate: goal == "recovery" ? Dates.dayString(anchorDate) : nil,
                    procedureType: goal == "recovery" ? procedure?.id : nil,
                    units: Locale.current.measurementSystem == .metric ? "metric" : "imperial",
                    smsBriefs: smsBriefs,
                    deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
            }
            verifyPersonal = true
            try handle(r, app: app)
        } catch let e as APIError where e.status == 409 && !personalSignin
                    && e.detail.lowercased().contains("email already has an account") {
            // The email is taken: the sign-in screen, with it filled in.
            loginEmail = email
            self.error = nil
            go(.login)
        } catch let e as APIError where e.status == 404 && personalSignin {
            personalSignin = false
            self.error = "No personal space uses that number yet — set one up below."
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// The usual door back in: email and password.
    func login(api: APIClient, app: AppModel) async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            let r = try await api.personalLogin(email: loginEmail.trimmingCharacters(in: .whitespaces).lowercased(),
                                                password: loginPassword)
            path = .personal
            guard let token = r.sessionToken, let me = r.me else {
                throw APIError(status: 0, detail: "The server didn’t return a session.")
            }
            app.adoptSession(token: token, me: me)
            // A returning person goes straight in; onboarding is done.
            app.enterHome()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func forgot(api: APIClient) async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            forgotSent = try await api.forgotPassword(email: loginEmail.trimmingCharacters(in: .whitespaces).lowercased())
            resetCode = ""
            resetPassword = ""
        } catch {
            self.error = error.localizedDescription
        }
    }

    func reset(api: APIClient, app: AppModel) async {
        guard let id = forgotSent?.verificationId else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let r = try await api.resetPassword(verificationId: id, code: resetCode, password: resetPassword)
            path = .personal
            guard let token = r.sessionToken, let me = r.me else {
                throw APIError(status: 0, detail: "The server didn’t return a session.")
            }
            app.adoptSession(token: token, me: me)
            app.enterHome()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func verify(api: APIClient, app: AppModel) async {
        guard let verificationId else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let r = verifyPersonal
                ? try await api.personalVerify(verificationId: verificationId, code: code)
                : try await api.verify(verificationId: verificationId, code: code, consent: consent)
            try handle(r, app: app)
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Re-send: whichever call started the verification.
    func resend(api: APIClient, app: AppModel) async {
        switch path {
        case .findRecord: await enroll(api: api, app: app)
        case .personal: await personalJoin(api: api, app: app)
        default: await join(api: api, app: app)
        }
    }

    private func handle(_ r: EnrollResponse, app: AppModel) throws {
        switch r.status {
        case "verification_required":
            verificationId = r.verificationId
            phoneMasked = r.phoneMasked
            code = ""
            go(.verify)
        case "enrolled":
            guard let token = r.sessionToken, let me = r.me else {
                throw APIError(status: 0, detail: "The server didn’t return a session.")
            }
            app.adoptSession(token: token, me: me)
            go(isPersonal ? .plan : .health)
        default:
            throw APIError(status: 0, detail: "Unexpected status \(r.status)")
        }
    }
}
