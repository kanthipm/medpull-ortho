import Foundation
import SwiftUI
import UniformTypeIdentifiers
#if canImport(UIKit)
import UIKit
#endif

/// Photos and files on the thread, on the app's side: getting one ready to
/// send, and drawing one that arrived.

// MARK: - Getting a file ready to send

enum AttachmentPrep {
    /// Long edge, in pixels. A wound photograph is read on a laptop, not
    /// enlarged in a darkroom, and twelve megapixels of it costs a patient
    /// their data allowance for no clinical gain.
    static let maxEdge: CGFloat = 2048
    static let quality: CGFloat = 0.82

    /// What the server accepts (app/storage/blobs.ALLOWED_TYPES).
    static let acceptedFiles: [UTType] = [.pdf, .jpeg, .png, .webP, .heic]

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
    /// they are; a picked HEIC is re-encoded for the same reason.
    static func file(at url: URL) -> Ready? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        let type = UTType(filenameExtension: url.pathExtension.lowercased())
        let name = url.lastPathComponent
        if type == .heic || type == .heif {
            return photo(data, name: (name as NSString).deletingPathExtension + ".jpg")
        }
        guard let mime = type?.preferredMIMEType else { return nil }
        return Ready(data: data, contentType: mime, filename: name)
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

/// A document on a thread line. A name and a size, because that is what
/// decides whether somebody opens it now.
struct AttachmentFileView: View {
    let attachment: ChatAttachment

    var body: some View {
        HStack(spacing: 8) {
            // `brandInk`, not `brand`: a glyph set with `foregroundStyle` is
            // a foreground, and #1976D2 as a foreground is 3.74:1 on dark
            // panel. `brandInk` is 5.75:1 light / 6.78:1 dark.
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
                        // NO `.italic()`. Instrument Sans ships no italic file,
                        // so SwiftUI shears the roman — synthetic obliquing,
                        // the same defect class as synthetic bold. The
                        // distinction is carried by weight and colour instead:
                        // 12pt / 400 on `muted`, against the live filename's
                        // 14pt / 500 on `ink` two lines above, and the copy
                        // ("taken back") already names the state. `faint` is
                        // 2.59:1 on panel and carries no text.
                        Text(a.isImage ? "Photo taken back" : "File taken back")
                            .font(.label)
                            .foregroundStyle(MP.muted)
                    } else if a.isImage {
                        AttachmentImageView(attachment: a)
                    } else {
                        AttachmentFileView(attachment: a)
                    }
                }
            }
        }
    }
}
