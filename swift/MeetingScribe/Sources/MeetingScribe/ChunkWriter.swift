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
    var localSampleRate: Double = 48000
    private var chunkStartTime: Date?
    private var chunkStartMach: UInt64 = 0
    private var samplesWritten = 0
    private var chunks: [ChunkInfo] = []
    private let writeQueue = DispatchQueue(label: "com.meetingscribe.chunkwriter")

    // Local mic converter
    private var localConverter: AVAudioConverter?
    private let localOutputFormat = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 1)!

    // Remote converter
    private var remoteConverter: AVAudioConverter?

    init(outputDir: URL, sampleRate: Int, chunkDuration: Int, overlapSeconds: Int) {
        self.outputDir = outputDir
        self.sampleRate = sampleRate
        self.chunkDuration = chunkDuration
        self.overlapSeconds = overlapSeconds
        try? FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
    }

    func start() { startNewChunk() }

    func configureLocalInputFormat(_ inputFormat: AVAudioFormat) {
        writeQueue.sync {
            localConverter = AVAudioConverter(from: inputFormat, to: localOutputFormat)
            localSampleRate = localOutputFormat.sampleRate
        }
    }

    func writeRemote(sampleBuffer: CMSampleBuffer, machTime: UInt64) {
        writeQueue.sync {
            if chunkStartMach == 0 { chunkStartMach = machTime }
            let maxSamples = sampleRate * chunkDuration
            if samplesWritten >= maxSamples { rollChunk() }

            guard let remoteFile = currentRemoteFile else { return }
            guard let pcm = pcmBufferFromSampleBuffer(sampleBuffer) else { return }

            // Convert to mono 16kHz if needed
            if let converted = convertToRemoteFormat(pcm) {
                try? remoteFile.write(from: converted)
                samplesWritten += Int(converted.frameLength)
            } else {
                try? remoteFile.write(from: pcm)
                samplesWritten += Int(pcm.frameLength)
            }
        }
    }

    private func pcmBufferFromSampleBuffer(_ sampleBuffer: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard let fmt = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbdPtr = CMAudioFormatDescriptionGetStreamBasicDescription(fmt) else { return nil }
        var asbd = asbdPtr.pointee
        guard let avFmt = AVAudioFormat(streamDescription: &asbd) else { return nil }

        let frames = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        guard frames > 0, let buf = AVAudioPCMBuffer(pcmFormat: avFmt, frameCapacity: frames) else { return nil }
        buf.frameLength = frames

        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer, at: 0, frameCount: Int32(frames), into: buf.mutableAudioBufferList
        )
        return status == noErr ? buf : nil
    }

    private func convertToRemoteFormat(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        let targetFormat = AVAudioFormat(standardFormatWithSampleRate: Double(sampleRate), channels: 1)!
        if buffer.format.sampleRate == targetFormat.sampleRate && buffer.format.channelCount == targetFormat.channelCount {
            return nil  // no conversion needed
        }

        if remoteConverter == nil || remoteConverter?.inputFormat != buffer.format {
            remoteConverter = AVAudioConverter(from: buffer.format, to: targetFormat)
        }
        guard let converter = remoteConverter else { return nil }

        let ratio = targetFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 1
        guard let out = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: capacity) else { return nil }

        var error: NSError?
        var consumed = false
        converter.convert(to: out, error: &error) { _, outStatus in
            if consumed { outStatus.pointee = .noDataNow; return nil }
            consumed = true
            outStatus.pointee = .haveData
            return buffer
        }
        return (error == nil && out.frameLength > 0) ? out : nil
    }

    func writeLocal(buffer: AVAudioPCMBuffer, machTime: UInt64) {
        writeQueue.sync {
            guard let file = currentLocalFile else { return }

            // Convert from native mic format to our output format if needed
            if let converter = localConverter {
                let ratio = localOutputFormat.sampleRate / buffer.format.sampleRate
                let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 1
                guard let converted = AVAudioPCMBuffer(pcmFormat: localOutputFormat, frameCapacity: capacity) else { return }

                var error: NSError?
                var consumed = false
                converter.convert(to: converted, error: &error) { _, outStatus in
                    if consumed {
                        outStatus.pointee = .noDataNow
                        return nil
                    }
                    consumed = true
                    outStatus.pointee = .haveData
                    return buffer
                }
                if error == nil && converted.frameLength > 0 {
                    try? file.write(from: converted)
                }
            } else {
                try? file.write(from: buffer)
            }
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

        currentRemoteFile = try? AVAudioFile(forWriting: outputDir.appendingPathComponent(remoteName), settings: remoteFormat.settings)
        currentLocalFile = try? AVAudioFile(forWriting: outputDir.appendingPathComponent(localName), settings: localOutputFormat.settings)
    }

    private func closeCurrentChunk() {
        guard let startTime = chunkStartTime else { return }
        let remoteName = String(format: "chunk_%03d_remote.wav", chunkIndex)
        let localName = String(format: "chunk_%03d_local.wav", chunkIndex)

        // Release file handles
        currentRemoteFile = nil
        currentLocalFile = nil

        // Deterministically fix WAV headers
        patchWavHeaderIfNeeded(outputDir.appendingPathComponent(remoteName))
        patchWavHeaderIfNeeded(outputDir.appendingPathComponent(localName))

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        chunks.append(ChunkInfo(
            remote: remoteName, local: localName,
            startMachTime: chunkStartMach, startISO: iso.string(from: startTime)
        ))
    }

    private func patchWavHeaderIfNeeded(_ url: URL) {
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
              let fileSize = (attrs[.size] as? NSNumber)?.uint64Value,
              fileSize >= 44,
              let fh = try? FileHandle(forUpdating: url) else { return }
        defer { try? fh.close() }

        // Write RIFF chunk size = fileSize - 8
        fh.seek(toFileOffset: 4)
        var riffSize = UInt32(fileSize - 8).littleEndian
        fh.write(Data(bytes: &riffSize, count: 4))

        // Find data chunk and fix its size
        var offset: UInt64 = 12
        while offset + 8 <= fileSize {
            fh.seek(toFileOffset: offset)
            guard let chunkID = try? fh.read(upToCount: 4), chunkID.count == 4,
                  let chunkSizeData = try? fh.read(upToCount: 4), chunkSizeData.count == 4 else { break }
            let chunkSize = chunkSizeData.withUnsafeBytes { $0.load(as: UInt32.self).littleEndian }
            if chunkID == Data("data".utf8) {
                let dataStart = fh.offsetInFile
                var dataSize = UInt32(fileSize - dataStart).littleEndian
                fh.seek(toFileOffset: dataStart - 4)
                fh.write(Data(bytes: &dataSize, count: 4))
                break
            }
            offset = fh.offsetInFile + UInt64(chunkSize + (chunkSize & 1))
        }
    }

    private func rollChunk() {
        closeCurrentChunk()
        startNewChunk()
    }
}
