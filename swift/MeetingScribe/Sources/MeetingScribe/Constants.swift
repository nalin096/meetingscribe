import Foundation

enum Constants {
    static let meetingScribeDir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".meetingscribe")
    static let recordingsDir = meetingScribeDir.appendingPathComponent("recordings")
    static let configPath = meetingScribeDir.appendingPathComponent("config.toml")
    static let pollInterval: TimeInterval = 3.0

    static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    enum BundleID {
        static let zoom = "zoom.us"
        static let chrome = "com.google.Chrome"
        static let slack = "com.tinyspeck.slackmacgap"
    }
}
