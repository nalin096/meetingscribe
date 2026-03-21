import Foundation

enum Log {
    private static let logFile = Constants.meetingScribeDir.appendingPathComponent("debug.log")
    private static let queue = DispatchQueue(label: "com.meetingscribe.logger")
    private static let formatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    static func debug(_ message: String, prefix: String = "") {
        let tag = prefix.isEmpty ? "" : "\(prefix) "
        let line = "[\(tag)\(formatter.string(from: Date()))] \(message)\n"
        queue.async {
            if let handle = try? FileHandle(forWritingTo: logFile) {
                handle.seekToEndOfFile()
                handle.write(line.data(using: .utf8)!)
                try? handle.close()
            } else {
                try? line.write(to: logFile, atomically: true, encoding: .utf8)
            }
        }
    }
}
