# Send Image to AWTRIX Android

Native Android app for cropping a picked image into AWTRIX frames and sending it over HTTP.

## What it does

- Picks an image from Android's file/photo picker.
- Lets you choose a crop rectangle.
- Scales the crop to 32 pixels wide with proportional height.
- Applies the same saturation and contrast boost used by `send_sacred_awtrix.py`.
- Displays the converted pixel preview.
- Sends the image as 32x8 display frames over 8 seconds total, repeated `/api/custom` updates to one app with `save:false`, one `/api/switch`, `/api/nextapp`, then deletion of the temporary custom app JSON and old generated prefixes.
- Optionally loops until Stop Animation is pressed.
- Lets the user enter any AWTRIX IP address.

## Defaults

- The AWTRIX IP field starts blank and is remembered after entry.
- The temporary AWTRIX app name is internal and cleaned up after each run.

## Build

This folder is intentionally dependency-free. It can be built with the Android SDK command-line tools, without Gradle.
