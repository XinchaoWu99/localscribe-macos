// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "LocalScribeSystemAudio",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(
            name: "localscribe-system-audio",
            targets: ["LocalScribeSystemAudio"]
        ),
    ],
    targets: [
        .executableTarget(
            name: "LocalScribeSystemAudio"
        ),
    ]
)
