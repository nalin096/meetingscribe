import Foundation
import ScreenCaptureKit

class DetectionManager {
    let onMeetingDetected: (String) -> Void
    let onMeetingEnded: () -> Void

    private var timer: Timer?
    private var isRecording = false
    private var activeDetector: (any MeetingDetector)?
    private let config: AppConfig

    private lazy var detectors: [any MeetingDetector] = [
        ZoomDetector(),
        MeetDetector(windowMatch: config.chromeWindowMatch),
        SlackDetector(minDurationSeconds: config.slackMinDurationSeconds),
    ]

    init(config: AppConfig = (try? .load()) ?? .defaultFallback, onMeetingDetected: @escaping (String) -> Void, onMeetingEnded: @escaping () -> Void) {
        self.config = config
        self.onMeetingDetected = onMeetingDetected
        self.onMeetingEnded = onMeetingEnded
    }

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: TimeInterval(config.pollIntervalSeconds), repeats: true) { [weak self] _ in
            Task { await self?.poll() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    private var sckPermissionDenied = false

    private func poll() async {
        // If SCK permission was denied, use CGWindowList-only detection (no prompt spam)
        if sckPermissionDenied {
            pollWithoutSCK()
            return
        }

        do {
            let content = try await SCShareableContent.current
            let runningApps = content.applications

            if isRecording {
                if let detector = activeDetector, !detector.isActive(apps: runningApps) {
                    isRecording = false
                    activeDetector = nil
                    Log.debug("Meeting ended")
                    await MainActor.run { onMeetingEnded() }
                }
                return
            }

            for detector in detectors {
                if detector.isActive(apps: runningApps) {
                    isRecording = true
                    activeDetector = detector
                    Log.debug("Meeting detected: \(detector.appName)")
                    await MainActor.run { onMeetingDetected(detector.appName) }
                    return
                }
            }
        } catch {
            Log.debug("SCShareableContent FAILED (switching to CGWindowList mode): \(error)")
            sckPermissionDenied = true
        }
    }

    /// Fallback detection using only CGWindowList — no SCK permission needed
    private func pollWithoutSCK() {
        if isRecording {
            // Check if meeting window is still present
            if let detector = activeDetector, !detector.isActive(apps: []) {
                isRecording = false
                activeDetector = nil
                Log.debug("Meeting ended (CGWindowList mode)")
                Task { await MainActor.run { onMeetingEnded() } }
            }
            return
        }

        for detector in detectors {
            if detector.isActive(apps: []) {
                isRecording = true
                activeDetector = detector
                Log.debug("Meeting detected (CGWindowList mode): \(detector.appName)")
                Task { await MainActor.run { onMeetingDetected(detector.appName) } }
                return
            }
        }
    }
}

protocol MeetingDetector {
    var appName: String { get }
    func isActive(apps: [SCRunningApplication]) -> Bool
}
