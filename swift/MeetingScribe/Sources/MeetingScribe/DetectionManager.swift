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

    init(config: AppConfig = (try? .load()) ?? AppConfig(
        apps: [], chromeWindowMatch: "Meet -|meet.google.com", slackMinDurationSeconds: 30,
        pollIntervalSeconds: 3, sampleRate: 16000, channels: 1,
        bitDepth: 16, chunkDurationSeconds: 300, chunkOverlapSeconds: 1
    ), onMeetingDetected: @escaping (String) -> Void, onMeetingEnded: @escaping () -> Void) {
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

    private func poll() async {
        guard let content = try? await SCShareableContent.current else { return }
        let runningApps = content.applications

        if isRecording {
            if let detector = activeDetector, !detector.isActive(apps: runningApps) {
                isRecording = false
                activeDetector = nil
                await MainActor.run { onMeetingEnded() }
            }
            return
        }

        for detector in detectors {
            if detector.isActive(apps: runningApps) {
                isRecording = true
                activeDetector = detector
                await MainActor.run { onMeetingDetected(detector.appName) }
                return
            }
        }
    }
}

protocol MeetingDetector {
    var appName: String { get }
    func isActive(apps: [SCRunningApplication]) -> Bool
}
