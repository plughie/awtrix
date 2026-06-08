# AWTRIX Square Sender

Small SwiftUI iOS app for converting an image into 32x32 RGB pixels and sending it to an AWTRIX display over HTTP.

## What it does

- Picks an image from Photos or Files.
- Center-crops the image to a square.
- Downsamples it to 32x32 pixels.
- Shows a 32x32 pixel preview.
- Uploads the image as 8 saved AWTRIX apps named `sacred_square_bar_1` through `sacred_square_bar_8`.
- Runs the saved apps once in sequence.

The AWTRIX matrix is 32x8, so the app sends the 32x32 image as overlapping 32x8 windows using the same paired-bar approach as the existing Python scripts.

## Use

1. Open `AwtrixSquareSender.xcodeproj` in Xcode.
2. Pick your Apple developer team in Signing & Capabilities if Xcode asks.
3. Run on an iPhone connected to the same Wi-Fi as the AWTRIX.
4. Leave the AWTRIX IP as `192.168.8.99`, or edit it in the app.
5. Choose an image, then tap Upload and Run.

The app allows plain HTTP and local-network access in `Info.plist`.
