import CoreLocation
import CoreMotion
import Foundation
import HealthKit
import Observation

/// Records what the backend's mobility engine needs from one walk: device
/// motion at 50 Hz (total acceleration, rotation rate, the gravity estimate,
/// timestamps), barometric altitude, the phone's own pedometer count and
/// distance, and — when the walk is outdoors and the patient allowed it —
/// the GPS path length. Nothing is computed here: the phone is the sensor,
/// the server is the algorithm, so an iPhone and an Android phone yield the
/// same metrics by the same rules (backend app/engine/mobility).
@Observable
@MainActor
final class MotionCapture {
    enum State: Equatable { case idle, recording, finished }

    static let sampleRate = 50.0

    private(set) var state: State = .idle
    private(set) var elapsed: TimeInterval = 0
    private(set) var steps = 0
    private(set) var pedometerDistance: Double?
    private(set) var sampleCount = 0
    private(set) var liveTiltDegrees: Double = 0
    private(set) var unavailable: String?

    var gpsDistance: Double { location.distance }
    var gpsAccuracy: Double? { location.meanAccuracy }
    var isAvailable: Bool { motion.isDeviceMotionAvailable }

    private let motion = CMMotionManager()
    private let altimeter = CMAltimeter()
    private let pedometer = CMPedometer()
    private let location = LocationTracker()
    private(set) var startedAt: Date?
    private var firstStamp: TimeInterval?
    private var accel: [[Double]] = []
    private var gyro: [[Double]] = []
    private var gravity: [[Double]] = []
    private var stamps: [Double] = []
    private var altitude: [[Double]] = []
    private var minuteSteps: [Int] = []
    private var ticker: Task<Void, Never>?
    private var limit: TimeInterval = 0

