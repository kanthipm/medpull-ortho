import AVFoundation
import AVKit
import SwiftUI
import UIKit

// The clips on the exercise screens: the therapist's demonstration, looping
// and muted, and the clip the person sent back, with its controls.
//
// A clip's link is good for minutes (a presigned URL) or needs the session
// (a path into this API on a server with no object store), so no link is
// ever kept or handed to a player. The bytes are fetched once, at the
// moment a tile needs them, from the link in the feed as it is then, and the
// player loops a file on this phone: a guided session can sit on one
// exercise far longer than a link lives.

/// What a clip tile plays.
enum ClipSource: Hashable {
    /// The therapist's demonstration for one assigned exercise. The row is
    /// read again for its link when the bytes are fetched.
    case demonstration(assignmentId: Int, mediaId: Int)
    /// The clip the person sent with a completion: a thread attachment.
    case attachment(id: Int)
    /// A clip already on this phone: one just recorded, or the sample.
    case file(URL)
}

extension ExerciseAssignment {
    /// The therapist's demonstration, when the row has one that can be
    /// played (a clip still waiting for approval arrives with no link).
    var demonstration: ClipSource? {
        guard let video, video.url != nil else { return nil }
        return .demonstration(assignmentId: id, mediaId: video.id)
    }
}

/// Clips as files, by what they are (a demonstration's media id, an
/// attachment's id): the same clip is fetched once however many screens
/// show it. Files live in the temporary directory for the life of the
/// process.
@MainActor
final class ClipLibrary {
    static let shared = ClipLibrary()

    private var files: [String: URL] = [:]
    private var loading: [String: Task<URL, Error>] = [:]

    private static var directory: URL {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("medpull-demo-clips")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    func file(for source: ClipSource, store: ExerciseStore, api: APIClient) async throws -> URL {
        let key: String
        switch source {
        case .file(let url): return url
        case .demonstration(_, let mediaId): key = "demonstration-\(mediaId)"
        case .attachment(let id): key = "attempt-\(id)"
        }
        if let file = files[key], FileManager.default.fileExists(atPath: file.path) { return file }
        if let running = loading[key] { return try await running.value }
        let task = Task { () throws -> URL in
            let (data, type) = try await Self.bytes(for: source, store: store, api: api)
            let file = Self.directory.appendingPathComponent(key + (type == "video/quicktime" ? ".mov" : ".mp4"))
            try data.write(to: file, options: .atomic)
            return file
        }
        loading[key] = task
        defer { loading[key] = nil }
        let file = try await task.value
        files[key] = file
        return file
    }

    private static func bytes(for source: ClipSource, store: ExerciseStore,
                              api: APIClient) async throws -> (Data, String) {
        switch source {
        case .file(let url):
            return (try Data(contentsOf: url), "video/mp4")
        case .attachment(let id):
            return (try await api.attachmentData(id: id), "video/mp4")
        case .demonstration(let assignmentId, _):
            func link() throws -> (String, String) {
                guard let video = store.assignment(assignmentId)?.video, let url = video.url else {
                    throw APIError(status: 404, detail: "This exercise has no clip any more.")
                }
                return (url, video.contentType)
            }
            let (first, type) = try link()
            do {
                return (try await api.clipData(from: first), type)
            } catch let error as APIError where error.status == 403 || error.status == 400 {
                // The link had expired by the time it was used: read the
                // calendar again and use the one it carries now.
                await store.refreshAll()
                let (fresh, type) = try link()
                return (try await api.clipData(from: fresh), type)
            }
        }
    }

    /// A demonstration's bytes, for the demo's "Use a sample clip".
    func data(for source: ClipSource, store: ExerciseStore, api: APIClient) async throws -> Data {
        try Data(contentsOf: try await file(for: source, store: store, api: api))
    }
}

// MARK: - The tile

/// A clip in the hero's frame: the video once its bytes are here, a spinner
/// while they come, a sentence and a retry when they do not. With no source
/// it is the gradient tile that says there is no clip yet.
///
/// `loop` is the therapist's demonstration: playing on its own, muted, round
/// and round, with nothing to tap. Without it the clip has the system's
/// controls (the person's own attempt).
struct ClipTile: View {
    let source: ClipSource?
    var loop = true
    /// What VoiceOver calls the clip.
    let label: String
    /// Shown when there is no clip: the exercise's steps stand in.
    var emptyTitle = "No clip for this one yet"
    var emptyDetail = "The steps are what to follow."
    /// The tallest the tile may be: a clip filmed upright would otherwise
    /// take most of a phone's screen. Narrower, never cropped.
    var maxHeight: CGFloat = 400

    @Environment(ExerciseStore.self) private var store
    @Environment(AppModel.self) private var app
    @State private var file: URL?
    @State private var failure: String?
    @State private var attempt = 0
    /// Width over height of the video itself, once known: a clip filmed on
    /// a phone held upright gets a taller tile than one filmed on its side.
    @State private var ratio: CGFloat = 4.0 / 3.0

    private struct LoadKey: Hashable {
        let source: ClipSource?
        let attempt: Int
    }

