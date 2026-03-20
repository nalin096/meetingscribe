import AVFoundation
import Foundation

class ChunkWriter {
    struct ChunkInfo {
        let remote: String
        let local: String
        let startMachTime: UInt64
        let startISO: String
    }

    private let outputDir: URL
    private let sampleRate: Int
    private let chunkDuration: Int
    private let overlapSeconds: Int
    private var chunkIndex = 0
    private var currentRemoteFile: AVAudioFile?
    private var currentLocalFile: AVAudioFile?
    private var chunkStartTime: Date?
    private var chunkStartMach: UInt64 = 0
    private var samplesWritten = 0
    private var chunks: [ChunkInfo] = []

    init(outputDir: URL, sampleRate: Int, chunkDuration: Int, overlapSeconds: Int) {
        self.outputDir = outputDir
        self.sampleRate = sampleRate
        self.chunkDuration = chunkDuration
        self.overlapSeconds = overlapSeconds
        try? FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
    }

    func start() { startNewChunk() }

    func writeRemote(sampleBuffer: CMSampleBuffer, machTime: UInt64) {
        if chunkStartMach == 0 { chunkStartMach = machTime }
        let maxSamples = sampleRate * chunkDuration
        if samplesWritten >= maxSamples { rollChunk() }
        let numSamples = CMSampleBufferGetNumSamples(sampleBuffer)
        samplesWritten += numSamples
    }

    func writeLocal(buffer: AVAudioPCMBuffer, machTime: UInt64) {
        guard let file = currentLocalFile else { return }
        try? file.write(from: buffer)
    }

    func finalize() -> [ChunkInfo] {
        closeCurrentChunk()
        return chunks
    }

    private func startNewChunk() {
        chunkIndex += 1
        chunkStartTime = Date()
        chunkStartMach = 0
        samplesWritten = 0

        let remoteName = String(format: "chunk_%03d_remote.wav", chunkIndex)
        let localName = String(format: "chunk_%03d_local.wav", chunkIndex)
        let format = AVAudioFormat(standardFormatWithSampleRate: Double(sampleRate), channels: 1)!

        currentRemoteFile = try? AVAudioFile(forWriting: outputDir.appendingPathComponent(remoteName), settings: format.settings)
        currentLocalFile = try? AVAudioFile(forWriting: outputDir.appendingPathComponent(localName), settings: format.settings)
    }

    private func closeCurrentChunk() {
        guard let startTime = chunkStartTime else { return }
        let remoteName = String(format: "chunk_%03d_remote.wav", chunkIndex)
        let localName = String(format: "chunk_%03d_local.wav", chunkIndex)

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        chunks.append(ChunkInfo(
            remote: remoteName, local: localName,
            startMachTime: chunkStartMach, startISO: iso.string(from: startTime)
        ))
        currentRemoteFile = nil
        currentLocalFile = nil
    }

    private func rollChunk() {
        closeCurrentChunk()
        startNewChunk()
    }
}
