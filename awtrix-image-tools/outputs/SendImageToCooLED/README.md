# SendImageToCooLED for iOS

SwiftUI iOS app for uploading a picked image to a CoolLEDX 64x16 Bluetooth display.

## What it does

- Scans for nearby Bluetooth LE displays.
- Connects to the CoolLEDX writable characteristic `0000fff1-0000-1000-8000-00805f9b34fb`.
- Picks an image from Photos or Files.
- Center-crops the image to the 64x16 display shape.
- Applies the same saturation and contrast boost used by the AWTRIX tools.
- Converts the image into the CoolLEDX image bitplane format.
- Sends image command chunks using the packet framing from `NunoMiguelVeloso/coolledux-driver`.

## Use

1. Open `SendImageToCooLED.xcodeproj` in Xcode.
2. Pick your Apple developer team in Signing & Capabilities if Xcode asks.
3. Run on an iPhone or iPad with Bluetooth enabled.
4. Tap Scan, choose the CoolLEDX display, choose an image, then tap Upload to Display.

The app needs Bluetooth and photo-library permissions. The app shown on the device is `SendImageToCooLED`.
