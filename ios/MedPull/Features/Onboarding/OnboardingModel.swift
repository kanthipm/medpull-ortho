import Foundation
import Observation

@Observable
@MainActor
final class OnboardingModel {
    enum Step: Int, CaseIterable, Hashable {
        case welcome, hospital, path, identity, join, verify, health, wearable, done

        /// Steps after the session exists. Going back from these would land
        /// on a form that has already done its job, so they hide the system
        /// back button (which also turns off the edge swipe).
        var isPastEnrollment: Bool { rawValue >= Step.health.rawValue }
    }

    /// How the person is joining: on the hospital's roster already (find the
    /// record), or new to it (create one — with or without a surgery).
    enum Path { case findRecord, joinGeneral, joinAfterSurgery }

    /// The NavigationStack path. Welcome is the root and never appears in
    /// it; `step` is whatever is on top.
    var route: [Step] = []
    var step: Step { route.last ?? .welcome }
    var path: Path = .joinGeneral

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

    var verificationId: Int?
    var phoneMasked: String?
    var code = ""

    var loading = false
    var error: String?

    var canSearch: Bool { name.trimmingCharacters(in: .whitespaces).count >= 2 }
    var phoneLooksValid: Bool { phone.filter(\.isNumber).count >= 10 }
    var canEnroll: Bool { selected != nil && phoneLooksValid && !loading }
    var canJoin: Bool {
        canSearch && phoneLooksValid && !loading
            && (path != .joinAfterSurgery || procedure != nil)
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
        let next: Step = path == .findRecord ? .identity : .join
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
            let r = try await api.enroll(patientId: selected.patientId, hospitalId: hospital.id, phone: phone)
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
                surgeryDate: surgeryDate)
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

    func verify(api: APIClient, app: AppModel) async {
        guard let verificationId else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let r = try await api.verify(verificationId: verificationId, code: code)
            try handle(r, app: app)
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Re-send: whichever call started the verification.
    func resend(api: APIClient, app: AppModel) async {
        if path == .findRecord { await enroll(api: api, app: app) } else { await join(api: api, app: app) }
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
            go(.health)
        default:
            throw APIError(status: 0, detail: "Unexpected status \(r.status)")
        }
    }
}
