import SwiftUI
import ScreenCaptureKit

@main
struct MeetingScribeApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(state: appState)
        } label: {
            Image(systemName: appState.isRecording ? "record.circle.fill" : "record.circle")
                .symbolRenderingMode(.palette)
                .foregroundStyle(appState.isRecording ? .red : .gray)
        }
    }
}

@MainActor
class AppState: ObservableObject {
    @Published var isRecording = false
    @Published var recordingApp: String = ""
    @Published var recordingDuration: TimeInterval = 0
    @Published var statusMessage: String = "Idle — watching for meetings"
    @Published var detectedAlternativeApp: String? = nil

    private var detectionManager: DetectionManager?
    private var systemEvents: SystemEvents?
    private var audioCapture: AudioCapture?
    private var timer: Timer?
    private var meetingID: String = ""
    private var meetingStartDate: Date = Date()

    init() {
        CrashRecovery.recoverIfNeeded(in: Constants.recordingsDir)
        // Start monitoring immediately on init — don't wait for onAppear
        startMonitoring()
    }

    func startMonitoring() {
        let config = (try? AppConfig.load()) ?? AppConfig(
            apps: [], chromeWindowMatch: "Meet -|meet.google.com", slackMinDurationSeconds: 30,
            pollIntervalSeconds: 3, sampleRate: 16000, channels: 1,
            bitDepth: 16, chunkDurationSeconds: 300, chunkOverlapSeconds: 1
        )

        systemEvents = SystemEvents()
        systemEvents?.onSleep = { [weak self] in
            Task { @MainActor in
                if self?.isRecording == true {
                    self?.stopRecording()
                }
            }
        }
        systemEvents?.onAudioDeviceChange = { [weak self] in
            Task { @MainActor in
                if self?.isRecording == true {
                    self?.statusMessage = "Audio device changed — still recording"
                }
            }
        }

        detectionManager = DetectionManager(
            config: config,
            onMeetingDetected: { [weak self] app in
                self?.handleMeetingDetected(app: app, config: config)
            },
            onMeetingEnded: { [weak self] in
                self?.handleMeetingEnded()
            }
        )
        detectionManager?.start()
        statusMessage = "Watching for meetings..."
    }

    /// Map detector app names to bundle identifiers for audio capture
    private static let appToBundleID: [String: String] = [
        "Google Meet": "com.google.Chrome",
        "Zoom": "zoom.us",
        "Slack Huddle": "com.tinyspeck.slackmacgap",
    ]

    private func handleMeetingDetected(app: String, config: AppConfig) {
        if isRecording {
            detectedAlternativeApp = app
            return
        }

        let id = ManifestWriter.generateMeetingID(startDate: Date())
        let started = Date()
        meetingID = id
        meetingStartDate = started

        CrashRecovery.writeLock(meetingID: id, app: app, started: started, in: Constants.recordingsDir)

        audioCapture = AudioCapture(config: config)

        let bundleID = AppState.appToBundleID[app] ?? app

        Task {
            do {
                let content = try await SCShareableContent.current
                if let scApp = content.applications.first(where: { $0.bundleIdentifier == bundleID }) {
                    try await audioCapture?.start(for: scApp, content: content)
                } else {
                    debugLog("App '\(bundleID)' not found in SCShareableContent — no audio capture")
                }
            } catch {
                debugLog("Audio capture failed: \(error)")
            }
        }

        startRecording(app: app)
    }

    private func debugLog(_ message: String) {
        let logFile = Constants.meetingScribeDir.appendingPathComponent("debug.log")
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let line = "[\(timestamp)] \(message)\n"
        if let handle = try? FileHandle(forWritingTo: logFile) {
            handle.seekToEndOfFile()
            handle.write(line.data(using: .utf8)!)
            handle.closeFile()
        } else {
            try? line.write(to: logFile, atomically: true, encoding: .utf8)
        }
    }

    private func handleMeetingEnded() {
        let chunks = audioCapture?.stop() ?? []
        audioCapture = nil

        let id = meetingID
        let started = meetingStartDate
        let app = recordingApp
        let ended = Date()

        ManifestWriter.write(meetingID: id, app: app, chunks: chunks, started: started, ended: ended, to: Constants.recordingsDir)
        CrashRecovery.removeLock(in: Constants.recordingsDir)

        stopRecording()
        detectedAlternativeApp = nil
    }

    func startRecording(app: String) {
        isRecording = true
        recordingApp = app
        recordingDuration = 0
        statusMessage = "Recording \(app)..."
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.recordingDuration += 1
        }
    }

    func stopRecording() {
        if isRecording && audioCapture != nil {
            handleMeetingEnded()
            return
        }
        isRecording = false
        timer?.invalidate()
        timer = nil
        statusMessage = "Idle — watching for meetings"
    }

    func discardRecording() {
        let chunks = audioCapture?.stop() ?? []
        audioCapture = nil

        // Delete chunk WAV files
        for chunk in chunks {
            try? FileManager.default.removeItem(at: Constants.recordingsDir.appendingPathComponent(chunk.remote))
            try? FileManager.default.removeItem(at: Constants.recordingsDir.appendingPathComponent(chunk.local))
        }

        CrashRecovery.removeLock(in: Constants.recordingsDir)

        isRecording = false
        timer?.invalidate()
        timer = nil
        detectedAlternativeApp = nil
        statusMessage = "Idle — watching for meetings"
    }

    func switchRecording() {
        guard let altApp = detectedAlternativeApp else { return }

        // Stop current, start new for altApp
        discardRecording()

        let config = (try? AppConfig.load()) ?? AppConfig(
            apps: [], chromeWindowMatch: "Meet -|meet.google.com", slackMinDurationSeconds: 30,
            pollIntervalSeconds: 3, sampleRate: 16000, channels: 1,
            bitDepth: 16, chunkDurationSeconds: 300, chunkOverlapSeconds: 1
        )
        handleMeetingDetected(app: altApp, config: config)
    }
}
