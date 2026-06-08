import CoreGraphics
import ImageIO
import SwiftUI
import UIKit

struct PixelImage {
    let width: Int
    let height: Int
    let colors: [Color]
    let rgbValues: [Int]
}

enum ImageProcessor {
    static func loadImage(from data: Data) -> UIImage? {
        UIImage(data: data)
    }

    static func makePixelImage(from image: UIImage, size: Int = 32) -> PixelImage? {
        guard let cgImage = image.normalizedCGImage() else { return nil }

        let cropSide = min(cgImage.width, cgImage.height)
        let cropRect = CGRect(
            x: (cgImage.width - cropSide) / 2,
            y: (cgImage.height - cropSide) / 2,
            width: cropSide,
            height: cropSide
        )
        guard let cropped = cgImage.cropping(to: cropRect) else { return nil }

        var bytes = [UInt8](repeating: 0, count: size * size * 4)
        guard let context = CGContext(
            data: &bytes,
            width: size,
            height: size,
            bitsPerComponent: 8,
            bytesPerRow: size * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else {
            return nil
        }

        context.interpolationQuality = .high
        context.draw(cropped, in: CGRect(x: 0, y: 0, width: size, height: size))

        var colors: [Color] = []
        var rgbValues: [Int] = []
        colors.reserveCapacity(size * size)
        rgbValues.reserveCapacity(size * size)

        for index in stride(from: 0, to: bytes.count, by: 4) {
            let r = Int(bytes[index])
            let g = Int(bytes[index + 1])
            let b = Int(bytes[index + 2])
            rgbValues.append((r << 16) | (g << 8) | b)
            colors.append(Color(red: Double(r) / 255, green: Double(g) / 255, blue: Double(b) / 255))
        }

        return PixelImage(width: size, height: size, colors: colors, rgbValues: rgbValues)
    }
}

private extension UIImage {
    func normalizedCGImage() -> CGImage? {
        if imageOrientation == .up, let cgImage {
            return cgImage
        }

        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        let rendered = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            draw(in: CGRect(origin: .zero, size: size))
        }
        return rendered.cgImage
    }
}
