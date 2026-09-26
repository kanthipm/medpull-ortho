import Foundation

// The personal tier's endpoints. Same client, same session header.
extension APIClient {
    struct PersonalJoinBody: Encodable {
        let name: String
        let email: String
        let password: String
        let consent: ConsentAcceptance
        let phone: String?
        let dateOfBirth: String?
        let sex: String?
        let goal: String
        let sport: String?
        let weeklyTargetMinutes: Int?
        let sleepTargetHours: Double?
        let injury: String?
        let anchorDate: String?
        let procedureType: String?
        let units: String
        let smsBriefs: Bool
        let deviceName: String
        let appVersion: String
    }

    func personalJoin(_ body: PersonalJoinBody) async throws -> EnrollResponse {
        try await post("/api/mobile/personal/join", body: body)
    }

    struct PhoneBody: Encodable { let phone: String; let deviceName: String; let appVersion: String }

    struct LoginBody: Encodable {
        let email: String; let password: String; let deviceName: String; let appVersion: String
    }

    func personalLogin(email: String, password: String) async throws -> EnrollResponse {
        try await post("/api/mobile/personal/login", body: LoginBody(
            email: email, password: password, deviceName: UIDeviceName.current,
            appVersion: AppConfig.appVersion))
    }

    struct ForgotBody: Encodable { let email: String }

    func forgotPassword(email: String) async throws -> ForgotResponse {
        try await post("/api/mobile/personal/password/forgot", body: ForgotBody(email: email))
    }

    struct ResetBody: Encodable {
        let verificationId: Int; let code: String; let password: String
        let deviceName: String; let appVersion: String
    }

