import AVFoundation
import ScreenCaptureKit
import Foundation

class AudioCapture {
    private var scStream: SCStream?
    private var audioEngine: AVAudioEngine?
    private var chunkWriter: ChunkWriter?
    private let config: AppConfig

    init(config: AppConfig) {
        self.config = config
    }

    func start(for app: SCRunningApplication, content: SCShareableContent) async throws {
        chunkWriter = ChunkWriter(
            outputDir: Constants.recordingsDir,
            sampleRate: config.sampleRate,
            chunkDuration: config.chunkDurationSeconds,
            overlapSeconds: config.chunkOverlapSeconds
        )
        chunkWriter?.start()

        // Setup SCStream for remote audio
        do {
            let appWindows = content.windows.filter { $0.owningApplication?.bundleIdentifier == app.bundleIdentifier }
            guard let display = content.displays.first else {
                log("No display found — skipping remote audio capture")
                throw CaptureError.noDisplay
            }

            guard !appWindows.isEmpty else {
                log("No windows found for \(app.bundleIdentifier) — skipping remote capture")
                throw CaptureError.appNotFound
            }

            let filter = SCContentFilter(display: display, including: appWindows)
            let streamConfig = SCStreamConfiguration()
            streamConfig.capturesAudio = true
            streamConfig.sampleRate = config.sampleRate
            streamConfig.channelCount = config.channels

            let delegate = AudioStreamDelegate(chunkWriter: chunkWriter!)
            scStream = SCStream(filter: filter, configuration: streamConfig, delegate: nil)
            try scStream?.addStreamOutput(delegate, type: .audio, sampleHandlerQueue: .global(qos: .userInitiated))
            try await scStream?.startCapture()
            log("SCStream remote capture started")
        } catch {
            log("SCStream setup failed (continuing with mic only): \(error)")
            // Don't rethrow — still capture local mic
        }

        // Setup AVAudioEngine for local mic
        do {
            audioEngine = AVAudioEngine()
            let inputNode = audioEngine!.inputNode
            let hwFormat = inputNode.inputFormat(forBus: 0)
            log("Mic hardware format: \(hwFormat.sampleRate)Hz, \(hwFormat.channelCount)ch, \(hwFormat.commonFormat.rawValue)")

            // Use a standard recording format — 48kHz mono Float32
            let recordFormat = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 1)!
            chunkWriter?.localSampleRate = 48000
            log("Recording format: \(recordFormat.sampleRate)Hz, \(recordFormat.channelCount)ch")

            // Pass nil as format to get the native hardware format in the tap,
            // then convert to our recording format
            inputNode.installTap(onBus: 0, bufferSize: 4096, format: recordFormat) { [weak self] buffer, time in
                let machTime = mach_absolute_time()
                self?.chunkWriter?.writeLocal(buffer: buffer, machTime: machTime)
            }

            try audioEngine?.start()
            log("AVAudioEngine mic capture started")
        } catch {
            log("AVAudioEngine failed: \(error)")
        }
    }

    func stop() -> [ChunkWriter.ChunkInfo] {
        if let stream = scStream {
            stream.stopCapture { _ in }
        }
        scStream = nil

        if audioEngine?.isRunning == true {
            audioEngine?.inputNode.removeTap(onBus: 0)
            audioEngine?.stop()
        }
        audioEngine = nil

        return chunkWriter?.finalize() ?? []
    }

    private func log(_ message: String) {
        let logFile = Constants.meetingScribeDir.appendingPathComponent("debug.log")
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let line = "[AUDIO \(timestamp)] \(message)\n"
        if let handle = try? FileHandle(forWritingTo: logFile) {
            handle.seekToEndOfFile()
            handle.write(line.data(using: .utf8)!)
            handle.closeFile()
        } else {
            try? line.write(to: logFile, atomically: true, encoding: .utf8)
        }
    }

    enum CaptureError: Error {
        case appNotFound
        case noDisplay
    }
}

class AudioStreamDelegate: NSObject, SCStreamOutput {
    let chunkWriter: ChunkWriter

    init(chunkWriter: ChunkWriter) {
        self.chunkWriter = chunkWriter
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }
        let machTime = mach_absolute_time()
        chunkWriter.writeRemote(sampleBuffer: sampleBuffer, machTime: machTime)
    }
}
