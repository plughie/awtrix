# AWTRIX Image Tools

Utilities and phone-app source for sending cropped images to an AWTRIX 32x8 display.

## Python sender

```bash
python3 work/send_image_to_awtrix.py image.png --display 192.168.8.99
```

`--display` accepts an IP address or hostname. If omitted, the script reads `config.toml`, then `AWTRIX_IP`.
Running without an image shows help unless `--clean` is used or a config file supplies an image.

Useful options:

- `--config config.toml`: read device, animation, output, and image queue settings.
- `--center-square`: crop the center square before scaling.
- `--direction top-to-bottom|bottom-to-top|left-to-right|right-to-left`
- `--seconds 8`: seconds per animation cycle.
- `--loop`: loop until `q` or Ctrl-C, then clean up.
- `--keep-in-rotation`: save and leave the generated app in AWTRIX rotation.
- `--clean`: remove generated AWTRIX image apps and exit.

Copy `config.example.toml` to `config.toml` for local defaults. `config.toml` is ignored by git so your display address and image queue stay private.

For one configured image:

```toml
[device]
display = "awtrix.local"

[image]
path = "images/source.png"
```

For a queue:

```toml
[[images]]
path = "images/first.png"
seconds = 8
direction = "top-to-bottom"

[[images]]
path = "images/second.png"
seconds = 5
direction = "left-to-right"
center_square = true
```

Command-line options override the shared config defaults. If you pass an image path on the command line, the configured image queue is skipped.

## Phone apps

- AWTRIX iOS source: `outputs/SendImageToAWTRIX`
- AWTRIX Android source: `outputs/Send Image to AWTRIX Android`
- SendImageToCooLED iOS Bluetooth source: `outputs/SendImageToCooLED`
- SendImageToCooLED Android Bluetooth source: `outputs/SendImageToCooLED Android`

For AWTRIX iOS, open `outputs/SendImageToAWTRIX/SendImageToAWTRIX.xcodeproj`. The AWTRIX app still appears as "Send Image to AWTRIX" on the device. It can also run on Apple Silicon Macs as a "Designed for iPad/iPhone" app; select "My Mac" as the Xcode run destination.

For CooLED iOS, open `outputs/SendImageToCooLED/SendImageToCooLED.xcodeproj`.

The CoolLEDX apps target a 64x16 Bluetooth display and use the packet format from `NunoMiguelVeloso/coolledux-driver`.

Generated APK/zip artifacts and Android build outputs are ignored by git.
