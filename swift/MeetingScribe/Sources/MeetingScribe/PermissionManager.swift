import AVFoundation
import ScreenCaptureKit
import AppKit

struct PermissionManager {
    struct PermissionStatus {
        var screenRecording: Bool
        var microphone: Bool
        var accessibility: Bool
    }

    static func check() async -> PermissionStatus {
        let screen = await checkScreenRecording()
        let mic = checkMicrophone()
        let accessibility = checkAccessibility()
        return PermissionStatus(screenRecording: screen, microphone: mic, accessibility: accessibility)
    }

    static func requestMissing(_ status: PermissionStatus) {
        if !status.screenRecording || !status.accessibility {
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy") {
                NSWorkspace.shared.open(url)
            }
        }
        if !status.microphone {
            AVCaptureDevice.requestAccess(for: .audio) { _ in }
        }
    }

    private static func checkScreenRecording() async -> Bool {
        do {
            _ = try await SCShareableContent.current
            return true
        } catch { return false }
    }

    private static func checkMicrophone() -> Bool {
        AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }

    private static func checkAccessibility() -> Bool {
        AXIsProcessTrusted()
    }
}
