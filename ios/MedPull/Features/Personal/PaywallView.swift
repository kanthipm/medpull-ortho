import StoreKit
import SwiftUI

/// The paywall, in three moods: the last onboarding step (the trial has just
/// started, here are the plans), a lapsed subscription covering the personal
/// screens, and the manage sheet from Profile. Prices come from StoreKit;
/// access comes from the server, which the purchase reports to.
struct PaywallView: View {
    enum Mode { case onboarding, lapsed, manage }

    let mode: Mode
    var onContinue: (() -> Void)? = nil
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var selected: String = Store.annualID
    @State private var working = false
    @State private var error: String?

    private var store: Store { app.store }
    private var state: SubscriptionState? {
        app.paywall ?? app.dashboard?.subscription ?? app.me?.subscription
    }

    private var title: String {
        switch mode {
        case .onboarding: return "Your 14-day trial\nhas started."
        case .lapsed: return "Your access\nhas ended."
        case .manage: return "MedPull Personal"
        }
    }

    private var lede: String {
        switch mode {
        case .onboarding:
            return "Everything is on for two weeks. Pick a plan now and it starts when the trial ends, or decide later."
        case .lapsed:
            return "Your readouts, plan and coach are waiting. Subscribe to pick up where you left off."
        case .manage:
            return state?.headline ?? "Your plan"
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(spacing: 14) {
                        IconTile("sparkles", family: .teal, size: 52)
                        Text(title).title(MPSize.displayS).accessibilityAddTraits(.isHeader)
                    }
                    Text(lede).mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if let state, mode != .onboarding {
                        stateCard(state)
                    }
                    features
                    plans
                    if let error { ErrorBanner(text: error) }
                    if let e = store.lastError { ErrorBanner(text: e) }
                    actions
                    PersonalGuardrail()
                    Text("Subscriptions renew automatically until cancelled in Settings › Apple ID › Subscriptions. Prices are set by the App Store for your region.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .ambientScreen()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if mode == .manage {
                    ToolbarItem(placement: .cancellationAction) {
                        if #available(iOS 26, *) {
                            Button(role: .close) { dismiss() }
                        } else {
                            Button("Done") { dismiss() }.mpFont(.copyLargeMedium)
                        }
                    }
                }
            }
            .task { await store.load() }
            .mpErrorFeedback(error)
        }
        .tint(MP.brandInk)
    }

    private func stateCard(_ state: SubscriptionState) -> some View {
        Card(tint: true) {
            HStack(spacing: 12) {
                IconTile(state.entitled ? "checkmark.seal.fill" : "clock.badge.exclamationmark",
                         family: state.entitled ? .teal : .blue)
                VStack(alignment: .leading, spacing: 2) {
                    Text(state.headline).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    if let expires = state.expiresAt {
                        Text("\(state.entitled ? "Renews" : "Ended") \(ProfileView.displayDate(expires))")
                            .mpFont(.label).mpSecondary()
                    }
                    if state.source == "apple", !state.verified {
                        Text("Test purchase (not verified with Apple).").mpFont(.label).mpSecondary()
                    }
                }
                Spacer()
            }
        }
    }

    private var features: some View {
        VStack(alignment: .leading, spacing: 14) {
            feature("gauge.with.dots.needle.67percent", .teal, "Readiness every morning",
                    "HRV, resting heart rate and sleep against your own baselines, with the reasons.")
            feature("flame.fill", .blue, "Training load that means something",
                    "Acute:chronic ratio, fitness and fatigue, monotony and strain, from your watch.")
            feature("bed.double.fill", .indigo, "Sleep need and debt",
                    "Your need, your debt, your regularity, and the one change that pays off.")
            feature("waveform", .violet, "A coach that knows your numbers",
                    "Ask why, get the actual values. A plan for the day, and a brief by text if you want it.")
        }
    }

    private func feature(_ icon: String, _ family: MP.Category, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            IconTile(icon, family: family, size: 40)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                Text(detail).mpFont(.copy).foregroundStyle(MP.body)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var plans: some View {
        if store.products.isEmpty {
            Card {
                HStack(spacing: 12) {
                    if store.loading { ProgressView().tint(MP.brand) }
                    Text(store.loading ? "Loading plans…"
                         : "Plans aren’t available on this build yet. Your trial covers everything meanwhile.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        } else {
            VStack(spacing: 10) {
                ForEach(store.products, id: \.id) { product in
                    planCard(product)
                }
            }
        }
    }

    private func planCard(_ product: Product) -> some View {
        let isSelected = selected == product.id
        let annual = product.id == Store.annualID
        return Button { selected = product.id } label: {
            HStack(spacing: 12) {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.systemGlyphs(22, weight: .regular))
                    .foregroundStyle(isSelected ? MP.ink : MP.lineStrong)
                    .contentTransition(.symbolEffect(.replace))
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text(annual ? "Yearly" : "Monthly").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        if annual, let saving = store.annualSavingPercent, saving > 0 {
                            StatusPill(text: "Save \(saving)%", tone: .low)
                        }
                    }
                    Text(annual ? "One payment a year" : "Cancel any time")
                        .mpFont(.label).foregroundStyle(MP.body)
                }
                Spacer(minLength: 8)
                VStack(alignment: .trailing, spacing: 0) {
                    Text(product.displayPrice).font(.figuresLede).foregroundStyle(MP.ink)
                    Text(annual ? "per year" : "per month").mpFont(.label).foregroundStyle(MP.muted)
                }
            }
            .padding(14)
            .glassSurface(MP.surfaceShape, solid: true)
            .overlay(MP.surfaceShape.strokeBorder(isSelected ? MP.ink : .clear, lineWidth: 1.5))
            .contentShape(MP.surfaceShape)
        }
        .buttonStyle(CardTapStyle())
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .sensoryFeedback(.selection, trigger: isSelected) { _, new in new }
    }

    @ViewBuilder private var actions: some View {
        VStack(spacing: 8) {
            if let product = store.products.first(where: { $0.id == selected }) {
                PrimaryButton(title: mode == .onboarding ? "Subscribe after the trial" : "Subscribe",
                              icon: "lock.open.fill", loading: working || store.purchasing) {
                    purchase(product)
                }
            }
            switch mode {
            case .onboarding:
                SecondaryButton(title: "Continue with the free trial", icon: "arrow.right") {
                    onContinue?()
                }
            case .lapsed:
                if let other = app.me?.otherSpace {
                    SecondaryButton(title: "Switch to \(other.label)", icon: "arrow.left.arrow.right") {
                        Task { await app.switchSpace(to: other) }
                    }
                }
            case .manage:
                SecondaryButton(title: "Manage in the App Store", icon: "arrow.up.forward.app") {
                    if let url = URL(string: "https://apps.apple.com/account/subscriptions") {
                        UIApplication.shared.open(url)
                    }
                }
            }
            Button("Restore purchases") { restore() }
                .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
                .disabled(working || store.purchasing)
        }
    }

    private func purchase(_ product: Product) {
        working = true
        error = nil
        Task {
            defer { working = false }
            if let state = await store.purchase(product, api: app.api) {
                await app.subscriptionChanged(state)
                if mode == .onboarding { onContinue?() } else if mode == .manage { dismiss() }
            }
        }
    }

    private func restore() {
        working = true
        error = nil
        Task {
            defer { working = false }
            if let state = await store.restore(api: app.api) {
                await app.subscriptionChanged(state)
                if mode == .manage { dismiss() }
            }
        }
    }
}
