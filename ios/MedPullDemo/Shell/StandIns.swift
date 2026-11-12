import Foundation
import Observation

// `Core/AppModel.swift` is shared with the real app as it is, and it owns a
// `HealthConnector` (Apple Health through the Vital SDK) and a `Store`
// (StoreKit). The demo app links neither framework: its people are fictional
// and their readings are written by the demo's fill, so there is nothing on
// this phone to connect and nothing to buy. These two types give AppModel
// what it asks for and do nothing.

/// Apple Health, in the demo: never connected. The shared screens read a
/// persona's sources from `/api/mobile/me`, not from this phone.
@Observable
@MainActor
final class HealthConnector {
    enum State: Equatable {
        case idle, connecting, connected, unavailable
        case failed(String)
    }

    let state: State = .unavailable
    var isConnected: Bool { false }

    func restore() {}

    func connect(patientId: String, api: APIClient) async -> Bool { false }

    func disconnect() async {}

    func uploadGait(api: APIClient) async throws {}
}

/// The App Store, in the demo: no products and no purchases. No demo person
/// is ever asked to pay, so the paywall is never shown.
@Observable
@MainActor
final class Store {
    func start(api: APIClient) {}
}
