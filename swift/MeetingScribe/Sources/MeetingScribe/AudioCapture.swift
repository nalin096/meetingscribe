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

        // Setup SCStream for remote audio — capture all windows from the target app
        let appWindows = content.windows.filter { $0.owningApplication?.bundleIdentifier == app.bundleIdentifier }
        guard let display = content.displays.first else {
            throw CaptureError.noDisplay
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

        // Setup AVAudioEngine for local mic
        audioEngine = AVAudioEngine()
        let inputNode = audioEngine!.inputNode
        let format = AVAudioFormat(standardFormatWithSampleRate: Double(config.sampleRate), channels: 1)!

        inputNode.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, time in
            let machTime = mach_absolute_time()
            self?.chunkWriter?.writeLocal(buffer: buffer, machTime: machTime)
        }

        try audioEngine?.start()
    }

    func stop() -> [ChunkWriter.ChunkInfo] {
        scStream?.stopCapture { _ in }
        scStream = nil

        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine?.stop()
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
