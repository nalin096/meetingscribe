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

    private func log(_ message: String) {
        let logFile = Constants.meetingScribeDir.appendingPathComponent("debug.log")
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let line = "[\(timestamp)] \(message)\n"
        if let handle = try? FileHandle(forWritingTo: logFile) {
            handle.seekToEndOfFile()
            handle.write(line.data(using: .utf8)!)
            handle.closeFile()
        } else {
            try? line.write(to: logFile, atomically: true, encoding: .utf8)
        }
    }

    private func poll() async {
        do {
            let content = try await SCShareableContent.current
            let runningApps = content.applications

            if isRecording {
                if let detector = activeDetector, !detector.isActive(apps: runningApps) {
                    isRecording = false
                    activeDetector = nil
                    log("Meeting ended")
                    await MainActor.run { onMeetingEnded() }
                }
                return
            }

            for detector in detectors {
                if detector.isActive(apps: runningApps) {
                    isRecording = true
                    activeDetector = detector
                    log("Meeting detected: \(detector.appName)")
                    await MainActor.run { onMeetingDetected(detector.appName) }
                    return
                }
            }
        } catch {
            log("SCShareableContent FAILED: \(error)")
            // Update status message on main thread
            await MainActor.run {
                // Fallback: try detection without SCK
            }
        }
    }
}

protocol MeetingDetector {
    var appName: String { get }
    func isActive(apps: [SCRunningApplication]) -> Bool
}
