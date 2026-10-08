import AVFoundation
import AVKit
import Foundation
import SwiftUI
import UniformTypeIdentifiers
#if canImport(UIKit)
import UIKit
#endif

/// Photos, clips, voice notes and files on the thread, on the app's side:
/// getting one ready to send, recording one, and drawing one that arrived.

// MARK: - Getting a file ready to send

enum AttachmentPrep {
    /// Long edge, in pixels. A wound photograph is read on a laptop, not
    /// enlarged in a darkroom, and twelve megapixels of it costs a patient
    /// their data allowance for no clinical gain.
    static let maxEdge: CGFloat = 2048
    static let quality: CGFloat = 0.82
    /// The server's cap for a clip or a recording (blobs.MAX_MEDIA_BYTES).
    static let maxMediaBytes = 48 * 1024 * 1024
    /// An MP4 under this goes as it is; anything else is re-encoded to 540p
    /// H.264, which every browser on the console side can play and which
    /// keeps a minute of a knee bending under a few megabytes.
    static let videoPassThroughBytes = 8 * 1024 * 1024

    /// What the server accepts (app/storage/blobs.ALLOWED_TYPES).
    static let acceptedFiles: [UTType] = [.pdf, .jpeg, .png, .webP, .heic,
                                          .movie, .mpeg4Movie, .quickTimeMovie,
                                          .mpeg4Audio, .mp3, .wav, .audio]

    struct Ready {
        let data: Data
        let contentType: String
        let filename: String?
    }

    /// A photo from the library, as something the other side can open.
    ///
    /// An iPhone stores photos as HEIC, and nothing on the receiving end
    /// draws HEIC: not a browser showing the console thread, not the
    /// clinician's desktop. So a picked photo is re-encoded as JPEG here
    /// rather than arriving as a file nobody can look at.
    static func photo(_ data: Data, name: String? = nil) -> Ready? {
        #if canImport(UIKit)
        guard let image = UIImage(data: data) else { return nil }
        let scaled = downscaled(image)
        guard let jpeg = scaled.jpegData(compressionQuality: quality) else { return nil }
        return Ready(data: jpeg, contentType: "image/jpeg", filename: name ?? "photo.jpg")
        #else
        return Ready(data: data, contentType: "image/jpeg", filename: name ?? "photo.jpg")
        #endif
    }

    /// A file the person chose in the document picker. PDFs and images go as
    /// they are; a picked HEIC is re-encoded for the same reason; a clip is
    /// shrunk; a recording goes as it is.
    static func file(at url: URL) async -> Ready? {
        let type = UTType(filenameExtension: url.pathExtension.lowercased())
        let name = url.lastPathComponent
        if let type, type.conforms(to: .movie) || type.conforms(to: .video) {
            return await video(at: url)
        }
        if let type, type.conforms(to: .audio) {
            return audio(at: url)
        }
        guard let data = try? Data(contentsOf: url) else { return nil }
        if type == .heic || type == .heif {
            return photo(data, name: (name as NSString).deletingPathExtension + ".jpg")
        }
        guard let mime = type?.preferredMIMEType else { return nil }
        return Ready(data: data, contentType: mime, filename: name)
    }