    func resetPassword(verificationId: Int, code: String, password: String) async throws -> EnrollResponse {
        try await post("/api/mobile/personal/password/reset", body: ResetBody(
            verificationId: verificationId, code: code, password: password,
            deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    struct ChangePasswordBody: Encodable { let currentPassword: String; let newPassword: String }

    func changePassword(current: String, new: String) async throws {
        let _: OKResponse = try await post("/api/mobile/personal/password/change",
                                           body: ChangePasswordBody(currentPassword: current, newPassword: new))
    }

    func consentDocument() async throws -> ConsentDocument { try await get("/api/mobile/consent") }

    struct ConsentAcceptBody: Encodable {
        let version: String; let scopes: [String: Bool]; let signature: String?
        let deviceName: String; let appVersion: String
    }

    /// Record acceptance for the signed-in account (either kind).
    func acceptConsent(_ acceptance: ConsentAcceptance) async throws -> ConsentStatus {
        struct R: Decodable { let ok: Bool; let consent: ConsentStatus }
        let r: R = try await post("/api/mobile/consent", body: ConsentAcceptBody(
            version: acceptance.version, scopes: acceptance.scopes, signature: acceptance.signature,
            deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
        return r.consent
    }

    struct ResearchBody: Encodable { let allowed: Bool }

    func setResearchUse(_ allowed: Bool) async throws -> ConsentStatus {
        struct R: Decodable { let ok: Bool; let consent: ConsentStatus }
        let r: R = try await patch("/api/mobile/personal/consent/research", body: ResearchBody(allowed: allowed))
        return r.consent
    }

    func deletePersonalAccount() async throws {
        struct R: Decodable { let ok: Bool }
        let _: R = try await delete("/api/mobile/personal/account")
    }

    func personalWeek() async throws -> WeekResponse { try await get("/api/mobile/personal/week") }

    func personalSignin(phone: String) async throws -> EnrollResponse {
        try await post("/api/mobile/personal/signin", body: PhoneBody(
            phone: phone, deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    func personalVerify(verificationId: Int, code: String) async throws -> EnrollResponse {
        try await post("/api/mobile/personal/verify", body: VerifyBody(
            verificationId: verificationId, code: code,
            deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    func profiles() async throws -> ProfilesResponse { try await get("/api/mobile/profiles") }

    struct SwitchBody: Encodable { let patientId: String; let deviceName: String; let appVersion: String }

    func switchProfile(to patientId: String) async throws -> SwitchResponse {
        try await post("/api/mobile/profiles/switch", body: SwitchBody(
            patientId: patientId, deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    struct AddSpaceBody: Encodable {
        let goal: String
        let sport: String?
        let weeklyTargetMinutes: Int?
        let sleepTargetHours: Double?
        let injury: String?
        let units: String
        let smsBriefs: Bool
        let deviceName: String
        let appVersion: String
    }

    func addPersonalSpace(_ body: AddSpaceBody) async throws -> AddSpaceResponse {
        try await post("/api/mobile/personal/add", body: body)
    }

    struct LinkHospitalBody: Encodable {
        let mode: String
        let hospitalId: String
        let patientId: String?
        let hadSurgery: Bool
        let procedureType: String?
        let surgeryDate: String?
        let deviceName: String
        let appVersion: String
    }

    func linkHospital(_ body: LinkHospitalBody) async throws -> LinkHospitalResponse {
        try await post("/api/mobile/personal/link-hospital", body: body)
    }

    func personalProfile() async throws -> PersonalProfileResponse {
        try await get("/api/mobile/personal/profile")
    }

    struct ProfilePatch: Encodable {
        var goal: String? = nil
        var sport: String? = nil
        var weeklyTargetMinutes: Int? = nil
        var sleepTargetHours: Double? = nil
        var injury: String? = nil
        var units: String? = nil
        var smsBriefs: Bool? = nil
        var briefHour: Int? = nil
    }

    func patchPersonalProfile(_ body: ProfilePatch) async throws -> PersonalProfileResponse {
        struct R: Decodable { let profile: PersonalProfile }
        let r: R = try await patch("/api/mobile/personal/profile", body: body)
        return PersonalProfileResponse(profile: r.profile, subscription: nil, profiles: nil)
    }

    func subscription() async throws -> SubscriptionState {
        try await get("/api/mobile/personal/subscription")
    }

    struct AppleTransactionBody: Encodable { let jws: String; let environment: String? }

    func reportAppleTransaction(jws: String, environment: String?) async throws -> AppleTransactionResponse {
        try await post("/api/mobile/personal/subscription/apple",
                       body: AppleTransactionBody(jws: jws, environment: environment))
    }

    func personalDashboard() async throws -> DashboardResponse {
        try await get("/api/mobile/personal/dashboard")
    }

    struct DayBody: Encodable { let text: Bool }

    func startDay() async throws -> StartDayResponse {
        try await post("/api/mobile/personal/day", body: DayBody(text: false))
    }

    func deepDive(_ domain: String) async throws -> DeepDive {
        try await get("/api/mobile/personal/insights/\(domain)")
    }

    struct LogBody: Encodable { let key: String; let value: Double?; let text: String? }

    func personalLog(key: String, value: Double? = nil, text: String? = nil) async throws {
        struct R: Decodable { let ok: Bool }
        let _: R = try await post("/api/mobile/personal/log", body: LogBody(key: key, value: value, text: text))
    }

    func exportPersonalData() async throws -> ExportResponse {
        try await post("/api/mobile/personal/export")
    }

    /// The export as bytes, for a deployment with no object store (the
    /// server returns the document inline instead of a link).
    func exportPersonalDataRaw() async throws -> Data {
        var request = URLRequest(url: AppConfig.baseURL.appendingPathComponent("/api/mobile/personal/export"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data("{}".utf8)
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.timeoutInterval = 60
        let (data, response) = try await URLSession.shared.data(for: request)
        try check(response, data)
        // The document sits under "data"; hand back just that.
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let inner = obj["data"] {
            return try JSONSerialization.data(withJSONObject: inner, options: [.prettyPrinted, .sortedKeys])
        }
        return data
    }
}
