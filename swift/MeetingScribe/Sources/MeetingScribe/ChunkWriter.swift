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
    var localSampleRate: Double = 48000  // Set by AudioCapture based on mic's native rate
    private var chunkStartTime: Date?
    private var chunkStartMach: UInt64 = 0
    private var samplesWritten = 0
    private var chunks: [ChunkInfo] = []
    private let writeQueue = DispatchQueue(label: "com.meetingscribe.chunkwriter")

    init(outputDir: URL, sampleRate: Int, chunkDuration: Int, overlapSeconds: Int) {
        self.outputDir = outputDir
        self.sampleRate = sampleRate
        self.chunkDuration = chunkDuration
        self.overlapSeconds = overlapSeconds
        try? FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
    }

    func start() { startNewChunk() }

    func writeRemote(sampleBuffer: CMSampleBuffer, machTime: UInt64) {
        writeQueue.sync {
            if chunkStartMach == 0 { chunkStartMach = machTime }
            let maxSamples = sampleRate * chunkDuration
            if samplesWritten >= maxSamples { rollChunk() }

            // Extract audio data from CMSampleBuffer and write to WAV
            guard let remoteFile = currentRemoteFile else { return }
            guard let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }

            let numSamples = CMSampleBufferGetNumSamples(sampleBuffer)
            guard numSamples > 0 else { return }

            var length = 0
            var dataPointer: UnsafeMutablePointer<Int8>?
            let status = CMBlockBufferGetDataPointer(blockBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &dataPointer)
            guard status == kCMBlockBufferNoErr, let data = dataPointer else { return }

            // Get the audio format from the sample buffer
            guard let formatDesc = CMSampleBufferGetFormatDescription(sampleBuffer),
                  let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(formatDesc) else { return }

            let channelCount = Int(asbd.pointee.mChannelsPerFrame)
            let frameCount = AVAudioFrameCount(numSamples)

            // Create AVAudioPCMBuffer matching the source format
            guard let srcFormat = AVAudioFormat(streamDescription: asbd),
                  let pcmBuffer = AVAudioPCMBuffer(pcmFormat: srcFormat, frameCapacity: frameCount) else { return }

            pcmBuffer.frameLength = frameCount

            // Copy raw audio data into the PCM buffer
            let bytesPerFrame = Int(asbd.pointee.mBytesPerFrame)
            let totalBytes = Int(frameCount) * bytesPerFrame
            guard totalBytes <= length else { return }

            if asbd.pointee.mFormatFlags & kAudioFormatFlagIsFloat != 0 {
                // Float32 format
                if let floatData = pcmBuffer.floatChannelData {
                    memcpy(floatData[0], data, min(totalBytes, length))
                }
            } else {
                // Int16 format
                if let int16Data = pcmBuffer.int16ChannelData {
                    memcpy(int16Data[0], data, min(totalBytes, length))
                }
            }

            // Convert to the output file's format if needed, then write
            if let outputFormat = AVAudioFormat(standardFormatWithSampleRate: Double(sampleRate), channels: 1),
               srcFormat.sampleRate != Double(sampleRate) || channelCount != 1 {
                // Need format conversion
                guard let converter = AVAudioConverter(from: srcFormat, to: outputFormat) else {
                    // Can't convert — try writing directly
                    try? remoteFile.write(from: pcmBuffer)
                    samplesWritten += numSamples
                    return
                }
                let convertedCapacity = AVAudioFrameCount(Double(frameCount) * Double(sampleRate) / srcFormat.sampleRate)
                guard let convertedBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: max(convertedCapacity, 1)) else { return }

                var error: NSError?
                converter.convert(to: convertedBuffer, error: &error) { _, outStatus in
                    outStatus.pointee = .haveData
                    return pcmBuffer
                }
                if error == nil {
                    try? remoteFile.write(from: convertedBuffer)
                }
            } else {
                try? remoteFile.write(from: pcmBuffer)
            }

            samplesWritten += numSamples
        }
    }

    func writeLocal(buffer: AVAudioPCMBuffer, machTime: UInt64) {
        writeQueue.sync {
            guard let file = currentLocalFile else { return }
            try? file.write(from: buffer)
        }
    }

    func finalize() -> [ChunkInfo] {
        writeQueue.sync {
            closeCurrentChunk()
            return chunks
        }
    }

    private func startNewChunk() {
        chunkIndex += 1
        chunkStartTime = Date()
        chunkStartMach = 0
        samplesWritten = 0

        let remoteName = String(format: "chunk_%03d_remote.wav", chunkIndex)
        let localName = String(format: "chunk_%03d_local.wav", chunkIndex)
        let remoteFormat = AVAudioFormat(standardFormatWithSampleRate: Double(sampleRate), channels: 1)!
        // Local file uses mic's native sample rate — Python pipeline resamples to 16kHz
        let localFormat = AVAudioFormat(standardFormatWithSampleRate: localSampleRate, channels: 1)!

        currentRemoteFile = try? AVAudioFile(forWriting: outputDir.appendingPathComponent(remoteName), settings: remoteFormat.settings)
        currentLocalFile = try? AVAudioFile(forWriting: outputDir.appendingPathComponent(localName), settings: localFormat.settings)
    }

    private func closeCurrentChunk() {
        guard let startTime = chunkStartTime else { return }
        let remoteName = String(format: "chunk_%03d_remote.wav", chunkIndex)
        let localName = String(format: "chunk_%03d_local.wav", chunkIndex)

        // Force AVAudioFile to flush WAV headers by releasing references.
        // AVAudioFile updates the RIFF/data chunk sizes in its deinit.
        // Use autoreleasepool to guarantee immediate deallocation.
        autoreleasepool {
            currentRemoteFile = nil
            currentLocalFile = nil
        }

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        chunks.append(ChunkInfo(
            remote: remoteName, local: localName,
            startMachTime: chunkStartMach, startISO: iso.string(from: startTime)
        ))
    }

    private func rollChunk() {
        closeCurrentChunk()
        startNewChunk()
    }
}
