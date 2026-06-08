# Send Image to AWTRIX

Small SwiftUI iOS app for cropping an image, scaling it to 32 pixels wide, and sending it to an AWTRIX display over HTTP.

## What it does

- Picks an image from Photos or Files.
- Lets you choose a crop rectangle.
- Scales the crop to 32 pixels wide with proportional height.
- Shows the converted pixel preview.
- Optionally loops until Stop Animation is pressed.
- Streams the image as one temporary AWTRIX custom app.
- Runs 4 vertical 32x8 display frames over 8 seconds total, then returns to the next app.

The AWTRIX matrix is 32x8, so the app splits the converted image into 32x8 slices. It repeatedly posts those frames to one `/api/custom` app with `save:false`, switches once with `/api/switch`, advances with `/api/nextapp`, waits briefly, then deletes the temporary custom app JSON and old generated prefixes. If looping is enabled, it keeps posting the frame sequence until stopped.

The temporary AWTRIX app name is internal and cleaned up after each run.

## Use

1. Open `Send Image to AWTRIX.xcodeproj` in Xcode.
2. Pick your Apple developer team in Signing & Capabilities if Xcode asks.
3. Run on an iPhone connected to the same Wi-Fi as the AWTRIX.
4. Enter the IP address of your AWTRIX display.
5. Choose an image, then tap Upload and Run.

The app allows plain HTTP and local-network access in `Info.plist`.