    var body: some View {
        Group {
            if source == nil {
                EmptyClipTile(title: emptyTitle, detail: emptyDetail)
            } else {
                ZStack {
                    Color(red: 0.07, green: 0.07, blue: 0.075)
                    if let file {
                        if loop {
                            LoopingVideo(url: file)
                        } else {
                            ControlledVideo(url: file)
                        }
                    } else if let failure {
                        VStack(spacing: 10) {
                            Label(failure, systemImage: "video.slash")
                                .mpFont(.copyMedium).foregroundStyle(.white.opacity(0.9))
                                .multilineTextAlignment(.center)
                            Button("Try again") { attempt += 1 }
                                .buttonStyle(MPButtonStyle(kind: .gray))
                                .controlSize(.small)
                        }
                        .padding(16)
                    } else {
                        ProgressView().tint(.white)
                    }
                }
                .clipShape(MP.surfaceShape)
                .overlay(MP.surfaceShape.strokeBorder(MP.glassRing, lineWidth: 0.5))
                .aspectRatio(ratio, contentMode: .fit)
                .frame(maxWidth: .infinity, maxHeight: maxHeight)
                .accessibilityElement(children: file == nil ? .contain : .ignore)
                .accessibilityLabel(Text(label))
                .accessibilityAddTraits(file == nil ? [] : .startsMediaSession)
            }
        }
        .task(id: LoadKey(source: source, attempt: attempt)) { await load() }
    }

    private func load() async {
        guard let source else { return }
        failure = nil
        do {
            let url = try await ClipLibrary.shared.file(for: source, store: store, api: app.api)
            if let shape = await Self.shape(of: url) { ratio = shape }
            file = url
        } catch {
            if let e = error as? APIError, e.isUnauthorized { app.note(error) }
            guard ExerciseStore.sentence(for: error) != nil else { return }
            file = nil
            failure = "This clip could not be loaded"
        }
    }

    /// The picture's own shape, held between a phone upright (3:4) and a
    /// wide clip (16:9) so no tile takes the whole screen or shrinks to a
    /// ribbon.
    private static func shape(of url: URL) async -> CGFloat? {
        let asset = AVURLAsset(url: url)
        guard let track = try? await asset.loadTracks(withMediaType: .video).first,
              let (size, transform) = try? await track.load(.naturalSize, .preferredTransform) else { return nil }
        let shown = size.applying(transform)
        let width = abs(shown.width), height = abs(shown.height)
        guard width > 0, height > 0 else { return nil }
        return min(16.0 / 9.0, max(3.0 / 4.0, width / height))
    }
}

/// The tile for an exercise with no demonstration: the screen's one
/// gradient, with the words in its dark top band.
private struct EmptyClipTile: View {
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).mpFont(.ledeMedium).foregroundStyle(.white)
            Text(detail).mpFont(.copy).foregroundStyle(.white.opacity(0.92))
            Spacer(minLength: 0)
            HStack {
                Spacer()
                Image(systemName: "figure.strengthtraining.functional")
                    .font(.system(size: 54, weight: .light))
                    .foregroundStyle(.white.opacity(0.9))
                    .accessibilityHidden(true)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .background {
            GradientFill(gradient: .sage)
                .overlay {
                    // The scrim `GradientTile` lays under its white type.
                    LinearGradient(colors: [Color(red: 24 / 255, green: 22 / 255, blue: 14 / 255).opacity(0.3), .clear],
                                   startPoint: .top, endPoint: .center)
                }
                .clipShape(MP.surfaceShape)
                .overlay(MP.surfaceShape.strokeBorder(.white.opacity(0.14), lineWidth: 0.5))
                .shadow(color: MP.shadow.opacity(0.18), radius: 14, y: 8)
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Players

/// A file playing on its own, muted, round and round.
private struct LoopingVideo: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> LoopingPlayerView {
        let view = LoopingPlayerView()
        view.play(url)
        return view
    }

    func updateUIView(_ view: LoopingPlayerView, context: Context) { view.play(url) }

    static func dismantleUIView(_ view: LoopingPlayerView, coordinator: ()) { view.stop() }
}

final class LoopingPlayerView: UIView {
    override static var layerClass: AnyClass { AVPlayerLayer.self }

    private var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
    private var player: AVQueuePlayer?
    private var looper: AVPlayerLooper?
    private var current: URL?
    private var observer: NSObjectProtocol?

    func play(_ url: URL) {
        guard url != current else { return }
        stop()
        current = url
        // Muted and mixed in: a lifter's own music keeps playing.
        try? AVAudioSession.sharedInstance().setCategory(.ambient, mode: .default, options: [.mixWithOthers])
        let queue = AVQueuePlayer()
        queue.isMuted = true
        // The guided session keeps the screen awake itself; a clip left
        // open on the exercise screen should not.
        queue.preventsDisplaySleepDuringVideoPlayback = false
        looper = AVPlayerLooper(player: queue, templateItem: AVPlayerItem(url: url))
        playerLayer.player = queue
        playerLayer.videoGravity = .resizeAspect
        player = queue
        queue.play()
        // The system pauses a player when the app leaves the foreground.
        observer = NotificationCenter.default.addObserver(
            forName: UIApplication.didBecomeActiveNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.player?.play() }
    }

    func stop() {
        if let observer { NotificationCenter.default.removeObserver(observer) }
        observer = nil
        player?.pause()
        looper?.disableLooping()
        looper = nil
        player = nil
        playerLayer.player = nil
        current = nil
    }

    deinit {
        if let observer { NotificationCenter.default.removeObserver(observer) }
    }
}

/// A file with the system's controls: the person's own clip.
private struct ControlledVideo: View {
    let url: URL
    @State private var player: AVPlayer?

    var body: some View {
        Group {
            if let player {
                VideoPlayer(player: player)
            } else {
                Color.clear
            }
        }
        .task(id: url) { player = AVPlayer(url: url) }
        .onDisappear { player?.pause() }
    }
}
