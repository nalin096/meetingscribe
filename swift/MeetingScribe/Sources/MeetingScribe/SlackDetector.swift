import Foundation
import ScreenCaptureKit

class SlackDetector: MeetingDetector {
    let appName = "Slack Huddle"
    let minDurationSeconds: Int
    private var audioStartTime: Date?

    init(minDurationSeconds: Int) {
        self.minDurationSeconds = minDurationSeconds
    }

    func isActive(apps: [SCRunningApplication]) -> Bool {
        if !apps.isEmpty {
            let slackRunning = apps.contains { $0.bundleIdentifier == "com.tinyspeck.slackmacgap" }
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
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        task.arguments = ["-f", "Slack Helper.*audio"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        try? task.run()
        task.waitUntilExit()
        return task.terminationStatus == 0
    }
}