    /// A clip, as something the other side can play.
    ///
    /// The camera roll holds HEVC QuickTime at 1080p or 4K, which a console
    /// browser cannot play and a patient's data allowance cannot afford. A
    /// small MP4 is passed through; everything else is exported at 540p
    /// H.264 with the moov atom at the front, so it starts playing before
    /// it has finished downloading.
    static func video(at url: URL) async -> Ready? {
        let name = (url.lastPathComponent as NSString).deletingPathExtension
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0
        if url.pathExtension.lowercased() == "mp4", size > 0, size <= videoPassThroughBytes,
           let data = try? Data(contentsOf: url) {
            return Ready(data: data, contentType: "video/mp4", filename: name + ".mp4")
        }
        let asset = AVURLAsset(url: url)
        guard let export = AVAssetExportSession(asset: asset, presetName: AVAssetExportPreset960x540)
        else { return nil }
        let out = FileManager.default.temporaryDirectory
            .appendingPathComponent("medpull-clip-\(UUID().uuidString).mp4")
        export.shouldOptimizeForNetworkUse = true
        defer { try? FileManager.default.removeItem(at: out) }
        if #available(iOS 18, *) {
            do { try await export.export(to: out, as: .mp4) } catch { return nil }
        } else {
            export.outputURL = out
            export.outputFileType = .mp4
            await export.export()
            guard export.status == .completed else { return nil }
        }
        guard let data = try? Data(contentsOf: out), data.count <= maxMediaBytes else { return nil }
        return Ready(data: data, contentType: "video/mp4", filename: name + ".mp4")
    }

    /// A recording the person already has. The three formats the server
    /// takes; the type is spelt the way the server stores it.
    static func audio(at url: URL) -> Ready? {
        guard let data = try? Data(contentsOf: url), data.count <= maxMediaBytes else { return nil }
        let mime: String
        switch url.pathExtension.lowercased() {
        case "m4a", "aac", "mp4": mime = "audio/mp4"
        case "mp3": mime = "audio/mpeg"
        case "wav": mime = "audio/wav"
        default: return nil
        }
        return Ready(data: data, contentType: mime, filename: url.lastPathComponent)
    }

    /// The app's own voice note, straight off the recorder.
    static func voiceNote(at url: URL) -> Ready? {
        guard let data = try? Data(contentsOf: url), data.count <= maxMediaBytes else { return nil }
        let stamp = Date().formatted(.dateTime.month(.abbreviated).day().hour().minute())
        return Ready(data: data, contentType: "audio/mp4", filename: "Voice note \(stamp).m4a")
    }

    #if canImport(UIKit)
    private static func downscaled(_ image: UIImage) -> UIImage {
        let longest = max(image.size.width, image.size.height)
        guard longest > maxEdge else { return image }
        let ratio = maxEdge / longest
        let size = CGSize(width: image.size.width * ratio, height: image.size.height * ratio)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
    #endif
}

/// A clip picked from the photo library. The picker hands movies over as
/// a file it deletes when the closure returns, so the file is copied out
/// before anything slow (the export) runs on it.
struct PickedMovie: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let ext = received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension
            let copy = FileManager.default.temporaryDirectory
                .appendingPathComponent("medpull-pick-\(UUID().uuidString).\(ext)")
            try? FileManager.default.removeItem(at: copy)
            try FileManager.default.copyItem(at: received.file, to: copy)
            return Self(url: copy)
        }
    }
}

// MARK: - Recording a voice note

/// The microphone, for a message rather than a transcript: AAC in an MP4
/// container, mono, which is what the server stores as audio/mp4 and what
/// the console's browser plays. Nothing is kept past the upload.
@MainActor
@Observable
final class VoiceNoteRecorder: NSObject, AVAudioRecorderDelegate {
    private(set) var isRecording = false
    private(set) var elapsed: TimeInterval = 0
    /// 0...1, for the meter beside the clock.
    private(set) var level: Double = 0
    private(set) var errorText: String?
    /// Long enough for a message, short enough to upload on a bad signal.
    static let maxSeconds: TimeInterval = 180

    private var recorder: AVAudioRecorder?
    private var ticker: Task<Void, Never>?
    private var fileURL: URL?

    var elapsedText: String {
        let s = Int(elapsed)
        return String(format: "%d:%02d", s / 60, s % 60)
    }

    func start() async {
        guard !isRecording else { return }
        errorText = nil
        guard await AVAudioApplication.requestRecordPermission() else {
            errorText = "Allow the microphone in Settings to record a voice note."
            return
        }
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetooth])
            try session.setActive(true)
        } catch {
            errorText = "The microphone could not be started: \(error.localizedDescription)"
            return
        }
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("medpull-note-\(UUID().uuidString).m4a")
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVEncoderBitRateKey: 64_000,
            AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
        ]
        do {
            let r = try AVAudioRecorder(url: url, settings: settings)
            r.delegate = self
            r.isMeteringEnabled = true
            guard r.record(forDuration: Self.maxSeconds) else {
                errorText = "The microphone could not be started."
                return
            }
            recorder = r
            fileURL = url
            isRecording = true
            elapsed = 0
            ticker = Task { [weak self] in
                while let self, !Task.isCancelled, self.isRecording {
                    try? await Task.sleep(for: .milliseconds(100))
                    guard let r = self.recorder else { break }
                    r.updateMeters()
                    self.elapsed = r.currentTime
                    // -60 dB (silence) to 0 dB, as a bar.
                    self.level = max(0, min(1, (Double(r.averagePower(forChannel: 0)) + 50) / 50))
                }
            }
        } catch {
            errorText = "Recording failed: \(error.localizedDescription)"
        }
    }

    /// Stop and hand back the file, or nil when nothing worth sending was
    /// recorded (under half a second is a tap, not a note).
    func stop() -> URL? {
        guard isRecording, let r = recorder else { return nil }
        let length = r.currentTime
        r.stop()
        finish()
        guard length >= 0.5, let url = fileURL else {
            if let url = fileURL { try? FileManager.default.removeItem(at: url) }
            return nil
        }
        return url
    }

    func cancel() {
        recorder?.stop()
        if let url = fileURL { try? FileManager.default.removeItem(at: url) }
        finish()
    }

    private func finish() {
        ticker?.cancel()
        ticker = nil
        recorder = nil
        isRecording = false
        level = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        // The time limit ran out: the composer notices isRecording flip and
        // treats it as a stop.
        Task { @MainActor in
            if self.isRecording { self.isRecording = false }
        }
    }
}

