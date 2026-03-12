import AVFAudio
import CoreGraphics
import CoreMedia
import Darwin
import Foundation
import ScreenCaptureKit

@main
struct LocalScribeSystemAudioTool {
    static func main() async {
        do {
            let options = try CommandLineOptions.parse(arguments: Array(CommandLine.arguments.dropFirst()))

            if options.listDisplays {
                try await DisplayDiscovery.printDisplays()
                return
            }

            let backend = try await BackendSessionClient(options: options)
            let capture = try await SystemAudioCaptureController(options: options, backend: backend)
            try await capture.start()

            print("LocalScribe system-audio capture is running.")
            print("Session ID: \(backend.sessionID)")
            print("Open \(options.serverBaseURL.absoluteString) in Safari and load the session from Recent sessions.")
            if let displayID = capture.displayID {
                print("Capturing display \(displayID). Press Control-C to stop.")
            }

            if let durationSeconds = options.durationSeconds {
                let nanoseconds = UInt64(max(0, durationSeconds) * 1_000_000_000)
                try await Task.sleep(nanoseconds: nanoseconds)
                try await capture.stop()
                return
            }

            await SignalTrap.waitForTermination()
            try await capture.stop()
        } catch {
            FileHandle.standardError.write(Data("Error: \(error.localizedDescription)\n".utf8))
            Darwin.exit(1)
        }
    }
}

struct CommandLineOptions {
    let serverBaseURL: URL
    let sessionID: String?
    let language: String?
    let prompt: String?
    let diarize: Bool
    let chunkMillis: Int
    let displayID: UInt32?
    let durationSeconds: Double?
    let listDisplays: Bool

    static func parse(arguments: [String]) throws -> CommandLineOptions {
        var server = "http://127.0.0.1:8765"
        var sessionID: String?
        var language: String?
        var prompt: String?
        var diarize = true
        var chunkMillis = 2200
        var displayID: UInt32?
        var durationSeconds: Double?
        var listDisplays = false

        var index = 0
        while index < arguments.count {
            let argument = arguments[index]
            switch argument {
            case "--server":
                index += 1
                server = try value(after: argument, in: arguments, index: index)
            case "--session-id":
                index += 1
                sessionID = try value(after: argument, in: arguments, index: index)
            case "--language":
                index += 1
                language = try value(after: argument, in: arguments, index: index)
            case "--prompt":
                index += 1
                prompt = try value(after: argument, in: arguments, index: index)
            case "--chunk-ms":
                index += 1
                chunkMillis = Int(try value(after: argument, in: arguments, index: index)) ?? chunkMillis
            case "--display-id":
                index += 1
                displayID = UInt32(try value(after: argument, in: arguments, index: index))
            case "--duration":
                index += 1
                durationSeconds = Double(try value(after: argument, in: arguments, index: index))
            case "--no-diarize":
                diarize = false
            case "--list-displays":
                listDisplays = true
            case "--help", "-h":
                printHelp()
                Darwin.exit(0)
            default:
                throw HelperError.usage("Unknown argument: \(argument)")
            }
            index += 1
        }

        guard let serverBaseURL = URL(string: server) else {
            throw HelperError.usage("Invalid --server URL: \(server)")
        }

        return CommandLineOptions(
            serverBaseURL: serverBaseURL,
            sessionID: sessionID,
            language: language,
            prompt: prompt,
            diarize: diarize,
            chunkMillis: max(500, chunkMillis),
            displayID: displayID,
            durationSeconds: durationSeconds,
            listDisplays: listDisplays
        )
    }

    static func printHelp() {
        let text = """
        localscribe-system-audio

        Capture native macOS system audio with ScreenCaptureKit and stream it into LocalScribe.

        Options:
          --server URL         LocalScribe base URL (default: http://127.0.0.1:8765)
          --session-id ID      Attach to an existing LocalScribe live session
          --language CODE      Language hint, for example en or zh
          --prompt TEXT        Prompt bias for names and acronyms
          --chunk-ms INT       Chunk duration in milliseconds (default: 2200)
          --display-id ID      Display ID to use for ScreenCaptureKit
          --duration SECONDS   Stop automatically after N seconds
          --no-diarize         Disable speaker assignment
          --list-displays      Print available displays and exit
          --help               Show this help
        """
        print(text)
    }

    private static func value(after flag: String, in arguments: [String], index: Int) throws -> String {
        guard index < arguments.count else {
            throw HelperError.usage("Missing value after \(flag)")
        }
        return arguments[index]
    }
}

