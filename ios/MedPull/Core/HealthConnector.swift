import Foundation
import HealthKit
import Observation
import VitalCore
import VitalHealthKit

/// Apple Health, in one tap.
///
/// The old wrapper asked for each Vital resource with its own button, so a
/// patient tapped "Ask for permission" thirty times and answered thirty
/// sheets. HealthKit shows exactly one authorization sheet per `ask` call
/// however many types it carries, so this asks for everything the recovery
/// engine reads — plus Apple's walking metrics, which never pass through
/// Junction and are read here directly — in a single call. The user sees one
/// sheet with a "Turn On All" switch.
///
/// Authentication is a Vital Sign-In Token minted by our backend for this
/// patient's Junction user; the team API key never ships in the app.
@Observable
@MainActor
final class HealthConnector {
    enum State: Equatable {
        case idle, connecting, connected, unavailable
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var syncLine: String = ""
    private(set) var lastGaitUpload: String?
    private var syncTask: Task<Void, Never>?

    /// Everything the engine scores or charts, plus what a surgeon would ask
    /// about. One list, one sheet.
    static let recoveryResources: [VitalResource] = [
        .profile, .body, .activity, .sleep, .workout,
        .vitals(.heartRate), .vitals(.heartRateVariability), .vitals(.bloodOxygen),
        .vitals(.respiratoryRate), .vitals(.temperature), .vitals(.bloodPressure),
        .individual(.steps), .individual(.distance), .individual(.floorsClimbed),
        .individual(.activeEnergyBurned), .individual(.exerciseTime), .individual(.vo2Max),
        .individual(.weight),
        .heartRateRecoveryOneMinute, .standHour,
    ]

    /// HealthKit-only walking metrics -> the backend's MetricType names.
    static let gaitTypes: [(HKQuantityTypeIdentifier, String, HKUnit, Double)] = [
        (.walkingSpeed, "walking_speed", HKUnit.meter().unitDivided(by: .second()), 1),
        (.walkingStepLength, "step_length", .meter(), 1),
        (.walkingDoubleSupportPercentage, "double_support_pct", .percent(), 100),
        (.walkingAsymmetryPercentage, "walking_asymmetry_pct", .percent(), 100),
        (.appleWalkingSteadiness, "walking_steadiness", .percent(), 100),
        (.stairAscentSpeed, "stair_speed_up", HKUnit.meter().unitDivided(by: .second()), 1),
        (.stairDescentSpeed, "stair_speed_down", HKUnit.meter().unitDivided(by: .second()), 1),
        (.sixMinuteWalkTestDistance, "six_min_walk", .meter(), 1),
        // The athlete fitness signals (the personal tier's Cardio fitness
        // panel): Apple's VO2 max estimate in mL/(kg·min), and the one-minute
        // heart-rate recovery after a workout, in bpm.
        (.vo2Max, "vo2_max",
         HKUnit.literUnit(with: .milli).unitDivided(by: HKUnit.gramUnit(with: .kilo).unitMultiplied(by: .minute())), 1),
        (.heartRateRecoveryOneMinute, "hr_recovery_1min", HKUnit.count().unitDivided(by: .minute()), 1),
    ]

    private let store = HKHealthStore()

    var isConnected: Bool { state == .connected }

    /// On launch: the SDK restored itself from secure storage; reflect that.
    func restore() {
        if VitalClient.status.contains(.signedIn) {
            state = .connected
            observeSync()
        }
    }

