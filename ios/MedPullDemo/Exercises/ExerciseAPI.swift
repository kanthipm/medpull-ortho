import Foundation

// The calls behind the exercise screens: the day and the program, starting,
// completing and skipping one exercise, getting a clip of the attempt into
// storage, and reading a demonstration's bytes. They go out on the signed-in
// client (`AppModel.api`): every route is authorised by the person's own app
// session, like the rest of /api/mobile.

extension APIClient {
    // MARK: Feeds

    /// The day's assignments and the week around them. `date` is the
    /// phone's own day, so an evening in Texas is not tomorrow in UTC.
    func exercises(date: String) async throws -> ExercisesResponse {
        try await get("/api/mobile/exercises", query: ["date": date])
    }

    /// The program: `days` days from `start`, each with its exercises and
    /// the counts the calendar's dots draw. The server allows 1 to 35.
    func exerciseProgram(start: String, days: Int) async throws -> ProgramResponse {
        try await get("/api/mobile/exercises/program", query: ["start": start, "days": String(days)])
    }

    // MARK: One exercise

    private struct StartBody: Encodable { let painBefore: Int?; let wearableWorn: Bool? }
    private struct SkipBody: Encodable { let reason: String }

    /// "Start": the pain right now and whether the watch is on. The row
    /// comes back with its session begun; starting again moves the clock. A
    /// done day answers 409.
    func startExercise(id: Int, painBefore: Int?, wearableWorn: Bool?) async throws -> ExerciseAssignment {
        let answer: AssignmentAnswer = try await post(
            "/api/mobile/exercises/\(id)/start", body: StartBody(painBefore: painBefore, wearableWorn: wearableWorn)
        )
        return answer.assignment
    }

    /// "Send": the pain after, how hard it was, what was done, a note, the
    /// staged clip and the session's clock. The server checks what the
    /// therapist asked for (422 in its own sentence), confirms the clip and
    /// writes the thread line. A day already done answers 409.
    func completeExercise(id: Int, body: ExerciseCompletionBody) async throws -> ExerciseAssignment {
        let answer: AssignmentAnswer = try await post("/api/mobile/exercises/\(id)/complete", body: body)
        return answer.assignment
    }

    /// "Can't do it today": the row is skipped with the reason, in the
    /// person's words or none.
    func skipExercise(id: Int, reason: String) async throws -> ExerciseAssignment {
        let answer: AssignmentAnswer = try await post("/api/mobile/exercises/\(id)/skip", body: SkipBody(reason: reason))
        return answer.assignment
    }

    // MARK: The clip of the attempt

    private struct DirectAnswer: Decodable {
        struct Row: Decodable { let id: Int; let contentType: String?; let byteSize: Int?; let filename: String? }
        let attachment: Row
    }

