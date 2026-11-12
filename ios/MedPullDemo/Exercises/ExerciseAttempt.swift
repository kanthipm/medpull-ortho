import Observation
import PhotosUI
import SwiftUI

// The clip of the attempt: getting one (the camera, the photo library or, on
// a demo server, a sample), and getting it into storage so the completion can
// carry it. The completion sheet and the guided session both use this.

/// A clip of the attempt, ready to upload.
struct ClipTake: Equatable {
    let data: Data
    let contentType: String
    let filename: String
    /// A file on this phone to preview it from.
    let preview: URL
    /// True for the demo's sample clip, which every screen that shows the
    /// take says in words: it is not the person's own recording.
    let isSample: Bool

    static func == (a: Self, b: Self) -> Bool { a.preview == b.preview }
}

/// One attempt's clip, from nothing to staged in storage.
@Observable
@MainActor
final class AttemptClip {
    enum Phase: Equatable {
        case none
        /// The camera's file is being made into something every browser on
        /// the therapist's side can play.
        case preparing
        /// In hand, not yet sent.
        case taken(ClipTake)
        /// Going up: the share of the bytes sent, 0 to 1.
        case uploading(ClipTake, Double)
        /// In storage, waiting for the completion to claim it.
        case staged(ClipTake, StagedClip)
        /// Why it did not work. The take is kept when only the upload failed.
        case failed(String, ClipTake?)
    }

    private(set) var phase: Phase = .none
    /// A pick that was removed before it finished must not come back.
    private var generation = 0

    var take: ClipTake? {
        switch phase {
        case .taken(let take), .uploading(let take, _), .staged(let take, _): return take
        case .failed(_, let take): return take
        default: return nil
        }
    }

    var staged: StagedClip? {
        if case .staged(_, let staged) = phase { return staged }
        return nil
    }

    var isWorking: Bool {
        switch phase {
        case .preparing, .uploading: return true
        default: return false
        }
    }

    private static func write(_ data: Data, name: String) -> URL? {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("medpull-demo-clips")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent(name)
        do {
            try data.write(to: file, options: .atomic)
            return file
        } catch {
            return nil
        }
    }

    /// A clip from the camera or the photo library, as a file. It is
    /// re-encoded the way the thread's clips are (`AttachmentPrep.video`).
    func use(movieAt url: URL) async {
        generation += 1
        let mine = generation
        phase = .preparing
        let ready = await AttachmentPrep.video(at: url)
        guard mine == generation else { return }
        guard let ready, let preview = Self.write(ready.data, name: "take-\(UUID().uuidString).mp4") else {
            phase = .failed("That clip could not be used. Record a shorter one, or try again.", nil)
            return
        }
        phase = .taken(ClipTake(data: ready.data, contentType: ready.contentType, filename: "attempt.mp4",
                                preview: preview, isSample: false))
    }

    /// The demo's stand-in for a recording: the therapist's own
    /// demonstration when the exercise has one, else the small clip the app
    /// carries. Offered on a demo server only, where a presenter may be on a
    /// simulator with no camera, and never called anything but a sample.
    func useSample(for a: ExerciseAssignment, store: ExerciseStore, api: APIClient) async {
        generation += 1
        let mine = generation
        phase = .preparing
        var data: Data?
        var type = "video/mp4"
        if let source = a.demonstration, let video = a.video, video.contentType.hasPrefix("video/") {
            data = try? await ClipLibrary.shared.data(for: source, store: store, api: api)
            type = video.contentType
        }
        if data == nil, let bundled = Bundle.main.url(forResource: "sample-attempt", withExtension: "mp4") {
            data = try? Data(contentsOf: bundled)
            type = "video/mp4"
        }
        guard mine == generation else { return }
        let ext = type == "video/quicktime" ? "mov" : "mp4"
        guard let data, let preview = Self.write(data, name: "sample-\(UUID().uuidString).\(ext)") else {
            phase = .failed("The sample clip could not be loaded.", nil)
            return
        }
        phase = .taken(ClipTake(data: data, contentType: type, filename: "sample-attempt.\(ext)",
                                preview: preview, isSample: true))
    }

    /// Send the take to storage. The completion that follows confirms it.
    func upload(api: APIClient) async {
        guard let take else { return }
        generation += 1
        let mine = generation
        phase = .uploading(take, 0)
        do {
            let staged = try await api.stageClip(take.data, contentType: take.contentType,
                                                 filename: take.filename) { [weak self] fraction in
                Task { @MainActor in
                    guard let self, mine == self.generation, case .uploading(let take, _) = self.phase else { return }
                    self.phase = .uploading(take, fraction)
                }
            }
            guard mine == generation else { return }
            phase = .staged(take, staged)
        } catch {
            guard mine == generation else { return }
            // A screen that went away leaves the take in hand, to try again.
            phase = ExerciseStore.sentence(for: error).map { Phase.failed($0, take) } ?? Phase.taken(take)
        }
    }

    /// The photo the camera took when a video was wanted.
    func refusePhoto() {
        generation += 1
        phase = .failed("That was a photo. Switch the camera to Video and record a few seconds.", nil)
    }

    func remove() {
        generation += 1
        phase = .none
    }

    #if DEBUG
    /// Simulator verification: hold the two states of an upload that pass
    /// too quickly on a laptop to be looked at.
    func debugHold(uploading fraction: Double) {
        if let take { phase = .uploading(take, fraction) }
    }

    func debugHold(failure message: String) {
        phase = .failed(message, take)
    }
    #endif
}