final class BackendSessionClient {
    let sessionID: String

    private let options: CommandLineOptions
    private let urlSession: URLSession
    private let webSocketTask: URLSessionWebSocketTask
    private var sequence = 1

    init(options: CommandLineOptions) async throws {
        self.options = options
        self.urlSession = URLSession(configuration: .default)

        if let sessionID = options.sessionID, !sessionID.isEmpty {
            self.sessionID = sessionID
        } else {
            self.sessionID = try await Self.createSession(serverBaseURL: options.serverBaseURL, session: urlSession)
        }

        let webSocketURL = try Self.makeWebSocketURL(serverBaseURL: options.serverBaseURL, sessionID: self.sessionID)
        self.webSocketTask = urlSession.webSocketTask(with: webSocketURL)
        self.webSocketTask.resume()
        startReceiveLoop()
    }

    func sendChunk(wavData: Data) async throws {
        var envelope: [String: Any] = [
            "type": "audio_chunk",
            "sequence": sequence,
            "mimeType": "audio/wav",
            "payload": wavData.base64EncodedString(),
            "diarize": options.diarize,
        ]
        sequence += 1
        if let language = options.language, !language.isEmpty {
            envelope["language"] = language
        }
        if let prompt = options.prompt, !prompt.isEmpty {
            envelope["prompt"] = prompt
        }

        let payload = try JSONSerialization.data(withJSONObject: envelope)
        guard let text = String(data: payload, encoding: .utf8) else {
            throw HelperError.transport("Could not encode WebSocket payload.")
        }
        try await webSocketTask.send(.string(text))
    }

    func sendStop() async {
        let payload = #"{"type":"stop"}"#
        try? await webSocketTask.send(.string(payload))
        webSocketTask.cancel(with: .normalClosure, reason: nil)
        urlSession.invalidateAndCancel()
    }

    private func startReceiveLoop() {
        webSocketTask.receive { [weak self] result in
            guard let self else {
                return
            }

            switch result {
            case let .failure(error):
                FileHandle.standardError.write(Data("WebSocket receive error: \(error.localizedDescription)\n".utf8))
            case let .success(message):
                switch message {
                case let .string(text):
                    if text.contains(#""type":"error""#) {
                        FileHandle.standardError.write(Data("LocalScribe reported an error: \(text)\n".utf8))
                    }
                case .data:
                    break
                @unknown default:
                    break
                }
                self.startReceiveLoop()
            }
        }
    }

    private static func createSession(serverBaseURL: URL, session: URLSession) async throws -> String {
        var request = URLRequest(url: serverBaseURL.appending(path: "/api/sessions"))
        request.httpMethod = "POST"
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200..<300).contains(httpResponse.statusCode) else {
            throw HelperError.transport("LocalScribe did not accept the session creation request.")
        }

        let decoded = try JSONDecoder().decode(CreateSessionResponse.self, from: data)
        return decoded.session.sessionId
    }

    private static func makeWebSocketURL(serverBaseURL: URL, sessionID: String) throws -> URL {
        guard var components = URLComponents(url: serverBaseURL, resolvingAgainstBaseURL: false) else {
            throw HelperError.transport("Could not build a WebSocket URL from \(serverBaseURL.absoluteString).")
        }
        components.scheme = components.scheme == "https" ? "wss" : "ws"
        components.path = "/ws/live/\(sessionID)"
        guard let url = components.url else {
            throw HelperError.transport("Could not build a WebSocket URL from \(serverBaseURL.absoluteString).")
        }
        return url
    }
}

final class SystemAudioCaptureController: NSObject, SCStreamDelegate, SCStreamOutput {
    private let options: CommandLineOptions
    private let backend: BackendSessionClient
    private let audioQueue = DispatchQueue(label: "localscribe.system-audio.queue")
    private let chunkAccumulator: AudioChunkAccumulator

    private var stream: SCStream?
    private var converter: AVAudioConverter?
    private var converterInputKey: String?
    private(set) var displayID: UInt32?

    init(options: CommandLineOptions, backend: BackendSessionClient) async throws {
        self.options = options
        self.backend = backend
        self.chunkAccumulator = AudioChunkAccumulator(chunkMillis: options.chunkMillis)
        super.init()
    }

