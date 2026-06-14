# SendImageToCooLED Android

Native Android app for uploading a picked image to a CoolLEDX 64x16 Bluetooth display.

## What it does

- Requests Bluetooth scan/connect permission.
- Scans for nearby Bluetooth LE devices.
- Connects to the CoolLEDX writable characteristic `0000fff1-0000-1000-8000-00805f9b34fb`.
- Picks an image from Android's file/photo picker.
- Center-crops the image to the 64x16 display shape.
- Applies the same saturation and contrast boost used by the AWTRIX tools.
- Converts the image into the CoolLEDX image bitplane format.
- Sends image command chunks using the packet framing from `NunoMiguelVeloso/coolledux-driver`.

## Build

This folder is intentionally dependency-free. It can be built with the Android SDK command-line tools, without Gradle:

```bash
./build_apk.sh
```

The generated APK is written next to this folder as `SendImageToCooLED Android.apk`.
