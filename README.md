# ColorLight 5A-75B Linux Driver

Open-source Linux driver for the ColorLight 5A-75B LED receiver card. **No Windows or LEDVISION required!**

This project provides complete protocol documentation and a Python driver to configure and drive LED matrix panels using the ColorLight 5A-75B receiver card entirely from Linux.

## Features

- **Full Linux-only configuration** - No LEDVISION/Windows needed
- **Complete protocol documentation** - Reverse engineered from CLTDevice.dll
- **Python driver** - Display images, test patterns, configure receiver
- **Framebuffer daemon** - Use LED matrix as a Linux display
- **.rcvbp parser** - Parse existing LEDVISION config files

## Hardware

- **ColorLight 5A-75B** - LED receiver card with Lattice ECP5 FPGA
- **HUB75 LED panels** - 64x32, 32x32, etc.
- **Gigabit Ethernet** - Required for communication

## Quick Start

```bash
# Show your panel configuration
python3 colorlight.py --info

# Display test pattern (requires sudo for raw sockets)
sudo python3 colorlight.py -W 320 -H 128 -i eth0 --test

# Configure receiver (no LEDVISION needed!)
sudo python3 colorlight.py \
    --panels-x 5 --panels-y 4 \
    --panel-width 64 --panel-height 32 \
    --scan-mode 16 \
    --configure --save-flash

# Display an image
sudo python3 colorlight.py -W 320 -H 128 --image photo.png
```

## Files

| File | Description |
|------|-------------|
| `colorlight.py` | Main driver with display and config support |
| `led_daemon.py` | Framebuffer daemon for continuous display |
| `rcvbp_parser.py` | Parse LEDVISION .rcvbp config files |
| `led_helpers.py` | Helper utilities for writing to display |
| `COLORLIGHT_PROTOCOL.md` | Complete protocol specification |
| `PROTOCOL_NOTES.md` | Reverse engineering session notes |
| `DECODED_STRUCTURES.md` | Detailed structure analysis |

## Protocol Overview

The ColorLight 5A-75B uses raw Ethernet frames with two formats:

### Display Frames (Pixel Data)
```
Offset  Field
0x00    DST MAC (11:22:33:44:55:66)
0x06    SRC MAC (22:22:33:44:55:66)
0x0C    Packet Type (0x55=pixels, 0x01=display, 0x0A=brightness)
0x0D+   Payload
```

### Config Frames (Board Configuration)
```
Offset  Field
0x00    DST MAC (11:22:33:44:55:66)
0x06    SRC MAC (22:22:33:44:55:66)
0x0C    EtherType (0x0880)
0x0E    Controller Address (16 bytes)
0x1E    Sync Pattern (55 66 11 22 33 44 55 66)
0x26    Packet Type
0x27    Sequence
0x28+   Payload
```

### Key Packet Types
| Code | Name | Description |
|------|------|-------------|
| 0x02 | CARDAREA | Control area |
| 0x03 | BASICROUTE | Port routing (J1-J8) |
| 0x05 | BASICPARAM | Dimensions, scan rate |
| 0x07 | DISCOVERY | Find receivers |
| 0x0A | BRIGHTNESS | Set brightness |
| 0x2B | EEPROM_SAVE | Save to flash |
| 0x55 | PIXEL_DATA | Row pixel data (BGR) |

## Configuration Sequence

To configure a receiver without LEDVISION:

```
1. CARDAREA (0x02)     - Control area
2. BASICROUTE (0x03)   - Port routing
3. BASICPARAM (0x05)   - Dimensions, scan
4. EEPROM_PARAM (0x1B) - EEPROM params (volatile)
5. EEPROM_SAVE (0x2B)  - Save to flash (persistent!)
```

## Requirements

- Python 3.8+
- numpy
- Pillow (PIL)
- Root access (for raw sockets)

```bash
pip install numpy pillow
```

## Hardware Setup

```
┌─────────────┐     Gigabit      ┌─────────────┐     HUB75      ┌─────────────┐
│  Linux PC   │────Ethernet─────│  5A-75B     │───────────────│  LED Panels │
│  (RPi5)     │                 │  Receiver   │               │  (64x32)    │
└─────────────┘                 └─────────────┘               └─────────────┘
```

## Credits

- Protocol reverse engineering from CLTDevice.dll and CLTNic.dll
- Prior work: [chubby75](https://github.com/q3k/chubby75), [haraldkubota/colorlight](https://github.com/haraldkubota/colorlight)
- Hardware docs: [PanelPlayer](https://github.com/ZoidTechnology/PanelPlayer)

## License

MIT License - See LICENSE file
