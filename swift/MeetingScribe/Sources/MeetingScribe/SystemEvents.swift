import Foundation
import AppKit
import CoreAudio

class SystemEvents {
    var onSleep: (() -> Void)?
    var onWake: (() -> Void)?
    var onAudioDeviceChange: (() -> Void)?

    private var sleepTime: Date?

    init() {
        setupNotifications()
        setupAudioDeviceListener()
    }

    private func setupNotifications() {
        let ws = NSWorkspace.shared.notificationCenter

        ws.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { [weak self] _ in
            self?.sleepTime = Date()
            self?.onSleep?()
        }

        ws.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { [weak self] _ in
            if let sleepTime = self?.sleepTime {
                let sleepDuration = Date().timeIntervalSince(sleepTime)
                if sleepDuration > 300 {
                    self?.onWake?()
                }
            }
            self?.sleepTime = nil
        }
    }

    private func setupAudioDeviceListener() {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            DispatchQueue.main
        ) { [weak self] _, _ in
            self?.onAudioDeviceChange?()
        }
    }
}
