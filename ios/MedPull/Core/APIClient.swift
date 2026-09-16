import Foundation

struct APIError: LocalizedError, Equatable {
    let status: Int
    let detail: String
    var errorDescription: String? { detail }
    var isUnauthorized: Bool { status == 401 }
}

/// One JSON client for /api/mobile. The session token is attached to every
/// call once set; a 401 clears the session upstream (AppModel).
final class APIClient {
    var token: String?

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        return e
    }()

    private struct Empty: Encodable {}

    func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        try await send("GET", path, query: query, body: Optional<Empty>.none)
    }

    func post<T: Decodable, B: Encodable>(_ path: String, body: B?) async throws -> T {
        try await send("POST", path, query: [:], body: body)
    }

    func post<T: Decodable>(_ path: String) async throws -> T {
        try await send("POST", path, query: [:], body: Optional<Empty>.none)
    }

    private func send<T: Decodable, B: Encodable>(
        _ method: String, _ path: String, query: [String: String], body: B?
    ) async throws -> T {
        var components = URLComponents(url: AppConfig.baseURL.appendingPathComponent(path),
                                       resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try encoder.encode(body)
        } else if method != "GET" {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = Data("{}".utf8)
        }

        // A GET is safe to repeat, and the server's hiccups are short: a cold
        // start, or a burst of console traffic taking every Lambda slot for a
        // second or two. One retry after a short pause hides most of them.
        var (data, response) = try await attempt(request)
        var status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if method == "GET" && (status == 0 || status == 429 || status >= 500) {
            // `try`, not `try?`: a sleep cancelled while the screen is going
            // away must abandon the retry rather than wake up and report a
            // failure nobody is waiting for.
            try await Task.sleep(for: .seconds(1.5))
            (data, response) = try await attempt(request)
            status = (response as? HTTPURLResponse)?.statusCode ?? 0
        }
        if status == 0 {
            throw APIError(status: 0, detail: "Can't reach MedPull right now. Check your connection.")
        }
        guard (200..<300).contains(status) else {
            var detail = HTTPURLResponse.localizedString(forStatusCode: status)
            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let d = obj["detail"] as? String {
                detail = d
            }
            throw APIError(status: status, detail: detail)
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError(status: status, detail: "Unexpected answer from the server (\(error.localizedDescription)).")
        }
    }

    /// One HTTP attempt. A transport failure (no network, DNS, timeout) comes
    /// back as status 0 with empty data rather than throwing, so the caller
    /// can decide whether to retry.
    ///
    /// Cancellation is not a transport failure and must not be folded into
    /// one. SwiftUI cancels the task behind a `.task` or `.refreshable` every
    /// time the view goes away — a tab switch, leaving Messages, the poll loop
    /// being torn down — and URLSession reports that as `URLError.cancelled`.
    /// Treating it as "no connection" is what put "Can't reach MedPull" in
    /// front of people whose connection was fine.
    private func attempt(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            return (Data(), URLResponse())
        }
    }
}

// MARK: - Endpoints

extension APIClient {
    struct HospitalsResponse: Codable { let hospitals: [Hospital] }
    struct CandidatesResponse: Codable { let candidates: [Candidate] }

    func hospitals(query: String = "") async throws -> [Hospital] {
        let r: HospitalsResponse = try await get("/api/mobile/hospitals", query: query.isEmpty ? [:] : ["q": query])
        return r.hospitals
    }

    struct SearchBody: Encodable { let hospitalId: String; let name: String; let phone: String? }

    func search(hospitalId: String, name: String, phone: String?) async throws -> [Candidate] {
        let r: CandidatesResponse = try await post("/api/mobile/patients/search",
                                                   body: SearchBody(hospitalId: hospitalId, name: name, phone: phone))
        return r.candidates
    }

    struct EnrollBody: Encodable {
        let patientId: String; let hospitalId: String; let phone: String
        let deviceName: String; let appVersion: String
    }

