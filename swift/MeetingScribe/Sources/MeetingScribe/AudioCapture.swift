import AVFoundation
import ScreenCaptureKit
import Foundation

class AudioCapture {
    private var scStream: SCStream?
    private var audioEngine: AVAudioEngine?
    private var chunkWriter: ChunkWriter?
    private let config: AppConfig
    private var scAudioDelegate: AudioStreamDelegate?

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
                Log.debug("No display found — skipping remote audio capture", prefix: "AUDIO")
                throw CaptureError.noDisplay
            }

            guard !appWindows.isEmpty else {
                Log.debug("No windows found for \(app.bundleIdentifier) — skipping remote capture", prefix: "AUDIO")
                throw CaptureError.appNotFound
            }

            let filter = SCContentFilter(display: display, including: appWindows)
            let streamConfig = SCStreamConfiguration()
            streamConfig.capturesAudio = true
            streamConfig.sampleRate = 48_000
            streamConfig.channelCount = 2

            let delegate = AudioStreamDelegate(chunkWriter: chunkWriter!)
            self.scAudioDelegate = delegate
            scStream = SCStream(filter: filter, configuration: streamConfig, delegate: nil)
            try scStream?.addStreamOutput(delegate, type: .audio, sampleHandlerQueue: DispatchQueue(label: "meetingscribe.sc.audio"))
            try await scStream?.startCapture()
            Log.debug("SCStream remote capture started", prefix: "AUDIO")
        } catch {
            Log.debug("SCStream setup failed (continuing with mic only): \(error)", prefix: "AUDIO")
            // Don't rethrow — still capture local mic
        }

        // Setup AVAudioEngine for local mic
        do {
            audioEngine = AVAudioEngine()
            let inputNode = audioEngine!.inputNode
            let nativeMicFormat = inputNode.outputFormat(forBus: 0)
            Log.debug("Mic native format: \(nativeMicFormat.sampleRate)Hz, \(nativeMicFormat.channelCount)ch", prefix: "AUDIO")
            chunkWriter?.configureLocalInputFormat(nativeMicFormat)

            // IMPORTANT: tap with nil format to get native hardware samples
            inputNode.installTap(onBus: 0, bufferSize: 2048, format: nil) { [weak self] buffer, _ in
                self?.chunkWriter?.writeLocal(buffer: buffer, machTime: mach_absolute_time())
            }

            audioEngine?.prepare()
            try audioEngine?.start()
            Log.debug("AVAudioEngine mic capture started", prefix: "AUDIO")
        } catch {
            Log.debug("AVAudioEngine failed: \(error)", prefix: "AUDIO")
        }
    }

    func stop() -> [ChunkWriter.ChunkInfo] {
        if let stream = scStream {
            let sem = DispatchSemaphore(value: 0)
            stream.stopCapture { _ in sem.signal() }
            _ = sem.wait(timeout: .now() + 2.0)
        }
        scStream = nil
        scAudioDelegate = nil

        if audioEngine?.isRunning == true {
            audioEngine?.inputNode.removeTap(onBus: 0)
            audioEngine?.stop()
        }
        audioEngine = nil

        return chunkWriter?.finalize() ?? []
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
