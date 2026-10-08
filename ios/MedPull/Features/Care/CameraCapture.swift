import SwiftUI
import UniformTypeIdentifiers
#if canImport(UIKit)
import UIKit

/// The camera, for a photo or a short clip of the thing the care team asked
/// to see. The system picker rather than a camera of our own: it already
/// handles the flip, the flash, the preview and the retake, and a wound is
/// photographed once, not composed.
struct CameraCapture: UIViewControllerRepresentable {
    /// A still, as JPEG-able image data.
    let onImage: (Data) -> Void
    /// A clip, as the temporary file the camera wrote.
    let onMovie: (URL) -> Void
    @Environment(\.dismiss) private var dismiss

    static var available: Bool { UIImagePickerController.isSourceTypeAvailable(.camera) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.mediaTypes = [UTType.image.identifier, UTType.movie.identifier]
        // Medium quality is 480p on most phones: plenty for a clip of a knee
        // bending, and a fraction of the bytes of the camera's default.
        picker.videoQuality = .typeMedium
        picker.videoMaximumDuration = 60
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraCapture
        init(_ parent: CameraCapture) { self.parent = parent }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let url = info[.mediaURL] as? URL {
                parent.onMovie(url)
            } else if let image = (info[.editedImage] ?? info[.originalImage]) as? UIImage,
                      let data = image.jpegData(compressionQuality: 0.95) {
                parent.onImage(data)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}
#endif