// MARK: - Drawing one that arrived

/// Decoded images, kept by content hash.
///
/// The links that serve them are minted per request and expire in minutes,
/// so the bytes cannot be cached by URL — but the hash is the bytes, so the
/// same photo is fetched once however many times the thread redraws (and it
/// redraws every twenty seconds while Messages is open).
@MainActor
@Observable
final class AttachmentImages {
    static let shared = AttachmentImages()

    private var images: [String: Image] = [:]
    private var order: [String] = []
    private var failed: Set<String> = []
    private var loading: Set<String> = []
    /// Enough for a long scroll back through a thread, bounded so a year of
    /// photographs cannot sit in memory.
    private let limit = 48

    private func key(_ a: ChatAttachment) -> String { a.sha256 ?? "id:\(a.id)" }

    func image(for a: ChatAttachment) -> Image? { images[key(a)] }
    func didFail(_ a: ChatAttachment) -> Bool { failed.contains(key(a)) }

    func load(_ a: ChatAttachment, using api: APIClient) async {
        let k = key(a)
        guard images[k] == nil, !failed.contains(k), !loading.contains(k) else { return }
        loading.insert(k)
        defer { loading.remove(k) }
        do {
            let data = try await api.attachmentData(id: a.id)
            #if canImport(UIKit)
            guard let ui = UIImage(data: data) else {
                failed.insert(k)
                return
            }
            store(k, Image(uiImage: ui))
            #endif
        } catch is CancellationError {
            // The view went away mid-fetch. Not a failure: leave the slot
            // empty so the next appearance tries again.
        } catch {
            failed.insert(k)
        }
    }

    private func store(_ k: String, _ image: Image) {
        images[k] = image
        order.append(k)
        while order.count > limit, let oldest = order.first {
            order.removeFirst()
            if oldest != k { images.removeValue(forKey: oldest) }
        }
    }
}

/// One photo on a thread line: the image once it is here, a placeholder
/// while it is coming, and a plain line of words if it cannot be shown.
struct AttachmentImageView: View {
    @Environment(AppModel.self) private var app
    private let cache = AttachmentImages.shared
    let attachment: ChatAttachment
    var maxHeight: CGFloat = 220

    var body: some View {
        Group {
            if let image = cache.image(for: attachment) {
                image
                    .resizable()
                    .scaledToFill()
                    .frame(maxWidth: 240, maxHeight: maxHeight)
                    .clipped()
            } else if cache.didFail(attachment) {
                HStack(spacing: 6) {
                    Image(systemName: "photo.badge.exclamationmark")
                    Text("This photo could not be loaded").font(.labelMedium)
                }
                .foregroundStyle(MP.muted)
                .padding(.horizontal, 12).padding(.vertical, 10)
            } else {
                MP.surfaceShape
                    .fill(MP.soft)
                    .frame(width: 180, height: 130)
                    .overlay(ProgressView())
            }
        }
        // 14 was not a radius, it was drift: a photo is content, so it takes
        // the 12pt surface radius. One shape for the clip and the edge.
        .clipShape(MP.surfaceShape)
        .overlay(MP.surfaceShape.strokeBorder(MP.line, lineWidth: 1))
        .task(id: attachment.id) { await cache.load(attachment, using: app.api) }
    }
}

/// Clips and recordings, kept as files by content hash: a player wants a
/// URL, not bytes, and a thread that redraws every twenty seconds must
/// not fetch a video every time.
@MainActor
@Observable
final class AttachmentMedia {
    static let shared = AttachmentMedia()

    private var urls: [String: URL] = [:]
    private var failed: Set<String> = []
    private var loading: Set<String> = []

    private func key(_ a: ChatAttachment) -> String { a.sha256 ?? "id:\(a.id)" }

