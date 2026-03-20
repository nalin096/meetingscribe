import Foundation

struct CrashRecovery {
    struct RecordingLock: Codable {
        let meetingID: String
        let app: String
        let started: Date
    }

    static let lockFilename = ".recording"

    static func writeLock(meetingID: String, app: String, started: Date, in directory: URL) {
        let lock = RecordingLock(meetingID: meetingID, app: app, started: started)
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(lock) else { return }
        try? data.write(to: directory.appendingPathComponent(lockFilename))
    }

    static func removeLock(in directory: URL) {
        try? FileManager.default.removeItem(at: directory.appendingPathComponent(lockFilename))
    }

    static func recoverIfNeeded(in directory: URL) {
        let lockPath = directory.appendingPathComponent(lockFilename)
        guard FileManager.default.fileExists(atPath: lockPath.path) else { return }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        guard let data = try? Data(contentsOf: lockPath),
              let lock = try? decoder.decode(RecordingLock.self, from: data) else {
            try? FileManager.default.removeItem(at: lockPath)
            return
        }

        let fm = FileManager.default
        let contents = (try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
        let chunks = contents.filter { $0.pathExtension == "wav" }

        if chunks.isEmpty {
            try? fm.removeItem(at: lockPath)
            return
        }

        let chunkPairs = buildChunkPairs(from: chunks)
        ManifestWriter.write(meetingID: lock.meetingID, app: lock.app, chunks: chunkPairs, started: lock.started, ended: Date(), to: directory)
        try? fm.removeItem(at: lockPath)
    }

    private static func buildChunkPairs(from wavFiles: [URL]) -> [ChunkWriter.ChunkInfo] {
        let remotes = wavFiles.filter { $0.lastPathComponent.contains("_remote") }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        let locals = wavFiles.filter { $0.lastPathComponent.contains("_local") }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        return zip(remotes, locals).map { remote, local in
            ChunkWriter.ChunkInfo(remote: remote.lastPathComponent, local: local.lastPathComponent, startMachTime: 0, startISO: "")
        }
    }
}
