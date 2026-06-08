import Foundation

struct AwtrixClient {
    private let frameWidth = 32
    private let frameHeight = 8
    private let barHeight = 4

    var host: String
    var appPrefix: String

    func prepareForUpload(keepInRotation: Bool = false) async throws {
        try await getStatsWithRetry()
        if !keepInRotation {
            try await stopAndCleanup()
        }
        try await getStatsWithRetry()
    }

    func send(pixelImage: PixelImage, loop: Bool, totalSeconds: Double = 8, direction: ScrollDirection = .topToBottom, keepInRotation: Bool = false) async throws {
        try await getStatsWithRetry()
        let frames = makeVerticalFrames(from: pixelImage, direction: direction)
        let frameDelay = UInt64((totalSeconds / Double(frames.count)) * 1_000_000_000)
        let appDuration = loop ? 86_400 : max(1, Int(ceil(totalSeconds)) + 1)
        let appLifetime = keepInRotation ? 0 : appDuration + 2
        let appName = appPrefix

        try await postFrame(frames[0], appName: appName, duration: appDuration, lifetime: appLifetime, save: keepInRotation)
        let switchBody = try JSONSerialization.data(withJSONObject: ["name": appName])
        try await post(path: "/api/switch", body: switchBody)

        repeat {
            for frame in frames {
                try Task.checkCancellation()
                try await postFrame(frame, appName: appName, duration: appDuration, lifetime: appLifetime, save: keepInRotation)
                try await Task.sleep(nanoseconds: frameDelay)
            }
        } while loop

        try await stop(keepInRotation: keepInRotation)
    }

    func stopAndCleanup() async throws {
        try await cleanupCustomApps(appName: appPrefix)
    }

    func stop(keepInRotation: Bool) async throws {
        if keepInRotation {
            try await post(path: "/api/nextapp", body: nil)
        } else {
            try await stopAndCleanup()
        }
    }

    private func postFrame(_ frame: [Int], appName: String, duration: Int, lifetime: Int, save: Bool) async throws {
        let payload = AwtrixPayload(
            draw: [DrawCommand(db: [0, 0, frameWidth, frameHeight, frame])],
            duration: duration,
            lifetime: lifetime,
            noScroll: true,
            save: save
        )
        let body = try JSONEncoder().encode(payload)
        try await post(path: "/api/custom", queryItems: [URLQueryItem(name: "name", value: appName)], body: body)
    }

    private func cleanupCustomApps(appName: String) async throws {
        let names = cleanupNames(appName: appName)

        for _ in 0..<4 {
            try await post(path: "/api/nextapp", body: nil)
            try await Task.sleep(nanoseconds: 800_000_000)

            for name in names {
                try await post(path: "/api/custom", queryItems: [URLQueryItem(name: "name", value: name)], body: nil)
            }

            try await Task.sleep(nanoseconds: 800_000_000)
            if try await loopIsClean(names: names) {
                return
            }
        }

        throw AwtrixError.cleanupFailed
    }

    private func cleanupNames(appName: String) -> [String] {
        var names = [appName]
        names.append("image_to_awtrix_bar")
        names.append("sacred_square")
        names.append("sacred_square_bar")
        names.append(contentsOf: (1...8).map { "image_to_awtrix_bar_\($0)" })
        names.append(contentsOf: (1...4).map { "sacred_square_\($0)" })
        names.append(contentsOf: (1...8).map { "sacred_square_bar_\($0)" })
        names.append(contentsOf: (1...8).map { "_\($0)" })
        return Array(Set(names))
    }

    private func loopIsClean(names: [String]) async throws -> Bool {
        let data = try await request(path: "/api/loop", method: "GET", body: nil)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return !object.keys.contains { names.contains($0) }
    }