    func enroll(patientId: String, hospitalId: String, phone: String) async throws -> EnrollResponse {
        try await post("/api/mobile/enroll", body: EnrollBody(
            patientId: patientId, hospitalId: hospitalId, phone: phone,
            deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    struct VerifyBody: Encodable {
        let verificationId: Int; let code: String; let deviceName: String; let appVersion: String
    }

    func verify(verificationId: Int, code: String) async throws -> EnrollResponse {
        try await post("/api/mobile/enroll/verify", body: VerifyBody(
            verificationId: verificationId, code: code,
            deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    struct ProceduresResponse: Codable { let procedures: [Procedure] }

    func procedures() async throws -> [Procedure] {
        let r: ProceduresResponse = try await get("/api/mobile/procedures")
        return r.procedures
    }

    struct JoinBody: Encodable {
        let hospitalId: String
        let name: String
        let phone: String
        let dateOfBirth: String?
        let hadSurgery: Bool
        let procedureType: String?
        let surgeryDate: String?
        let deviceName: String
        let appVersion: String
    }

    func join(hospitalId: String, name: String, phone: String, dateOfBirth: Date?,
              hadSurgery: Bool, procedureType: String?, surgeryDate: Date?) async throws -> EnrollResponse {
        try await post("/api/mobile/join", body: JoinBody(
            hospitalId: hospitalId, name: name, phone: phone,
            dateOfBirth: dateOfBirth.map(Dates.dayString),
            hadSurgery: hadSurgery, procedureType: hadSurgery ? procedureType : nil,
            surgeryDate: hadSurgery ? surgeryDate.map(Dates.dayString) : nil,
            deviceName: UIDeviceName.current, appVersion: AppConfig.appVersion))
    }

    func portfolio(days: Int = 14) async throws -> PortfolioResponse {
        try await get("/api/mobile/portfolio", query: ["days": String(days)])
    }

    func me() async throws -> Me { try await get("/api/mobile/me") }
    func tasks() async throws -> TasksResponse { try await get("/api/mobile/tasks") }

    struct AnswersBody: Encodable { let answers: [String: AnswerValue]; let via: String }

    func complete(taskId: Int, answers: [String: AnswerValue], via: String) async throws -> CompleteResponse {
        try await post("/api/mobile/tasks/\(taskId)/complete", body: AnswersBody(answers: answers, via: via))
    }

    func skip(taskId: Int) async throws -> CompleteResponse {
        try await post("/api/mobile/tasks/\(taskId)/skip")
    }

    func messages(sinceId: Int = 0) async throws -> [ChatMessage] {
        let r: MessagesResponse = try await get("/api/mobile/messages", query: ["since_id": String(sinceId)])
        return r.messages
    }

    struct TextBody: Encodable { let text: String }
    struct AgentBody: Encodable { let text: String; let channel: String }

    func sendMessage(_ text: String) async throws -> ChatMessage {
        let r: SentMessageResponse = try await post("/api/mobile/messages", body: TextBody(text: text))
        return r.message
    }

    func markMessagesRead() async throws {
        struct R: Codable { let ok: Bool; let count: Int }
        let _: R = try await post("/api/mobile/messages/read")
    }

    func agent(_ text: String, channel: String) async throws -> AgentResponse {
        try await post("/api/mobile/agent", body: AgentBody(text: text, channel: channel))
    }

    func appleSession() async throws -> AppleSession { try await post("/api/mobile/wearables/apple/session") }
    func wearables() async throws -> WearablesResponse { try await get("/api/mobile/wearables") }
    func refreshWearables() async throws -> WearablesResponse { try await post("/api/mobile/wearables/refresh") }
    func wearableLink() async throws -> LinkResponse { try await post("/api/mobile/wearables/link") }
    func progress(days: Int = 14) async throws -> ProgressResponse {
        try await get("/api/mobile/progress", query: ["days": String(days)])
    }
    func uploadGait(_ upload: GaitUpload) async throws -> GaitUploadResponse {
        try await post("/api/mobile/observations/gait", body: upload)
    }
    func signOut() async throws { let _: OKResponse = try await post("/api/mobile/signout") }
}

/// Answers are mixed: numbers for scale/number questions, strings otherwise.
enum AnswerValue: Encodable, Hashable {
    case int(Int)
    case string(String)

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .int(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        }
    }

    var intValue: Int? { if case .int(let v) = self { return v } else { return nil } }
    var stringValue: String? { if case .string(let v) = self { return v } else { return nil } }
}

enum UIDeviceName {
    static var current: String {
        #if canImport(UIKit)
        return UIKitDeviceName.name
        #else
        return "iPhone"
        #endif
    }
}
