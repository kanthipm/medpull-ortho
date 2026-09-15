import UIKit

enum UIKitDeviceName {
    static var name: String {
        "\(UIDevice.current.model) · iOS \(UIDevice.current.systemVersion)"
    }
}