// MARK: - Where a clip comes from

/// The ways to get a clip, as buttons: the system camera (the shared
/// `CameraCapture`), a video already in the photo library, and, on a demo
/// server, a sample. The first one this phone can do is the filled button.
struct AttemptSources: View {
    let a: ExerciseAssignment
    let clip: AttemptClip
    /// The filled button for the first source; otherwise all are quiet.
    var prominent = true
    /// Called once a take is in hand.
    var onTaken: () -> Void = {}

    @Environment(AppModel.self) private var app
    @Environment(DemoShell.self) private var shell
    @Environment(ExerciseStore.self) private var store
    @State private var showCamera = false
    @State private var pick: PhotosPickerItem?

    private var cameraFirst: Bool { CameraCapture.available }
    private var sampleOffered: Bool { shell.isDemoServer }

    var body: some View {
        VStack(spacing: 10) {
            if CameraCapture.available {
                button("Record a clip", "video.fill", filled: prominent) { showCamera = true }
            }
            if sampleOffered {
                button("Use a sample clip", "film", filled: prominent && !cameraFirst) {
                    Task {
                        await clip.useSample(for: a, store: store, api: app.api)
                        if clip.take != nil { onTaken() }
                    }
                }
            }
            PhotosPicker(selection: $pick, matching: .videos, photoLibrary: .shared()) {
                HStack(spacing: 8) {
                    Image(systemName: "photo.on.rectangle")
                    Text("Choose a video")
                }
            }
            .buttonStyle(MPButtonStyle(kind: .gray, fullWidth: true))
            .controlSize(.large)
            if sampleOffered {
                Text("The sample is for this demo: it stands in for your own recording"
                     + (CameraCapture.available ? "." : ", because this device has no camera."))
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            } else if !CameraCapture.available {
                Text("This device has no camera. Choose a video you already have.")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .disabled(clip.isWorking)
        .fullScreenCover(isPresented: $showCamera) {
            CameraCapture(onImage: { _ in clip.refusePhoto() },
                          onMovie: { url in
                              Task {
                                  await clip.use(movieAt: url)
                                  if clip.take != nil { onTaken() }
                              }
                          })
                .ignoresSafeArea()
        }
        .onChange(of: pick) { _, item in
            guard let item else { return }
            pick = nil
            Task {
                guard let movie = try? await item.loadTransferable(type: PickedMovie.self) else {
                    clip.refusePhoto()
                    return
                }
                await clip.use(movieAt: movie.url)
                try? FileManager.default.removeItem(at: movie.url)
                if clip.take != nil { onTaken() }
            }
        }
    }

    @ViewBuilder
    private func button(_ title: String, _ icon: String, filled: Bool, action: @escaping () -> Void) -> some View {
        if filled {
            PrimaryButton(title: title, icon: icon, action: action)
        } else {
            SecondaryButton(title: title, icon: icon, action: action)
        }
    }
}

/// A take as one line: its name, how far the upload has got, and a way to
/// take it back. The completion sheet's clip row.
struct AttemptChip: View {
    let clip: AttemptClip

    var body: some View {
        let failed: Bool = { if case .failed = clip.phase { return true } else { return false } }()
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: failed ? "video.slash" : "film")
                .font(.subhead).foregroundStyle(failed ? MP.riskMed : MP.brandInk)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 5) {
                Text(title).mpFont(.copyMedium).foregroundStyle(MP.ink)
                    .fixedSize(horizontal: false, vertical: true)
                switch clip.phase {
                case .preparing:
                    Text("Getting it ready…").mpFont(.label).foregroundStyle(MP.muted)
                case .uploading(_, let fraction):
                    UploadLine(fraction: fraction)
                    Text("Uploading\(MP.dot)\(Int((fraction * 100).rounded()))%")
                        .font(.figuresLabel).foregroundStyle(MP.muted)
                case .staged(let take, _):
                    Text("Uploaded\(MP.dot)\(Self.size(take.data.count))\(MP.dot)goes with your answers")
                        .mpFont(.label).foregroundStyle(MP.riskLow)
                case .failed(let message, _):
                    Text(message).mpFont(.label).foregroundStyle(MP.riskMed)
                        .fixedSize(horizontal: false, vertical: true)
                case .taken, .none:
                    EmptyView()
                }
            }
            Spacer(minLength: 4)
            if clip.phase != .preparing {
                Button { clip.remove() } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.subhead).foregroundStyle(MP.muted)
                        .frame(width: 44, height: 44)
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Remove the clip")
            }
        }
        .padding(.leading, 14).padding(.trailing, 4).padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.panel))
        .overlay(MP.controlShape.strokeBorder(MP.line, lineWidth: 1))
    }

    private var title: String {
        guard let take = clip.take else { return "Your clip" }
        return take.isSample ? "Sample clip (demo)" : "Your clip"
    }

    static func size(_ bytes: Int) -> String {
        if bytes >= 1_048_576 { return String(format: "%.1f MB", Double(bytes) / 1_048_576) }
        return "\(max(1, bytes / 1024)) KB"
    }
}

/// A thin line that fills as the bytes go.
struct UploadLine: View {
    let fraction: Double

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                MP.capsuleShape.fill(MP.track)
                MP.capsuleShape.fill(MP.brand)
                    .frame(width: max(4, proxy.size.width * min(1, max(0, fraction))))
            }
        }
        .frame(height: 5)
        .animation(.linear(duration: 0.15), value: fraction)
        .accessibilityHidden(true)
    }
}
