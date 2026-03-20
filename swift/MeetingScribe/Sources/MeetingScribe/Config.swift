import Foundation
import TOMLKit

struct AppConfig {
    let apps: [String]
    let chromeWindowMatch: String
    let slackMinDurationSeconds: Int
    let pollIntervalSeconds: Int
    let sampleRate: Int
    let channels: Int
    let bitDepth: Int
    let chunkDurationSeconds: Int
    let chunkOverlapSeconds: Int

    static func load(from path: URL = Constants.configPath) throws -> AppConfig {
        let data = try String(contentsOf: path, encoding: .utf8)
        let table = try TOMLTable(string: data)

        let detection = table["detection"] as? TOMLTable ?? TOMLTable()
        let audio = table["audio"] as? TOMLTable ?? TOMLTable()

        return AppConfig(
            apps: (detection["apps"] as? TOMLArray)?.compactMap { ($0 as? String) } ?? [],
            chromeWindowMatch: (detection["chrome_window_match"] as? String) ?? "Meet -|meet.google.com",
            slackMinDurationSeconds: (detection["slack_min_duration_seconds"] as? Int) ?? 30,
            pollIntervalSeconds: (detection["poll_interval_seconds"] as? Int) ?? 3,
            sampleRate: (audio["sample_rate"] as? Int) ?? 16000,
            channels: (audio["channels"] as? Int) ?? 1,
            bitDepth: (audio["bit_depth"] as? Int) ?? 16,
            chunkDurationSeconds: (audio["chunk_duration_seconds"] as? Int) ?? 300,
            chunkOverlapSeconds: (audio["chunk_overlap_seconds"] as? Int) ?? 1
        )
    }
}
