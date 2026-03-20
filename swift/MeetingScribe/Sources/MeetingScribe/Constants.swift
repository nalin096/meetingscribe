import Foundation

enum Constants {
    static let meetingScribeDir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".meetingscribe")
    static let recordingsDir = meetingScribeDir.appendingPathComponent("recordings")
    static let configPath = meetingScribeDir.appendingPathComponent("config.toml")
    static let pollInterval: TimeInterval = 3.0
}
