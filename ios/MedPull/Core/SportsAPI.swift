import Foundation

// MedPull Sports endpoints. Same client, same session header.
extension APIClient {
    struct SportsJoinBody: Encodable {
        let name: String
        let email: String
        let password: String
        let consent: ConsentAcceptance
        let phone: String?
        let dateOfBirth: String?
        let sex: String?
        let sport: String
        let orgId: String?
        let teamId: String?
        let joinCode: String?
        let position: String?
        let jersey: String?
        let classYear: String?
        let level: String?
        let heightCm: Double?
        let weightKg: Double?
        let wingspanCm: Double?
        let standingReachCm: Double?
        let dominantSide: String?
        let units: String
        let cycleTracking: Bool
        let deviceName: String
        let appVersion: String
    }

    func sportsJoin(_ body: SportsJoinBody) async throws -> SportsJoinResponse {
        try await post("/api/mobile/sports/join", body: body)
    }

    /// Any email login, sports or personal: the app reads `me.patient.accountKind`.
    func sportsLogin(email: String, password: String) async throws -> SportsJoinResponse {
        try await post("/api/mobile/sports/login", body: LoginBody(
            email: email, password: password, deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    func sportsOrgs(query: String = "") async throws -> [SportsOrg] {
        let r: OrgsResponse = try await get("/api/mobile/sports/orgs", query: query.isEmpty ? [:] : ["q": query])
        return r.orgs
    }

    func sportsCatalog(sport: String) async throws -> SportsCatalog {
        try await get("/api/mobile/sports/catalog", query: ["sport": sport])
    }

    func sportsHome() async throws -> SportsHome { try await get("/api/mobile/sports/home") }
    func sportsStartDay() async throws -> SportsHome { try await post("/api/mobile/sports/day") }
    func sportsRecovery() async throws -> RecoveryBoard { try await get("/api/mobile/sports/recovery") }
    func sportsPerformance() async throws -> PerformanceBoard { try await get("/api/mobile/sports/performance") }
    func sportsRehab() async throws -> RehabBoard { try await get("/api/mobile/sports/rehab") }
    func sportsDevices() async throws -> DevicesBoard { try await get("/api/mobile/sports/devices") }
    func sportsProfile() async throws -> SportsProfileResponse { try await get("/api/mobile/sports/profile") }

    struct WellnessBody: Encodable { let answers: [String: AnswerValue]; let date: String? }

    func sportsLogWellness(_ answers: [String: AnswerValue], date: String? = nil) async throws -> WellnessLogResponse {
        try await post("/api/mobile/sports/wellness", body: WellnessBody(answers: answers, date: date))
    }

    struct SessionBody: Encodable {
        let date: String?
        let kind: String
        let minutes: Double
        let rpe: Double?
        let jumps: Int?
        let note: String?
        let source: String
    }

    func sportsLogSession(_ body: SessionBody) async throws -> SessionLogResponse {
        try await post("/api/mobile/sports/sessions", body: body)
    }

    func sportsSessions(days: Int = 28) async throws -> [SportsSession] {
        let r: SessionsResponse = try await get("/api/mobile/sports/sessions", query: ["days": String(days)])
        return r.sessions
    }

    struct TestEntry: Encodable {
        let testKey: String
        let value: Double
        let side: String?
        let date: String?
        let source: String
        let device: String?
        let note: String?
    }
    struct TestsBody: Encodable { let entries: [TestEntry] }

    func sportsLogTests(_ entries: [TestEntry]) async throws -> TestsLogResponse {
        try await post("/api/mobile/sports/tests", body: TestsBody(entries: entries))
    }

    func sportsDeleteTest(id: Int) async throws {
        let _: OKResponse = try await delete("/api/mobile/sports/tests/\(id)")
    }

    struct JumpBody: Encodable {
        let accel: [[Double]]
        let sampleRateHz: Double
        let testKey: String
        let side: String?
        let recordedAt: String
        let deviceModel: String?
        let save: Bool
    }

    func sportsPhoneJump(_ body: JumpBody) async throws -> PhoneJumpResponse {
        try await post("/api/mobile/sports/tests/jump", body: body)
    }

    struct BalanceBody: Encodable {
        let gravity: [[Double]]
        let sampleRateHz: Double
        let side: String
        let secondsHeld: Double?
        let save: Bool
    }

    func sportsPhoneBalance(_ body: BalanceBody) async throws -> PhoneBalanceResponse {
        try await post("/api/mobile/sports/tests/balance", body: body)
    }

    struct InjuryBody: Encodable {
        let injuryKey: String
        let side: String?
        let dateOfInjury: String
        let dateOfSurgery: String?
        let graft: String?
        let grade: String?
        let mechanism: String?
        let clinician: String?
        let note: String?
        let targetReturnDate: String?
    }

    func sportsReportInjury(_ body: InjuryBody) async throws -> InjuryReportResponse {
        try await post("/api/mobile/sports/injuries", body: body)
    }

    struct InjuryPatch: Encodable {
        var status: String? = nil
        var phaseOverride: Int? = nil
        var targetReturnDate: String? = nil
        var note: String? = nil
        var clinician: String? = nil
    }

    func sportsUpdateInjury(id: Int, _ body: InjuryPatch) async throws -> InjuryPatchResponse {
        try await patch("/api/mobile/sports/injuries/\(id)", body: body)
    }

    struct MeasureEntry: Encodable {
        let measureKey: String
        let value: Double
        let side: String?
        let date: String?
        let source: String
        let note: String?
    }
    struct MeasuresBody: Encodable { let entries: [MeasureEntry] }

    func sportsLogMeasures(injuryId: Int, _ entries: [MeasureEntry]) async throws -> MeasuresLogResponse {
        try await post("/api/mobile/sports/injuries/\(injuryId)/measures", body: MeasuresBody(entries: entries))
    }

    struct SportsProfilePatch: Encodable {
        var position: String? = nil
        var jersey: String? = nil
        var classYear: String? = nil
        var level: String? = nil
        var heightCm: Double? = nil
        var weightKg: Double? = nil
        var wingspanCm: Double? = nil
        var standingReachCm: Double? = nil
        var dominantSide: String? = nil
        var units: String? = nil
        var cycleTracking: Bool? = nil
        var status: String? = nil
        var statusNote: String? = nil
    }

    func sportsPatchProfile(_ body: SportsProfilePatch) async throws -> SportsProfileResponse {
        try await patch("/api/mobile/sports/profile", body: body)
    }

    struct OrgJoinBody: Encodable { let orgId: String; let teamId: String?; let joinCode: String?; let position: String? }

    func sportsJoinOrg(_ body: OrgJoinBody) async throws -> SportsProfileResponse {
        try await post("/api/mobile/sports/org/join", body: body)
    }

    func sportsLeaveOrg() async throws -> SportsProfileResponse {
        try await post("/api/mobile/sports/org/leave")
    }

    struct DeviceConnectBody: Encodable { let mode: String }

    func sportsConnectDevice(key: String, mode: String = "sample") async throws -> DeviceConnectResponse {
        try await post("/api/mobile/sports/devices/\(key)/connect", body: DeviceConnectBody(mode: mode))
    }

    func sportsDisconnectDevice(key: String) async throws {
        let _: OKResponse = try await delete("/api/mobile/sports/devices/\(key)")
    }
}