    /// Put a clip in storage and stop before confirming it: the completion
    /// that follows confirms it, so the row is written beside the day it
    /// belongs to (`APIClient.upload` is the thread's version, which
    /// confirms at once). The ticket decides the way: a presigned multipart
    /// POST straight to object storage, or, on a server without one, the
    /// bytes as the body of this API's direct route, which confirms as it
    /// stores. `progress` is the share of the bytes sent, 0 to 1.
    func stageClip(_ data: Data, contentType: String, filename: String?,
                   progress: @escaping @Sendable (Double) -> Void) async throws -> StagedClip {
        let ticket: UploadTicket = try await get(
            "/api/mobile/attachments/upload-ticket",
            query: ["content_type": contentType, "byte_size": String(data.count)]
        )
        guard data.count <= ticket.maxBytes else {
            throw APIError(status: 413, detail: "That clip is over \(ticket.maxBytes / 1_048_576) MB. Try a shorter one.")
        }
        guard !ticket.direct, let upload = ticket.upload, let target = URL(string: upload.url) else {
            return try await stageDirect(data, contentType: contentType, filename: filename, progress: progress)
        }

        // A presigned POST carries its own authorisation in the signed
        // fields, so none of ours goes with it, and the file part is last,
        // which the storage service requires.
        let boundary = "medpull-\(UUID().uuidString)"
        var body = Data()
        for (key, value) in upload.fields {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(key)\"\r\n\r\n\(value)\r\n".utf8))
        }
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(filename ?? "attempt.mp4")\"\r\n".utf8))
        body.append(Data("Content-Type: \(contentType)\r\n\r\n".utf8))
        body.append(data)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        var request = URLRequest(url: target)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 120
        let (_, response) = try await ClipTransfer.send(request, body: body, progress: progress)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            throw APIError(status: status, detail: "The upload was refused by storage. Try again.")
        }
        return StagedClip(storageKey: ticket.storageKey, attachmentId: nil, contentType: contentType,
                          byteSize: data.count, filename: filename)
    }

    private func stageDirect(_ data: Data, contentType: String, filename: String?,
                             progress: @escaping @Sendable (Double) -> Void) async throws -> StagedClip {
        var components = URLComponents(
            url: AppConfig.baseURL.appendingPathComponent("/api/mobile/attachments/direct"),
            resolvingAgainstBaseURL: false
        )!
        if let filename { components.queryItems = [URLQueryItem(name: "filename", value: filename)] }
        var request = URLRequest(url: components.url!)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.timeoutInterval = 120
        let (answer, response) = try await ClipTransfer.send(request, body: data, progress: progress)
        try check(response, answer)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let row = try? decoder.decode(DirectAnswer.self, from: answer).attachment else {
            throw APIError(status: 200, detail: "The clip was stored, but the server’s answer could not be read.")
        }
        return StagedClip(storageKey: nil, attachmentId: row.id, contentType: row.contentType ?? contentType,
                          byteSize: row.byteSize ?? data.count, filename: row.filename ?? filename)
    }

    // MARK: A demonstration's bytes

    /// The bytes behind a demonstration clip's link, read now. A presigned
    /// link is fetched as it is; a path into this API (a server with no
    /// object store) is fetched under the session, which a player given the
    /// bare URL could not do.
    func clipData(from link: String) async throws -> Data {
        guard let url = URL(string: link, relativeTo: AppConfig.baseURL)?.absoluteURL else {
            throw APIError(status: 0, detail: "That clip’s address could not be read.")
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 60
        if Self.needsSession(url), let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await ClipTransfer.fetch(request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            if status == 401 { throw APIError(status: 401, detail: "Your session has ended.") }
            throw APIError(status: status, detail: "The clip could not be loaded.")
        }
        return data
    }

    /// Whether a clip's address is this API's own stream rather than a
    /// presigned object link.
    static func needsSession(_ url: URL) -> Bool {
        let base = AppConfig.baseURL
        return url.host == base.host && url.port == base.port && url.path.hasPrefix("/api/")
    }

    // MARK: The server

    /// `GET /api/health`: whether this server is the demo, and when its
    /// people were last brought up to today.
    func serverHealth() async throws -> ServerHealth { try await get("/api/health") }
}

/// What `/api/health` says that the demo app shows.
struct ServerHealth: Decodable, Equatable {
    /// True on the public demo (and on a laptop started with DEMO_MODE).
    let demo: Bool
    /// "yyyy-MM-dd": the day the showcase's people were last re-anchored to,
    /// or nil when the server does not say.
    let filledOn: String?

    private enum CodingKeys: String, CodingKey { case demo, showcase }
    private enum ShowcaseKeys: String, CodingKey { case filledOn }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        demo = c.lenient(Bool.self, .demo) ?? false
        filledOn = (try? c.nestedContainer(keyedBy: ShowcaseKeys.self, forKey: .showcase))?
            .lenient(String.self, .filledOn)
    }
}

/// One upload or download of a clip, outside `APIClient`'s JSON path: the
/// body is bytes, and an upload reports how much of it has gone.
enum ClipTransfer {
    private final class Progress: NSObject, URLSessionTaskDelegate {
        let report: @Sendable (Double) -> Void
        init(_ report: @escaping @Sendable (Double) -> Void) { self.report = report }

        func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
                        totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
            guard totalBytesExpectedToSend > 0 else { return }
            report(min(1, Double(totalBytesSent) / Double(totalBytesExpectedToSend)))
        }
    }

    static func send(_ request: URLRequest, body: Data,
                     progress: @escaping @Sendable (Double) -> Void) async throws -> (Data, URLResponse) {
        do {
            let answer = try await URLSession.shared.upload(for: request, from: body, delegate: Progress(progress))
            progress(1)
            return answer
        } catch {
            throw mapped(error)
        }
    }

    static func fetch(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await URLSession.shared.data(for: request)
        } catch {
            throw mapped(error)
        }
    }

    /// A cancelled transfer is the screen going away, not a failure; any
    /// other transport error reads as the app's usual sentence.
    private static func mapped(_ error: Error) -> Error {
        if error is CancellationError { return error }
        if let e = error as? URLError, e.code == .cancelled { return CancellationError() }
        return APIError(status: 0, detail: "Can’t reach MedPull right now. Check your connection.")
    }
}