    private func makeVerticalFrames(from pixelImage: PixelImage, direction: ScrollDirection) -> [[Int]] {
        switch direction {
        case .topToBottom, .bottomToTop:
            let frameCount = max(1, Int(ceil(Double(pixelImage.height) / Double(barHeight))))
            let indices = direction == .topToBottom ? Array(0..<frameCount) : Array((0..<frameCount).reversed())
            return indices.map { index in
                rows(from: pixelImage, y: index * barHeight, height: frameHeight)
            }
        case .leftToRight, .rightToLeft:
            let frameCount = max(1, Int(ceil(Double(pixelImage.width) / Double(barHeight))))
            let indices = direction == .leftToRight ? Array(0..<frameCount) : Array((0..<frameCount).reversed())
            return indices.map { index in
                columns(from: pixelImage, x: index * barHeight, width: frameWidth, height: frameHeight)
            }
        }
    }

    private func rows(from pixelImage: PixelImage, y: Int, height: Int) -> [Int] {
        var values: [Int] = []
        values.reserveCapacity(pixelImage.width * height)
        for row in y..<(y + height) {
            guard row >= 0 && row < pixelImage.height else {
                values.append(contentsOf: Array(repeating: 0, count: pixelImage.width))
                continue
            }
            let start = row * pixelImage.width
            values.append(contentsOf: pixelImage.rgbValues[start..<(start + pixelImage.width)])
        }
        return values
    }

    private func columns(from pixelImage: PixelImage, x: Int, width: Int, height: Int) -> [Int] {
        var values: [Int] = []
        values.reserveCapacity(width * height)
        for row in 0..<height {
            for column in x..<(x + width) {
                guard row < pixelImage.height && column >= 0 && column < pixelImage.width else {
                    values.append(0)
                    continue
                }
                values.append(pixelImage.rgbValues[row * pixelImage.width + column])
            }
        }
        return values
    }

    private func post(path: String, queryItems: [URLQueryItem]? = nil, body: Data?) async throws {
        try await request(path: path, queryItems: queryItems, method: "POST", body: body)
    }

    private func getStatsWithRetry() async throws {
        do {
            try await request(path: "/api/stats", method: "GET", body: nil)
        } catch {
            try await Task.sleep(nanoseconds: 350_000_000)
            try await request(path: "/api/stats", method: "GET", body: nil)
        }
    }

    @discardableResult
    private func request(path: String, queryItems: [URLQueryItem]? = nil, method: String, body: Data?) async throws -> Data {
        var components = URLComponents()
        components.scheme = "http"
        components.host = normalizedHost
        components.path = path
        components.queryItems = queryItems

        guard let url = components.url else {
            throw AwtrixError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 10
        request.setValue("close", forHTTPHeaderField: "Connection")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode) else {
            throw AwtrixError.requestFailed
        }
        return data
    }

    private var normalizedHost: String {
        var value = host.trimmingCharacters(in: .whitespacesAndNewlines)
        if let url = URL(string: value), let parsedHost = url.host {
            value = parsedHost
        }
        if let slashIndex = value.firstIndex(of: "/") {
            value = String(value[..<slashIndex])
        }
        if let colonIndex = value.firstIndex(of: ":"), value.filter({ $0 == ":" }).count == 1 {
            value = String(value[..<colonIndex])
        }
        return value
    }
}

enum ScrollDirection: String, CaseIterable, Identifiable {
    case topToBottom
    case bottomToTop
    case leftToRight
    case rightToLeft

    var id: String { rawValue }

    var label: String {
        switch self {
        case .topToBottom:
            return "Top to Bottom"
        case .bottomToTop:
            return "Bottom to Top"
        case .leftToRight:
            return "Left to Right"
        case .rightToLeft:
            return "Right to Left"
        }
    }
}

private struct AwtrixPayload: Encodable {
    let draw: [DrawCommand]
    let duration: Int
    let lifetime: Int
    let noScroll: Bool
    let save: Bool
}

private struct DrawCommand: Encodable {
    let db: [AnyEncodable]

    init(db: [Any]) {
        self.db = db.map { AnyEncodable($0) }
    }
}

private struct AnyEncodable: Encodable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let int as Int:
            try container.encode(int)
        case let values as [Int]:
            try container.encode(values)
        default:
            throw AwtrixError.requestFailed
        }
    }
}

enum AwtrixError: Error {
    case invalidURL
    case requestFailed
    case cleanupFailed
}