    func start() async throws {
        try ensureScreenCaptureAccess()
        let display = try await DisplayDiscovery.selectDisplay(requestedID: options.displayID)
        displayID = display.displayID

        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let configuration = SCStreamConfiguration()
        configuration.width = 2
        configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 60)
        configuration.showsCursor = false
        configuration.capturesAudio = true
        configuration.excludesCurrentProcessAudio = true
        configuration.sampleRate = 48_000
        configuration.channelCount = 2

        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        self.stream = stream
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: audioQueue)
        try await stream.startCapture()
    }

    func stop() async throws {
        if let finalChunk = chunkAccumulator.flushRemainder() {
            try await backend.sendChunk(wavData: finalChunk)
        }
        if let stream {
            try await stream.stopCapture()
        }
        await backend.sendStop()
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write(Data("ScreenCaptureKit stopped: \(error.localizedDescription)\n".utf8))
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of outputType: SCStreamOutputType) {
        guard outputType == .audio else {
            return
        }

        do {
            let pcmBuffer = try convert(sampleBuffer: sampleBuffer)
            if let chunk = chunkAccumulator.append(buffer: pcmBuffer) {
                Task {
                    try? await self.backend.sendChunk(wavData: chunk)
                }
            }
        } catch {
            FileHandle.standardError.write(Data("Audio conversion failed: \(error.localizedDescription)\n".utf8))
        }
    }

    private func convert(sampleBuffer: CMSampleBuffer) throws -> AVAudioPCMBuffer {
        guard let description = CMSampleBufferGetFormatDescription(sampleBuffer) else {
            throw HelperError.audio("Missing format description in sample buffer.")
        }
        guard let inputFormat = AVAudioFormat(cmAudioFormatDescription: description) else {
            throw HelperError.audio("Could not derive an AVAudioFormat from the sample buffer.")
        }

        let frameCount = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        guard let inputBuffer = AVAudioPCMBuffer(pcmFormat: inputFormat, frameCapacity: frameCount) else {
            throw HelperError.audio("Could not allocate an input PCM buffer.")
        }
        inputBuffer.frameLength = frameCount

        let copyStatus = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer,
            at: 0,
            frameCount: Int32(frameCount),
            into: inputBuffer.mutableAudioBufferList
        )
        guard copyStatus == noErr else {
            throw HelperError.audio("Could not copy PCM data from the sample buffer. OSStatus=\(copyStatus)")
        }

        let outputFormat = AudioChunkAccumulator.outputFormat
        let inputKey = "\(inputFormat.sampleRate)-\(inputFormat.channelCount)-\(inputFormat.commonFormat.rawValue)"
        if converter == nil || converterInputKey != inputKey {
            converter = AVAudioConverter(from: inputFormat, to: outputFormat)
            converterInputKey = inputKey
        }
        guard let converter else {
            throw HelperError.audio("Could not create an audio converter.")
        }

        let ratio = outputFormat.sampleRate / inputFormat.sampleRate
        let outputCapacity = AVAudioFrameCount((Double(frameCount) * ratio).rounded(.up) + 8)
        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: outputCapacity) else {
            throw HelperError.audio("Could not allocate an output PCM buffer.")
        }

        var providedInput = false
        var conversionError: NSError?
        let status = converter.convert(to: outputBuffer, error: &conversionError) { _, outStatus in
            if providedInput {
                outStatus.pointee = .noDataNow
                return nil
            }
            providedInput = true
            outStatus.pointee = .haveData
            return inputBuffer
        }

        if let conversionError {
            throw conversionError
        }
        guard status == .haveData || status == .inputRanDry || status == .endOfStream else {
            throw HelperError.audio("Audio conversion ended with status \(status.rawValue).")
        }
        return outputBuffer
    }

    private func ensureScreenCaptureAccess() throws {
        if CGPreflightScreenCaptureAccess() {
            return
        }
        _ = CGRequestScreenCaptureAccess()
        throw HelperError.permission(
            "Screen Recording access is required. Grant permission in System Settings, then run the helper again."
        )
    }
}