    /// Start recording. `seconds` is the auto-stop; `outdoors` turns the GPS on.
    func start(seconds: TimeInterval, outdoors: Bool) {
        guard state != .recording else { return }
        guard motion.isDeviceMotionAvailable else {
            unavailable = "This device has no motion sensors."
            return
        }
        reset()
        limit = seconds
        startedAt = Date()
        state = .recording
        motion.deviceMotionUpdateInterval = 1.0 / Self.sampleRate
        motion.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: .main) { [weak self] data, _ in
            guard let self, let d = data, self.state == .recording else { return }
            self.append(d)
        }
        if CMAltimeter.isRelativeAltitudeAvailable() {
            altimeter.startRelativeAltitudeUpdates(to: .main) { [weak self] data, _ in
                guard let self, let d = data, let start = self.firstStamp else { return }
                let t = d.timestamp - start
                self.altitude.append([(t * 100).rounded() / 100, (d.relativeAltitude.doubleValue * 100).rounded() / 100])
            }
        }
        if CMPedometer.isStepCountingAvailable() {
            pedometer.startUpdates(from: Date()) { [weak self] data, _ in
                guard let d = data else { return }
                Task { @MainActor [weak self] in
                    guard let self, self.state == .recording else { return }
                    self.steps = d.numberOfSteps.intValue
                    self.pedometerDistance = d.distance?.doubleValue
                }
            }
        }
        if outdoors { location.start() }
        ticker = Task { [weak self] in
            var lastMinute = 0
            var stepsAtMinute = 0
            while let self, !Task.isCancelled, self.state == .recording {
                try? await Task.sleep(for: .milliseconds(250))
                guard let started = self.startedAt else { return }
                self.elapsed = Date().timeIntervalSince(started)
                let minute = Int(self.elapsed / 60)
                if minute > lastMinute {
                    self.minuteSteps.append(self.steps - stepsAtMinute)
                    stepsAtMinute = self.steps
                    lastMinute = minute
                }
                if self.elapsed >= self.limit { self.stop() }
            }
        }
    }

    private func append(_ d: CMDeviceMotion) {
        if firstStamp == nil { firstStamp = d.timestamp }
        let t = d.timestamp - (firstStamp ?? d.timestamp)
        let g = d.gravity, u = d.userAcceleration, r = d.rotationRate
        let k = 9.80665
        accel.append([r3((u.x + g.x) * k), r3((u.y + g.y) * k), r3((u.z + g.z) * k)])
        gyro.append([r3(r.x), r3(r.y), r3(r.z)])
        gravity.append([r3(g.x), r3(g.y), r3(g.z)])
        stamps.append((t * 1000).rounded() / 1000)
        sampleCount = accel.count
        // The phone's long-axis tilt from horizontal, for the range-of-motion
        // screen's live readout: atan2(-g_y, -g_z), the same rule the server uses.
        liveTiltDegrees = atan2(-g.y, -g.z) * 180 / .pi
        if sampleCount >= 36_000 { stop() }   // 12 minutes: the server's ceiling
    }

    func stop() {
        guard state == .recording else { return }
        motion.stopDeviceMotionUpdates()
        altimeter.stopRelativeAltitudeUpdates()
        pedometer.stopUpdates()
        location.stop()
        ticker?.cancel()
        ticker = nil
        if let started = startedAt { elapsed = Date().timeIntervalSince(started) }
        state = .finished
    }

    func reset() {
        if state == .recording { stop() }
        state = .idle
        elapsed = 0
        steps = 0
        pedometerDistance = nil
        sampleCount = 0
        startedAt = nil
        firstStamp = nil
        accel = []; gyro = []; gravity = []; stamps = []; altitude = []; minuteSteps = []
        location.reset()
    }

    /// The recorded window in the server's shape, or nil when too short.
    func window(context: String, pocketSide: String?) -> MotionWindowUpload? {
        guard let started = startedAt, accel.count >= 50 else { return nil }
        return MotionWindowUpload(
            startedAt: Dates.iso(started), sampleRateHz: Self.sampleRate, accel: accel, gyro: gyro,
            gravity: gravity, timestamps: stamps, altitude: altitude.isEmpty ? nil : altitude,
            gpsDistanceM: location.distance > 0 ? location.distance : nil,
            gpsAccuracyM: location.meanAccuracy, pedometerSteps: steps,
            pedometerDistanceM: pedometerDistance, pocketSide: pocketSide, context: context
        )
    }

    /// Gravity samples from the last `seconds` of the recording — the hold
    /// the range-of-motion test reads its angle from.
    func recentGravity(seconds: Double) -> [[Double]] {
        let n = min(gravity.count, Int(seconds * Self.sampleRate))
        return Array(gravity.suffix(n))
    }

    var minuteStepCounts: [Int] { minuteSteps }

    private func r3(_ v: Double) -> Double { (v * 1000).rounded() / 1000 }

    // MARK: stature

    /// The most recent height in Health, for the step-length model. Absent
    /// (never recorded, or not shared) the Measure screen asks for it once.
    static func healthHeightCm() async -> Double? {
        guard HKHealthStore.isHealthDataAvailable(),
              let type = HKObjectType.quantityType(forIdentifier: .height) else { return nil }
        let store = HKHealthStore()
        let descriptor = HKSampleQueryDescriptor(
            predicates: [.quantitySample(type: type)],
            sortDescriptors: [SortDescriptor(\.endDate, order: .reverse)], limit: 1
        )
        guard let sample = try? await descriptor.result(for: store).first else { return nil }
        let cm = sample.quantity.doubleValue(for: .meterUnit(with: .centi))
        return (100...250).contains(cm) ? cm : nil
    }
}

/// GPS path length while a walk is being recorded. Fixes worse than
/// `maxAccuracy` are skipped, and the mean accuracy of the ones used travels
/// with the distance so the server can decide whether to trust it.
final class LocationTracker: NSObject, CLLocationManagerDelegate, @unchecked Sendable {
    private let manager = CLLocationManager()
    private let lock = NSLock()
    private var last: CLLocation?
    private var total: Double = 0
    private var accuracies: [Double] = []
    private let maxAccuracy = 20.0

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = 2
        manager.activityType = .fitness
    }

    var distance: Double { lock.withLock { total } }
    var meanAccuracy: Double? {
        lock.withLock { accuracies.isEmpty ? nil : accuracies.reduce(0, +) / Double(accuracies.count) }
    }

    func start() {
        if manager.authorizationStatus == .notDetermined { manager.requestWhenInUseAuthorization() }
        manager.startUpdatingLocation()
    }

    func stop() { manager.stopUpdatingLocation() }

    func reset() {
        lock.withLock { last = nil; total = 0; accuracies = [] }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        lock.withLock {
            for fix in locations where fix.horizontalAccuracy > 0 && fix.horizontalAccuracy <= maxAccuracy {
                if let prev = last { total += fix.distance(from: prev) }
                last = fix
                accuracies.append(fix.horizontalAccuracy)
            }
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if manager.authorizationStatus == .authorizedWhenInUse || manager.authorizationStatus == .authorizedAlways {
            manager.startUpdatingLocation()
        }
    }
}
