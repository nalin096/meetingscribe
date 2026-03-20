import Foundation

struct ManifestWriter {
    static func write(meetingID: String, app: String, chunks: [ChunkWriter.ChunkInfo], started: Date, ended: Date, to directory: URL) {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        let chunkDicts: [[String: Any]] = chunks.map { chunk in
            ["remote": chunk.remote, "local": chunk.local,
             "start_mach_time": chunk.startMachTime, "start_iso": chunk.startISO]
        }

        let manifest: [String: Any] = [
            "meeting_id": meetingID, "app": app, "chunks": chunkDicts,
            "started": iso.string(from: started), "ended": iso.string(from: ended),
        ]

        guard let jsonData = try? JSONSerialization.data(withJSONObject: manifest, options: .prettyPrinted) else { return }

        let tmpPath = directory.appendingPathComponent("\(meetingID).tmp")
        let finalPath = directory.appendingPathComponent("\(meetingID).json")
        try? jsonData.write(to: tmpPath)
        try? FileManager.default.moveItem(at: tmpPath, to: finalPath)
    }

    static func generateMeetingID(startDate: Date) -> String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        let suffix = String(format: "%04x", arc4random_uniform(0xFFFF))
        return "\(iso.string(from: startDate))-\(suffix)"
    }
}
