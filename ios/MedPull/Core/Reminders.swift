import Foundation
import Observation
import UserNotifications

/// A local morning reminder. No server, no push certificate: the phone
/// itself says "your readiness is ready" at the hour the person chose, and
/// opening the app does the rest. Off until they turn it on in Profile.
@Observable
@MainActor
final class Reminders {
    private static let key = "morning_reminder_hour"
    private static let identifier = "medpull.morning"

    /// The hour (0–23) the reminder fires, or nil when off.
    private(set) var hour: Int? = {
        let stored = UserDefaults.standard.object(forKey: Reminders.key) as? Int
        return stored
    }()
    private(set) var denied = false

    var isOn: Bool { hour != nil }

    /// Turn on at `hour`, asking permission the first time. Returns false
    /// when the permission was refused.
    @discardableResult
    func enable(hour: Int) async -> Bool {
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        guard granted else {
            denied = true
            return false
        }
        denied = false
        let content = UNMutableNotificationContent()
        content.title = "Your readiness is in"
        content.body = "Last night is scored. Open MedPull for today’s verdict and plan."
        content.sound = .default
        var components = DateComponents()
        components.hour = hour
        components.minute = 0
        let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
        let request = UNNotificationRequest(identifier: Self.identifier, content: content, trigger: trigger)
        center.removePendingNotificationRequests(withIdentifiers: [Self.identifier])
        try? await center.add(request)
        self.hour = hour
        UserDefaults.standard.set(hour, forKey: Self.key)
        return true
    }

    func disable() {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [Self.identifier])
        hour = nil
        UserDefaults.standard.removeObject(forKey: Self.key)
    }
}
