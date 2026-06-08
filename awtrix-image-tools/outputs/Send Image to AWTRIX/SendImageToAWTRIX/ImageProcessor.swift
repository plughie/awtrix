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
    private static let saturation = 1.35
    private static let contrast = 1.18

    static func loadImage(from data: Data) -> UIImage? {
        UIImage(data: data)
    }

    static func makePixelImage(from image: UIImage, cropRect: CGRect? = nil, width: Int = 32) -> PixelImage? {
        guard let cgImage = image.normalizedCGImage() else { return nil }

        let defaultSide = min(cgImage.width, cgImage.height)
        let defaultCropRect = CGRect(
            x: (cgImage.width - defaultSide) / 2,
            y: (cgImage.height - defaultSide) / 2,
            width: defaultSide,
            height: defaultSide
        )
        let requestedCrop = cropRect ?? defaultCropRect
        let imageBounds = CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height)
        let safeCrop = requestedCrop.integral.intersection(imageBounds)
        guard safeCrop.width > 0, safeCrop.height > 0, let cropped = cgImage.cropping(to: safeCrop) else { return nil }

        let scaledHeight = max(8, Int(round(safeCrop.height / safeCrop.width * CGFloat(width))))
        var bytes = [UInt8](repeating: 0, count: width * scaledHeight * 4)
        guard let context = CGContext(
            data: &bytes,
            width: width,
            height: scaledHeight,
            bitsPerComponent: 8,
            bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else {
            return nil
        }

        context.interpolationQuality = .high
        context.draw(cropped, in: CGRect(x: 0, y: 0, width: width, height: scaledHeight))

        var colors: [Color] = []
        var rgbValues: [Int] = []
        colors.reserveCapacity(width * scaledHeight)
        rgbValues.reserveCapacity(width * scaledHeight)

        for index in stride(from: 0, to: bytes.count, by: 4) {
            let adjusted = adjustedRGB(red: bytes[index], green: bytes[index + 1], blue: bytes[index + 2])
            let r = adjusted.red
            let g = adjusted.green
            let b = adjusted.blue
            rgbValues.append((r << 16) | (g << 8) | b)
            colors.append(Color(red: Double(r) / 255, green: Double(g) / 255, blue: Double(b) / 255))
        }

        return PixelImage(width: width, height: scaledHeight, colors: colors, rgbValues: rgbValues)
    }

    private static func adjustedRGB(red: UInt8, green: UInt8, blue: UInt8) -> (red: Int, green: Int, blue: Int) {
        let r = Double(red)
        let g = Double(green)
        let b = Double(blue)
        let luma = (0.299 * r) + (0.587 * g) + (0.114 * b)

        return (
            red: clamp(((luma + (r - luma) * saturation) - 128) * contrast + 128),
            green: clamp(((luma + (g - luma) * saturation) - 128) * contrast + 128),
            blue: clamp(((luma + (b - luma) * saturation) - 128) * contrast + 128)
        )
    }

    private static func clamp(_ value: Double) -> Int {
        min(255, max(0, Int(round(value))))
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
