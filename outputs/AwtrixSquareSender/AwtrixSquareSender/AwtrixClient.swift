import Foundation

struct AwtrixClient {
    var host: String
    var appPrefix: String

    func upload(pixelImage: PixelImage, duration: Int = 1) async throws {
        let bars = makeBars(from: pixelImage)
        try await post(path: "/api/custom?name=\(appPrefix)_", body: nil)

        for index in 0..<8 {
            let frame = bars[index] + bars[index + 1]
            let payload = AwtrixPayload(
                draw: [DrawCommand(db: [0, 0, 32, 8, frame])],
                duration: duration,
                lifetime: 0,
                noScroll: true,
                save: true
            )
            let body = try JSONEncoder().encode(payload)
            try await post(path: "/api/custom?name=\(appPrefix)_\(index + 1)", body: body)
        }
    }

    func runOnce(totalSeconds: Double = 8) async throws {
        let delay = UInt64((totalSeconds / 8) * 1_000_000_000)
        for index in 1...8 {
            let switchBody = try JSONSerialization.data(withJSONObject: ["name": "\(appPrefix)_\(index)"])
            try await post(path: "/api/switch", body: switchBody)
            try await Task.sleep(nanoseconds: delay)
        }
        try await post(path: "/api/nextapp", body: Data())
    }

    private func makeBars(from pixelImage: PixelImage) -> [[Int]] {
        (0...8).map { index in
            let y = Int(round(Double(index * (pixelImage.height - 4)) / 8.0))
            return rows(from: pixelImage, y: y, height: 4)
        }
    }

    private func rows(from pixelImage: PixelImage, y: Int, height: Int) -> [Int] {
        var values: [Int] = []
        values.reserveCapacity(pixelImage.width * height)
        for row in y..<(y + height) {
            let start = row * pixelImage.width
            values.append(contentsOf: pixelImage.rgbValues[start..<(start + pixelImage.width)])
        }
        return values
    }

    private func post(path: String, body: Data?) async throws {
        guard var components = URLComponents(string: "http://\(host)\(path)") else {
            throw AwtrixError.invalidURL
        }
        components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        guard let url = components.url else {
            throw AwtrixError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 10
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode) else {
            throw AwtrixError.requestFailed
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
}
