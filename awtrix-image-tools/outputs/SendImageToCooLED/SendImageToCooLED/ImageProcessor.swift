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

    static func makeTestPattern(width: Int = 64, height: Int = 16) -> PixelImage {
        var colors: [Color] = []
        var rgbValues: [Int] = []
        colors.reserveCapacity(width * height)
        rgbValues.reserveCapacity(width * height)

        for y in 0..<height {
            for x in 0..<width {
                let value: Int
                if x < width / 4 {
                    value = 0xff0000
                } else if x < width / 2 {
                    value = 0x00ff00
                } else if x < width * 3 / 4 {
                    value = 0x0000ff
                } else {
                    value = ((x + y) % 2 == 0) ? 0xffffff : 0x000000
                }
                rgbValues.append(value)
                colors.append(Color(
                    red: Double((value >> 16) & 0xff) / 255,
                    green: Double((value >> 8) & 0xff) / 255,
                    blue: Double(value & 0xff) / 255
                ))
            }
        }

        return PixelImage(width: width, height: height, colors: colors, rgbValues: rgbValues)
    }

    static func makePixelImage(from image: UIImage, cropRect: CGRect? = nil, width: Int = 64, height: Int = 16) -> PixelImage? {
        guard let cgImage = image.normalizedCGImage() else { return nil }

        let targetAspect = CGFloat(width) / CGFloat(height)
        let imageAspect = CGFloat(cgImage.width) / CGFloat(cgImage.height)
        let defaultCropRect: CGRect
        if imageAspect > targetAspect {
            let cropWidth = CGFloat(cgImage.height) * targetAspect
            defaultCropRect = CGRect(
                x: (CGFloat(cgImage.width) - cropWidth) / 2,
                y: 0,
                width: cropWidth,
                height: CGFloat(cgImage.height)
            )
        } else {
            let cropHeight = CGFloat(cgImage.width) / targetAspect
            defaultCropRect = CGRect(
                x: 0,
                y: (CGFloat(cgImage.height) - cropHeight) / 2,
                width: CGFloat(cgImage.width),
                height: cropHeight
            )
        }
        let requestedCrop = cropRect ?? defaultCropRect
        let imageBounds = CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height)
        let safeCrop = requestedCrop.integral.intersection(imageBounds)
        guard safeCrop.width > 0, safeCrop.height > 0, let cropped = cgImage.cropping(to: safeCrop) else { return nil }

        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        guard let context = CGContext(
            data: &bytes,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else {
            return nil
        }

        context.interpolationQuality = .high
        context.draw(cropped, in: CGRect(x: 0, y: 0, width: width, height: height))

        var colors: [Color] = []
        var rgbValues: [Int] = []
        colors.reserveCapacity(width * height)
        rgbValues.reserveCapacity(width * height)

        for index in stride(from: 0, to: bytes.count, by: 4) {
            let adjusted = adjustedRGB(red: bytes[index], green: bytes[index + 1], blue: bytes[index + 2])
            let r = adjusted.red
            let g = adjusted.green
            let b = adjusted.blue
            rgbValues.append((r << 16) | (g << 8) | b)
            colors.append(Color(red: Double(r) / 255, green: Double(g) / 255, blue: Double(b) / 255))
        }

        return PixelImage(width: width, height: height, colors: colors, rgbValues: rgbValues)
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
