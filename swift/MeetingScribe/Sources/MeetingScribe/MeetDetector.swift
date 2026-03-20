import Foundation
import ScreenCaptureKit
import CoreGraphics

struct MeetDetector: MeetingDetector {
    let appName = "Google Meet"
    let windowMatch: String

    func isActive(apps: [SCRunningApplication]) -> Bool {
        let chromeRunning = apps.contains { $0.bundleIdentifier == "com.google.Chrome" }
        guard chromeRunning else { return false }

        guard let windowList = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] else {
            return false
        }

        let patterns = windowMatch.split(separator: "|").map(String.init)
        for window in windowList {
            guard let owner = window[kCGWindowOwnerName as String] as? String,
                  owner == "Google Chrome",
                  let title = window[kCGWindowName as String] as? String else {
                continue
            }
            for pattern in patterns {
                if title.contains(pattern) {
                    return true
                }
            }
        }
        return false
    }
}
