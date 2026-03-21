import Foundation
import ScreenCaptureKit
import CoreGraphics

class SlackDetector: MeetingDetector {
    let appName = "Slack Huddle"
    let minDurationSeconds: Int
    private var audioStartTime: Date?

    init(minDurationSeconds: Int) {
        self.minDurationSeconds = minDurationSeconds
    }

    func isActive(apps: [SCRunningApplication]) -> Bool {
        if !apps.isEmpty {
            let slackRunning = apps.contains { $0.bundleIdentifier == Constants.BundleID.slack }
            guard slackRunning else {
                audioStartTime = nil
                return false
            }
        }

        let hasAudio = checkSlackAudio()
        if hasAudio {
            if audioStartTime == nil { audioStartTime = Date() }
            return Date().timeIntervalSince(audioStartTime!) >= Double(minDurationSeconds)
        } else {
            audioStartTime = nil
            return false
        }
    }

    private func checkSlackAudio() -> Bool {
        // Require both a Slack huddle/call window AND a WebRTC-related process
        return hasSlackCallWindow() && hasSlackCallProcess()
    }

    private func hasSlackCallWindow() -> Bool {
        guard let windowList = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] else {
            return false
        }
        for window in windowList {
            guard let owner = window[kCGWindowOwnerName as String] as? String,
                  owner == "Slack",
                  let title = window[kCGWindowName as String] as? String else { continue }
            let lower = title.lowercased()
            if lower.contains("huddle") || lower.contains("call") {
                return true
            }
        }
        return false
    }

    private func hasSlackCallProcess() -> Bool {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        task.arguments = ["-f", "Slack.*webrtc|Slack.*huddle|Slack.*call"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        try? task.run()
        task.waitUntilExit()
        return task.terminationStatus == 0
    }
}
