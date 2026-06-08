# AWTRIX Image Tools

Utilities and phone-app source for sending cropped images to an AWTRIX 32x8 display.

## Python sender

```bash
python3 work/send_image_to_awtrix.py image.png --display 192.168.8.99
```

`--display` accepts an IP address or hostname. If omitted, the script reads `AWTRIX_IP`.

Useful options:

- `--center-square`: crop the center square before scaling.
- `--direction top-to-bottom|bottom-to-top|left-to-right|right-to-left`
- `--seconds 8`: seconds per animation cycle.
- `--loop`: loop until `q` or Ctrl-C, then clean up.
- `--keep-in-rotation`: save and leave the generated app in AWTRIX rotation.
- `--clean`: remove generated AWTRIX image apps and exit.

## Phone apps

- iOS source: `outputs/Send Image to AWTRIX`
- Android source: `outputs/Send Image to AWTRIX Android`

Generated APK/zip artifacts and Android build outputs are ignored by git.