final class AudioChunkAccumulator {
    static let outputFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: 16_000,
        channels: 1,
        interleaved: false
    )!

    private let targetFrames: Int
    private var pendingPCM = Data()
    private var pendingFrames = 0

    init(chunkMillis: Int) {
        targetFrames = max(1_600, Int(AudioChunkAccumulator.outputFormat.sampleRate * Double(chunkMillis) / 1000.0))
    }

    func append(buffer: AVAudioPCMBuffer) -> Data? {
        guard let channelData = buffer.int16ChannelData else {
            return nil
        }

        let frameCount = Int(buffer.frameLength)
        let byteCount = frameCount * MemoryLayout<Int16>.size
        pendingPCM.append(Data(bytes: channelData[0], count: byteCount))
        pendingFrames += frameCount

        guard pendingFrames >= targetFrames else {
            return nil
        }
        return dequeue(frames: targetFrames)
    }

    func flushRemainder() -> Data? {
        guard pendingFrames > 0 else {
            return nil
        }
        return dequeue(frames: pendingFrames)
    }

    private func dequeue(frames: Int) -> Data {
        let byteCount = frames * MemoryLayout<Int16>.size
        let pcm = pendingPCM.prefix(byteCount)
        pendingPCM.removeFirst(byteCount)
        pendingFrames -= frames
        return Self.wrapWAV(pcm: Data(pcm), frames: frames)
    }

    private static func wrapWAV(pcm: Data, frames: Int) -> Data {
        let channelCount = 1
        let sampleRate = 16_000
        let bitsPerSample = 16
        let byteRate = sampleRate * channelCount * bitsPerSample / 8
        let blockAlign = channelCount * bitsPerSample / 8

        var data = Data()
        data.reserveCapacity(44 + pcm.count)
        data.append(contentsOf: Array("RIFF".utf8))
        data.append(littleEndian(UInt32(36 + pcm.count)))
        data.append(contentsOf: Array("WAVE".utf8))
        data.append(contentsOf: Array("fmt ".utf8))
        data.append(littleEndian(UInt32(16)))
        data.append(littleEndian(UInt16(1)))
        data.append(littleEndian(UInt16(channelCount)))
        data.append(littleEndian(UInt32(sampleRate)))
        data.append(littleEndian(UInt32(byteRate)))
        data.append(littleEndian(UInt16(blockAlign)))
        data.append(littleEndian(UInt16(bitsPerSample)))
        data.append(contentsOf: Array("data".utf8))
        data.append(littleEndian(UInt32(pcm.count)))
        data.append(pcm)
        return data
    }
}

enum DisplayDiscovery {
    static func printDisplays() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        for display in content.displays {
            print("Display ID \(display.displayID) \(display.width)x\(display.height)")
        }
    }

    static func selectDisplay(requestedID: UInt32?) async throws -> SCDisplay {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        if let requestedID {
            if let match = content.displays.first(where: { $0.displayID == requestedID }) {
                return match
            }
            throw HelperError.usage("Display \(requestedID) is not available. Run --list-displays to inspect options.")
        }

        let mainDisplayID = CGMainDisplayID()
        if let main = content.displays.first(where: { $0.displayID == mainDisplayID }) {
            return main
        }
        if let first = content.displays.first {
            return first
        }
        throw HelperError.permission("No displays are available to ScreenCaptureKit.")
    }
}

enum SignalTrap {
    static func waitForTermination() async {
        await withCheckedContinuation { continuation in
            signal(SIGINT, SIG_IGN)
            signal(SIGTERM, SIG_IGN)

            let intSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
            let termSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)

            let resumeOnce = ResumeOnce(continuation: continuation)
            intSource.setEventHandler {
                intSource.cancel()
                termSource.cancel()
                resumeOnce.resume()
            }
            termSource.setEventHandler {
                intSource.cancel()
                termSource.cancel()
                resumeOnce.resume()
            }

            intSource.resume()
            termSource.resume()
        }
    }
}

final class ResumeOnce {
    private let lock = NSLock()
    private var resumed = false
    private let continuation: CheckedContinuation<Void, Never>

    init(continuation: CheckedContinuation<Void, Never>) {
        self.continuation = continuation
    }

    func resume() {
        lock.lock()
        defer { lock.unlock() }
        guard !resumed else {
            return
        }
        resumed = true
        continuation.resume()
    }
}

enum HelperError: LocalizedError {
    case usage(String)
    case permission(String)
    case transport(String)
    case audio(String)

    var errorDescription: String? {
        switch self {
        case let .usage(message), let .permission(message), let .transport(message), let .audio(message):
            return message
        }
    }
}

private struct CreateSessionResponse: Decodable {
    struct SessionPayload: Decodable {
        let sessionId: String
    }

    let session: SessionPayload
}

private func littleEndian<T: FixedWidthInteger>(_ value: T) -> Data {
    var little = value.littleEndian
    return Data(bytes: &little, count: MemoryLayout<T>.size)
}
