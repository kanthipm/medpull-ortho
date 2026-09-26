import Foundation
import Observation
import StoreKit

/// The App Store side of MedPull Personal, on StoreKit 2.
///
/// Two products, one subscription group. Every verified transaction —
/// a purchase here, a renewal Apple pushes through `Transaction.updates`,
/// a restore — is reported to the backend as its signed JWS, and the
/// backend decides what the account may see. The app never grants itself
/// access from a receipt: the server's `SubscriptionState` is the truth.
///
/// Locally (an Xcode run with the MedPull.storekit configuration) the
/// transactions are signed by Xcode, not Apple, so the server has to be in
/// its lenient mode to accept them; the trial covers a phone on a strict
/// server until App Store Connect is live.
@Observable
@MainActor
final class Store {
    static let monthlyID = "com.medpull.recovery.personal.monthly"
    static let annualID = "com.medpull.recovery.personal.annual"
    static let productIDs = [monthlyID, annualID]

    private(set) var products: [Product] = []
    private(set) var loading = false
    private(set) var purchasing = false
    private(set) var lastError: String?
    /// Whether an Apple entitlement is live on this device, from StoreKit's
    /// own view. Informational; the server's state gates the screens.
    private(set) var hasAppleEntitlement = false

    private var updates: Task<Void, Never>?

    var monthly: Product? { products.first { $0.id == Self.monthlyID } }
    var annual: Product? { products.first { $0.id == Self.annualID } }

    /// What an annual plan saves against twelve months, as a whole percent.
    var annualSavingPercent: Int? {
        guard let m = monthly, let a = annual else { return nil }
        let year = m.price * 12
        guard year > 0 else { return nil }
        let saving = (year - a.price) / year * 100
        return NSDecimalNumber(decimal: saving).intValue
    }

    func start(api: APIClient) {
        guard updates == nil else { return }
        updates = Task { [weak self] in
            for await result in Transaction.updates {
                guard let self else { return }
                await self.handle(result, api: api)
            }
        }
        Task { await load() }
        Task { await refreshEntitlement() }
    }

    func load() async {
        guard products.isEmpty, !loading else { return }
        loading = true
        defer { loading = false }
        do {
            products = try await Product.products(for: Self.productIDs)
                .sorted { $0.price < $1.price }
            lastError = nil
        } catch {
            lastError = "Couldn’t load the plans (\(error.localizedDescription))."
        }
    }

    /// Buy one plan and report it. Returns the server's new state, or nil
    /// when the person cancelled or the purchase is pending approval.
    func purchase(_ product: Product, api: APIClient) async -> SubscriptionState? {
        purchasing = true
        defer { purchasing = false }
        lastError = nil
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                return await handle(verification, api: api)
            case .pending:
                lastError = "The purchase is waiting for approval."
                return nil
            case .userCancelled:
                return nil
            @unknown default:
                return nil
            }
        } catch {
            lastError = error.localizedDescription
            return nil
        }
    }

    /// Restore: re-report whatever entitlements Apple says this Apple ID holds.
    func restore(api: APIClient) async -> SubscriptionState? {
        purchasing = true
        defer { purchasing = false }
        lastError = nil
        do { try await AppStore.sync() } catch { /* the sheet was dismissed */ }
        var latest: SubscriptionState?
        for await result in Transaction.currentEntitlements {
            if let state = await handle(result, api: api) { latest = state }
        }
        if latest == nil { lastError = "No active subscription found for this Apple ID." }
        return latest
    }

    private func refreshEntitlement() async {
        var found = false
        for await result in Transaction.currentEntitlements {
            if case .verified(let t) = result, Self.productIDs.contains(t.productID) { found = true }
        }
        hasAppleEntitlement = found
    }

    /// Verify locally, report the signed transaction, finish it.
    @discardableResult
    private func handle(_ result: VerificationResult<Transaction>, api: APIClient) async -> SubscriptionState? {
        switch result {
        case .unverified(_, let error):
            lastError = "That purchase couldn’t be verified (\(error.localizedDescription))."
            return nil
        case .verified(let transaction):
            guard Self.productIDs.contains(transaction.productID) else {
                await transaction.finish()
                return nil
            }
            var state: SubscriptionState?
            do {
                let environment: String
                switch transaction.environment {
                case .xcode: environment = "Xcode"
                case .sandbox: environment = "Sandbox"
                case .production: environment = "Production"
                default: environment = "Unknown"
                }
                let r = try await api.reportAppleTransaction(jws: result.jwsRepresentation,
                                                             environment: environment)
                state = r.subscription
                hasAppleEntitlement = true
            } catch {
                // Not finished: StoreKit will hand it back on the next launch
                // and the report is retried then.
                lastError = AppModel.message(for: error)
                return nil
            }
            await transaction.finish()
            return state
        }
    }
}
