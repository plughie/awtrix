# AWTRIX

Tools for the AWTRIX / Svitrix 32×8 LED matrix display.

## Project structure

```
awtrix/
├── awtrix-image-tools/        # Send and animate images on the display
│   ├── work/                  # Python scripts (sender, probes, tests)
│   ├── outputs/               # iOS, Android, and macOS app source
│   ├── config.example.toml    # Template config
│   └── README.md
│
└── awtrix-music-visualizer/   # Real-time audio spectrum visualizer
    ├── visualizer/            # Python package (audio, render, transport, web UI)
    ├── config.example.toml    # Template config
    ├── install_autostart.py   # Auto-start on login (macOS launchd / Windows Task Scheduler)
    ├── stop.sh                # Stop visualizer and clear the display
    ├── requirements.txt
    └── README.md
```

## Quick start

### Image tools

Send an image to the display:

```bash
cd awtrix-image-tools
cp config.example.toml config.toml   # edit with your device IP
python3 work/send_image_to_awtrix.py image.png --display 192.168.8.99
```

Supports scrolling animations, image queues, center-square cropping, and multiple scroll directions. See [awtrix-image-tools/README.md](awtrix-image-tools/README.md) for full usage.

### Music visualizer

Stream a real-time audio spectrum to the display:

```bash
cd awtrix-music-visualizer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml   # edit with your device IP and audio device
python -m visualizer
```

**macOS notes:**
- Use [Loopback](https://rogueamoeba.com/loopback/) or BlackHole for system audio capture. Set `audio.device` to the virtual device name and `audio.loopback = false`.
- Set `audio.blocksize = 512` (max supported by most virtual audio devices on macOS).

**Auto-start on login:**

```bash
python install_autostart.py            # install
python install_autostart.py --remove   # remove
```

**Stop and clear the display:**

```bash
./stop.sh
```

See [awtrix-music-visualizer/README.md](awtrix-music-visualizer/README.md) for visualization modes, color schemes, web UI, and full config reference.

## Requirements

- Python 3.11+
- Device: Ulanzi TC001 or compatible running AWTRIX 3 / Svitrix firmware
- Device and host on the same network

## License

See individual sub-project READMEs for details.