    func url(for a: ChatAttachment) -> URL? { urls[key(a)] }
    func didFail(_ a: ChatAttachment) -> Bool { failed.contains(key(a)) }
    func isLoading(_ a: ChatAttachment) -> Bool { loading.contains(key(a)) }

    private static var directory: URL {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("medpull-media")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    func load(_ a: ChatAttachment, using api: APIClient) async {
        let k = key(a)
        guard urls[k] == nil, !failed.contains(k), !loading.contains(k) else { return }
        let ext = a.isVideo ? "mp4" : a.contentType == "audio/mpeg" ? "mp3"
            : a.contentType == "audio/wav" ? "wav" : "m4a"
        let file = Self.directory.appendingPathComponent(k.replacingOccurrences(of: ":", with: "-") + "." + ext)
        if FileManager.default.fileExists(atPath: file.path) {
            urls[k] = file
            return
        }
        loading.insert(k)
        defer { loading.remove(k) }
        do {
            let data = try await api.attachmentData(id: a.id)
            try data.write(to: file, options: .atomic)
            urls[k] = file
        } catch is CancellationError {
            // Left empty so the next appearance tries again.
        } catch {
            failed.insert(k)
        }
    }
}

/// A clip on a thread line: the player once the file is here, a
/// placeholder while it is coming, a line of words if it cannot be shown.
struct AttachmentVideoView: View {
    @Environment(AppModel.self) private var app
    private let cache = AttachmentMedia.shared
    let attachment: ChatAttachment
    @State private var player: AVPlayer?

    var body: some View {
        Group {
            if let player {
                VideoPlayer(player: player)
                    .frame(width: 240, height: 180)
            } else if cache.didFail(attachment) {
                HStack(spacing: 6) {
                    Image(systemName: "video.slash")
                    Text("This video could not be loaded").font(.labelMedium)
                }
                .foregroundStyle(MP.muted)
                .padding(.horizontal, 12).padding(.vertical, 10)
            } else {
                MP.surfaceShape
                    .fill(MP.soft)
                    .frame(width: 240, height: 180)
                    .overlay(ProgressView())
            }
        }
        .clipShape(MP.surfaceShape)
        .overlay(MP.surfaceShape.strokeBorder(MP.line, lineWidth: 1))
        .task(id: attachment.id) {
            await cache.load(attachment, using: app.api)
            if let url = cache.url(for: attachment), player == nil {
                player = AVPlayer(url: url)
            }
        }
        .onDisappear { player?.pause() }
        .accessibilityLabel(Text(attachment.displayName))
    }
}

/// One recording playing at a time, app-wide: tapping a second note stops
/// the first, the way Messages does it.
@MainActor
@Observable
final class AudioClipPlayer: NSObject, AVAudioPlayerDelegate {
    static let shared = AudioClipPlayer()

    private(set) var playingKey: String?
    private(set) var progress: Double = 0
    private var player: AVAudioPlayer?
    private var ticker: Task<Void, Never>?

    func isPlaying(_ key: String) -> Bool { playingKey == key }

    func toggle(key: String, url: URL) {
        if playingKey == key {
            stop()
            return
        }
        stop()
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try session.setActive(true)
            let p = try AVAudioPlayer(contentsOf: url)
            p.delegate = self
            p.play()
            player = p
            playingKey = key
            ticker = Task { [weak self] in
                while let self, !Task.isCancelled, let p = self.player {
                    self.progress = p.duration > 0 ? p.currentTime / p.duration : 0
                    try? await Task.sleep(for: .milliseconds(100))
                }
            }
        } catch {
            stop()
        }
    }

    func stop() {
        ticker?.cancel()
        ticker = nil
        player?.stop()
        player = nil
        playingKey = nil
        progress = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }

    static func duration(of url: URL) -> TimeInterval? {
        (try? AVAudioPlayer(contentsOf: url))?.duration
    }
}

/// A voice note on a thread line: play, the clock, a thin progress line.
struct AttachmentAudioView: View {
    @Environment(AppModel.self) private var app
    private let cache = AttachmentMedia.shared
    private let clips = AudioClipPlayer.shared
    let attachment: ChatAttachment
    let mine: Bool
    @State private var duration: TimeInterval?

    private var key: String { attachment.sha256 ?? "id:\(attachment.id)" }
    private var playing: Bool { clips.isPlaying(key) }

    private var clock: String {
        guard let duration else { return attachment.sizeLabel }
        let shown = playing ? duration * clips.progress : duration
        let s = Int(shown.rounded())
        return String(format: "%d:%02d", s / 60, s % 60)
    }