    func connect(patientId: String, api: APIClient) async -> Bool {
        guard HKHealthStore.isHealthDataAvailable() else {
            state = .unavailable
            return false
        }
        state = .connecting
        do {
            // The identity carries the Junction user, not just the patient:
            // the SDK skips re-authentication when the external id is
            // unchanged, so a chart whose Junction account was replaced (a
            // record merge, a disconnect and relink) would go on pushing to
            // the retired account, where our webhook has no mapping and the
            // data is dropped. Fetching the session first is what lets the
            // id name the account the backend is actually reading.
            let session = try await api.appleSession()
            try await VitalClient.identifyExternalUser(
                "medpull:\(patientId):\(session.userId)"
            ) { _ in .signInToken(rawToken: session.signInToken) }
            await VitalHealthKitClient.configure(
                .init(
                    backgroundDeliveryEnabled: true,
                    numberOfDaysToBackFill: 90,
                    logsEnabled: false,
                    connectionPolicy: .autoConnect
                )
            )
            let extra: [HKObjectType] = Self.gaitTypes.compactMap {
                HKObjectType.quantityType(forIdentifier: $0.0)
            }
            let outcome = await VitalHealthKitClient.shared.ask(
                readPermissions: Self.recoveryResources,
                writePermissions: [],
                extraReadPermissions: extra
            )
            switch outcome {
            case .success:
                state = .connected
                observeSync()
                VitalHealthKitClient.shared.syncData()
                Task { try? await uploadGait(api: api) }
                return true
            case .healthKitNotAvailable:
                state = .unavailable
                return false
            case .failure(let message):
                state = .failed(message)
                return false
            }
        } catch {
            state = .failed(error.localizedDescription)
            return false
        }
    }

    func syncNow() {
        guard isConnected else { return }
        VitalHealthKitClient.shared.syncData()
    }

    func disconnect() async {
        syncTask?.cancel()
        syncTask = nil
        if VitalClient.status.contains(.signedIn) {
            await VitalClient.shared.signOut()
        }
        state = .idle
        syncLine = ""
    }

    private func observeSync() {
        syncTask?.cancel()
        let publisher = VitalHealthKitClient.shared.status
        syncTask = Task { [weak self] in
            for await status in publisher.values {
                guard let self, !Task.isCancelled else { return }
                switch status {
                case .syncing(let resource):
                    self.syncLine = "Syncing \(resource.logDescription)…"
                case .successSyncing(let resource, _):
                    self.syncLine = "Synced \(resource.logDescription)"
                case .nothingToSync(let resource):
                    self.syncLine = "Up to date: \(resource.logDescription)"
                case .failedSyncing(let resource, _):
                    self.syncLine = "Couldn't sync \(resource.logDescription)"
                case .syncingCompleted:
                    self.syncLine = "Everything is up to date"
                }
            }
        }
    }

    /// Daily averages of Apple's walking metrics for the last two weeks,
    /// posted to the backend, which runs them through the same ingest path
    /// as every wearable row. Returns the number of rows the server took.
    @discardableResult
    func uploadGait(api: APIClient, days: Int = 14) async throws -> Int {
        guard HKHealthStore.isHealthDataAvailable() else { return 0 }
        let calendar = Calendar.current
        let end = calendar.startOfDay(for: Date()).addingTimeInterval(86_400)
        let start = calendar.date(byAdding: .day, value: -days, to: end)!
        var points: [GaitPoint] = []
        for (identifier, metric, unit, scale) in Self.gaitTypes {
            guard let type = HKObjectType.quantityType(forIdentifier: identifier) else { continue }
            let predicate = HKQuery.predicateForSamples(withStart: start, end: end)
            let descriptor = HKStatisticsCollectionQueryDescriptor(
                predicate: HKSamplePredicate.quantitySample(type: type, predicate: predicate),
                options: .discreteAverage,
                anchorDate: calendar.startOfDay(for: start),
                intervalComponents: DateComponents(day: 1)
            )
            let collection: HKStatisticsCollection
            do {
                collection = try await descriptor.result(for: store)
            } catch {
                continue  // not authorized for this one type, or no store access
            }
            collection.enumerateStatistics(from: start, to: end) { stats, _ in
                guard let avg = stats.averageQuantity() else { return }
                points.append(GaitPoint(
                    metricType: metric,
                    date: Dates.dayString(stats.startDate),
                    value: avg.doubleValue(for: unit) * scale
                ))
            }
        }
        guard !points.isEmpty else {
            lastGaitUpload = "No walking data on this phone yet"
            return 0
        }
        let result = try await api.uploadGait(GaitUpload(points: points, deviceModel: UIKitDeviceName.name))
        let taken = result.ingested + result.updated
        lastGaitUpload = "Sent \(points.count) walking values\(MP.dot)\(taken) new or updated"
        return taken
    }
}
