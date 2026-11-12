import Foundation
import Security

/// Where the demo app keeps its session token: the keychain when there is
/// one, and UserDefaults as well.
///
/// This replaces `Core/Keychain.swift` in the demo target (same four calls,
/// which is all `AppModel` uses). The real app must not put a patient's
/// token in UserDefaults. The demo's tokens belong to fictional people, and
/// an unsigned simulator build has no keychain at all
/// (errSecMissingEntitlement), so without the second copy the chosen person
/// would be forgotten on every launch there.
enum Keychain {
    private static let service = "com.medpull.demo"
    private static let defaultsPrefix = "demo_session."

    static func set(_ value: String, for key: String) {
        UserDefaults.standard.set(value, forKey: defaultsPrefix + key)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
        var insert = query
        insert[kSecValueData as String] = Data(value.utf8)
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(insert as CFDictionary, nil)
    }

    static func get(_ key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        if SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
           let data = item as? Data, let value = String(data: data, encoding: .utf8) {
            return value
        }
        return UserDefaults.standard.string(forKey: defaultsPrefix + key)
    }

    static func delete(_ key: String) {
        UserDefaults.standard.removeObject(forKey: defaultsPrefix + key)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
    }

    /// Every token this app stored, in both places.
    static func deleteAll() {
        let defaults = UserDefaults.standard
        for key in defaults.dictionaryRepresentation().keys where key.hasPrefix(defaultsPrefix) {
            defaults.removeObject(forKey: key)
        }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