    var body: some View {
        HStack(spacing: 10) {
            Button {
                guard let url = cache.url(for: attachment) else { return }
                clips.toggle(key: key, url: url)
            } label: {
                Image(systemName: playing ? "pause.fill" : "play.fill")
                    .font(.systemGlyphs(15, weight: .semibold))
                    .foregroundStyle(MP.onAction)
                    .frame(width: 36, height: 36)
                    .background(Circle().fill(cache.url(for: attachment) == nil ? MP.disabledFill : MP.action))
                    .contentShape(Circle())
            }
            .buttonStyle(ComposerSendStyle())
            .disabled(cache.url(for: attachment) == nil)
            .accessibilityLabel(playing ? "Pause" : "Play \(attachment.displayName)")
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    Image(systemName: "waveform").font(.labelMedium).foregroundStyle(MP.brandInk)
                    Text(attachment.filename == nil ? "Voice note" : attachment.displayName)
                        .font(.copyMedium).foregroundStyle(MP.ink).lineLimit(1)
                    Spacer(minLength: 4)
                    if cache.didFail(attachment) {
                        Text("Could not load").font(.labelMedium).foregroundStyle(MP.riskMed)
                    } else if cache.url(for: attachment) == nil {
                        ProgressView().controlSize(.mini)
                    } else {
                        Text(clock).font(.figuresLabel).foregroundStyle(MP.muted)
                    }
                }
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        MP.capsuleShape.fill(MP.track)
                        MP.capsuleShape.fill(MP.brand)
                            .frame(width: proxy.size.width * (playing ? clips.progress : 0))
                    }
                }
                .frame(height: 4)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
        .frame(width: 240)
        .background(MP.surfaceShape.fill(MP.panel))
        .overlay(MP.surfaceShape.strokeBorder(MP.line, lineWidth: 1))
        .task(id: attachment.id) {
            await cache.load(attachment, using: app.api)
            if let url = cache.url(for: attachment), duration == nil {
                duration = AudioClipPlayer.duration(of: url)
            }
        }
    }
}

/// A document on a thread line. A name and a size, because that is what
/// decides whether somebody opens it now.
struct AttachmentFileView: View {
    let attachment: ChatAttachment

    var body: some View {
        HStack(spacing: 8) {
            // `brandInk`, not `brand`: a glyph set with `foregroundStyle` is
            // a foreground (sage text, 7.25 light / 10.53 dark on panel).
            Image(systemName: attachment.contentType == "application/pdf" ? "doc.richtext" : "doc")
                .font(.copyLarge)
                .foregroundStyle(MP.brandInk)
            VStack(alignment: .leading, spacing: 1) {
                Text(attachment.displayName)
                    .font(.copyMedium)
                    .foregroundStyle(MP.ink)
                    .lineLimit(1)
                Text(attachment.sizeLabel)
                    .font(.labelMedium)
                    .foregroundStyle(MP.muted)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
        .background(MP.surfaceShape.fill(MP.panel))
        // ONE edge, no shadow: `panel` is 1.13:1 against canvas light and
        // 1.07:1 dark, so the hairline is what says "a file is attached here".
        .overlay(MP.surfaceShape.strokeBorder(MP.line, lineWidth: 1))
    }
}

/// Everything attached to one line, in the bubble's own alignment.
struct AttachmentStrip: View {
    let attachments: [ChatAttachment]
    let mine: Bool

    var body: some View {
        if !attachments.isEmpty {
            VStack(alignment: mine ? .trailing : .leading, spacing: 6) {
                ForEach(attachments) { a in
                    if a.isWithdrawn {
                        // NO `.italic()`. The bundled face ships no italic file,
                        // so SwiftUI shears the roman — synthetic obliquing,
                        // the same defect class as synthetic bold. The
                        // distinction is carried by weight and colour instead:
                        // 12pt / 400 on `muted`, against the live filename's
                        // 14pt / 500 on `ink` two lines above, and the copy
                        // ("taken back") already names the state. `faint` is
                        // 2.59:1 on panel and carries no text.
                        Text("\(a.noun.prefix(1).uppercased() + a.noun.dropFirst()) taken back")
                            .font(.label)
                            .foregroundStyle(MP.muted)
                    } else if a.isImage {
                        AttachmentImageView(attachment: a)
                    } else if a.isVideo {
                        AttachmentVideoView(attachment: a)
                    } else if a.isAudio {
                        AttachmentAudioView(attachment: a, mine: mine)
                    } else {
                        AttachmentFileView(attachment: a)
                    }
                }
            }
        }
    }
}
