// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "MeetingScribe",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/LebJe/TOMLKit.git", from: "0.6.0"),
    ],
    targets: [
        .executableTarget(
            name: "MeetingScribe",
            dependencies: ["TOMLKit"]
        ),
        .testTarget(
            name: "MeetingScribeTests",
            dependencies: ["MeetingScribe"]
        ),
    ]
)
