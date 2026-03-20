import Foundation
import ScreenCaptureKit

struct ZoomDetector: MeetingDetector {
    let appName = "Zoom"

    func isActive(apps: [SCRunningApplication]) -> Bool {
        let zoomRunning = apps.contains { $0.bundleIdentifier == "zoom.us" }
        guard zoomRunning else { return false }

        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        task.arguments = ["-f", "CptHost"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        try? task.run()
        task.waitUntilExit()
        return task.terminationStatus == 0
    }
}
