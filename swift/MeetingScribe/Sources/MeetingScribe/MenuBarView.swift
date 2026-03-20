import SwiftUI

struct MenuBarView: View {
    @ObservedObject var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(state.statusMessage)
                .font(.headline)

            if state.isRecording {
                Divider()
                Text("App: \(state.recordingApp)")
                Text("Duration: \(formatDuration(state.recordingDuration))")

                if let altApp = state.detectedAlternativeApp {
                    Button("Switch to \(altApp)") {
                        state.switchRecording()
                    }
                }

                Button("Discard Recording") {
                    state.discardRecording()
                }

                Button("Stop Recording") {
                    state.stopRecording()
                }
            }

            Divider()

            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q")
        }
        .padding(8)
        .onAppear {
            state.startMonitoring()
        }
    }

    private func formatDuration(_ seconds: TimeInterval) -> String {
        let m = Int(seconds) / 60
        let s = Int(seconds) % 60
        return String(format: "%02d:%02d", m, s)
    }
}
