# ColorLight 5A-75B Protocol Specification
# Reverse Engineered from CLTDevice.dll / CLTNic.dll
# Status: Working Draft

## Overview

The ColorLight 5A-75B receiver card uses two distinct frame formats:
1. **Display frames** - Pixel data streaming (simple format)
2. **Config frames** - Board configuration (complex format with sync pattern)

---

## Display Frame Format (Pixel Streaming)

Used for real-time pixel data. Simple format, high throughput.

```
Offset  Size  Field          Value/Description
──────  ────  ─────          ─────────────────
0x00    6     DST MAC        11:22:33:44:55:66
0x06    6     SRC MAC        22:22:33:44:55:66
0x0C    1     Packet Type    0x01, 0x0A, or 0x55
0x0D+   var   Payload        Type-specific data
```

### Display Packet Types (offset 0x0C)

| Type | Name | Description |
|------|------|-------------|
| 0x01 | Display Frame | Triggers refresh, contains brightness |
| 0x0A | Brightness | Set display brightness (0-255) |
| 0x55 | Pixel Data | Row pixel data in BGR format |

### Pixel Data Packet (0x55)
```
Offset  Size  Field          Description
──────  ────  ─────          ───────────
0x0C    1     Type           0x55
0x0D    2     Row Number     Big-endian row index
0x0F    2     Pixel Offset   Horizontal offset (for wide displays)
0x11    2     Pixel Count    Number of pixels in packet
0x13    1     Fixed          0x08
0x14    1     Fixed          0x88
0x15+   var   Pixel Data     BGR format, 3 bytes per pixel
```

Max 497 pixels per packet (to fit in ethernet MTU).

---

## Config Frame Format (Board Configuration)

Used for discovery, panel setup, routing, gamma tables, etc.

```
Offset  Size  Field          Value/Description
──────  ────  ─────          ─────────────────
0x00    6     DST MAC        11:22:33:44:55:66
0x06    6     SRC MAC        22:22:33:44:55:66
0x0C    2     EtherType      0x0880 (ColorLight config)
0x0E    16    Controller     Controller addressing (see below)
0x1E    8     SYNC           55:66:11:22:33:44:55:66 (FPGA sync marker)
0x26    1     Packet Type    Config packet type code
0x27    1     Sequence       Packet sequence number
0x28+   var   Payload        Type-specific configuration data
```

### The Sync Pattern
The 8-byte sequence `55 66 11 22 33 44 55 66` at offset 0x1E is critical.
The FPGA firmware uses this to locate the packet type byte.

### Config Packet Types (offset 0x26)

| Type | Section Name | Description |
|------|--------------|-------------|
| 0x02 | CARDAREA | Control area / card boundaries |
| 0x03 | BASICROUTE | Routing table - J1-J8 port mapping |
| 0x05 | BASICPARAM | Basic parameters - dimensions, scan rate |
| 0x07 | - | Discovery request |
| 0x08 | - | Discovery response |
| 0x0A | - | Brightness control (config format) |
| 0x1B | EEPROM_PARAM | EEPROM parameters |
| 0x1F | VOID_ROWCOL_PARAM | Void line information |
| 0x2B | - | EEPROM parameters (alternate) |
| 0x32 | ANTI_VOID_ROWCOL_PARAM | Anti-void line table |
| 0x37 | T_Anti_RouteTable | T Anti routing table |
| 0x41 | DATA_REMAPPING_TABLE_PARAM | Data remapping table |
| 0x73 | - | Separate gamma table |
| 0x76 | GAMATABLE | Gamma table |
| 0x7B | GAMACALIBRATION_GRAY | Gamma calibration gray |
| 0x7F | GAMACALIBRATION_DELTA | Gamma calibration delta |
| 0x83 | - | Anti routing table |

---

## Controller Addressing (Offset 0x0E-0x1D)

16 bytes for controller/receiver addressing. Structure TBD.
May contain:
- Controller ID (0-255)
- Receiver card address
- Screen ID

---

## Brightness Config Packet (0x0A) - DECODED

Full structure for config-style brightness control:

```
Offset  Size  Field          Value/Description
──────  ────  ─────          ─────────────────
0x00    6     DST MAC        11:22:33:44:55:66
0x06    6     SRC MAC        22:22:33:44:55:66
0x0C    2     EtherType      0x0880
0x0E    16    Controller     Addressing bytes
0x1E    8     SYNC           55:66:11:22:33:44:55:66
0x26    1     Type           0x0A
0x27    3     Ctrl Addr      Controller address (from discovery)
0x2A    1     Brightness     0x00-0xFF (0-255)
0x2B+   var   Padding        Zero padding to 93 bytes total
```

---

## Port Configuration Structure

Each output port (J1-J8) has a 40-byte config structure:

```
Offset  Size  Field          Description
──────  ────  ─────          ───────────
0x00    32    GroupName      ASCII string identifier
0x20    8     GroupFlag      Configuration flags
```

- Maximum 8 ports (J1-J8)
- ValidPortCount stored at main_struct + 0x30F4
- Port array starts at main_struct + 0x3115

---

## .rcvp File Format (Panel Configuration)

Binary configuration file used by LEDVISION.

### Header (0x50 bytes)
```
Offset  Size  Field          Value/Description
──────  ────  ─────          ─────────────────
0x00    16    Signature      Magic bytes / file ID
0x10    4     Flags          0x00000004 (version indicator?)
0x14    2     Unknown        0x0001
0x16    2     Version        0x0701
0x18    1     ModuleWidth    Panel width: 4, 16, 32, 64 pixels
0x19    1     ScanNumber     Scan lines: 4, 8, 16, 32
0x1A    1     Unknown        0x01
0x1B-1F 5     Reserved       0x00
0x20    1     Unknown        0x02
0x21-33 19    Reserved       0x00
0x34    4     Float          IEEE754 float (timing related?)
0x38    1     ScanNumber2    Duplicate of scan number
0x39    1     Unknown        0x07
0x3A    1     Unknown        0x00
0x3B    1     ScanTypeFlag   0x0C=8-scan, 0x0B=others
0x3C    1     Unknown        0x01
0x3D-3E 2     Config2        0x0000=8-scan, 0x0019=others
0x40    4     Mask           0x03FFFFFF
0x44    1     Config3        0x02
0x45-47 3     Variable       Scan-type dependent
0x48    1     Constant       0x32 (50)
0x49    1     Constant       0x14 (20)
0x4A-4D 4     Marker         0x2B2B2B2B ("++++" ASCII)
```

### Scan Rate Values
| File Type | Offset 0x19 | Offset 0x38 | Scan Type |
|-----------|-------------|-------------|-----------|
| 4-scan    | 0x04        | 0x04        | 1:4       |
| 8-scan    | 0x08        | 0x08        | 1:8       |
| 16-scan   | 0x10        | 0x10        | 1:16      |
| 32-scan   | 0x20        | 0x20        | 1:32      |

### Compressed Format (.rcvbp)
- 32-byte header with zlib compressed data at offset 0x20
- Offset 0x10-0x13: Flags (0x0004 = compressed)

---

## Chip Variants

The protocol supports multiple LED driver chip families:

### Chip-Specific Functions
| Chip | Scan Function | Module Function |
|------|---------------|-----------------|
| 6618 | SetScanNum6618 | SetModuleWH6618 |
| 6619 | SetScanNum6619 | SetModuleWH6619 |
| Generic | SetScanNum | SetModuleWH |

### Common APIs (all chips)
- SetBrightness / GetBrightness
- SetRefreshRate / GetRefreshRate
- SetFieldFrequence / GetFieldFrequence
- SetShiftClock / GetShiftClock
- SetGammaMode / SetGammaStep
- SetMaxCurrent

---

## Key DLL Exports

### CLTNic.dll (Network Layer)
```c
Nic_CreateScreen(screenId, width, height, 0, mode1, mode2)
Nic_SetScreenSize(screenId, width, height)
Nic_SetBrightness(6 params)
Nic_SendScreenPicture(screenId, dataPtr)
Nic_SendScreenBlackPicture(screenId)
Nic_SenderStart(adapterName)
Nic_SenderStop()
Nic_Write(dataPtr, length)
Nic_Read(5 params)
```

### CLTDevice.dll (Config Layer)
```c
CLTDiscoveryProcessors()
CLTReceiverDetectAndGetRcvInfo(2 params)
CLTReceiverDetectAll(3 params)
CLTReceiverSendCmdParam(5 params)
CLTReceiverSaveBasicParamFromFile(5 params)
CLTReceiverSaveBasicParamToFile(4 params)
CLTProcessorSetBrightness(3 params)
CLTProcessorSetScreenShowOnOrOff(1 param)
CLTProcessorSetTestMode(3 params)
```

---

## Controller Address (0x0E-0x1D) - DECODED

The 16-byte controller address field:
- Initialized to zeros for broadcast
- Populated from discovery response (packet type 0x08)
- Used by `Nic_CreateScreen()` to target specific receiver
- For single-receiver setups, zeros work fine

---

## .rcvbp Decompressed Config Structure - FULLY DECODED

The decompressed .rcvbp file contains the complete receiver configuration:

### Panel Dimensions & Scan
| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| 0x04 | 1 | Module Width | pixels (32, 64) |
| 0x05 | 1 | Module Height | pixels (32, 64) |
| 0x24 | 1 | Scan Mode | 4, 8, 16, or 32 |
| 0xC4 | 2 | Cabinet Width | uint16 LE |
| 0xC6 | 2 | Cabinet Height | uint16 LE |

### Cascade Direction (Critical for panel chaining!)
| Offset | Size | Field | Values |
|--------|------|-------|--------|
| 0x40 | 1 | Cascade Direction | 0=R→L, 1=L→R, 2=T→B, 3=B→T |

### Color & Brightness
| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| 0x1C | 1 | Data Polarity | 0=Normal, 2=Reversed |
| 0x20 | 4 | Gamma Value | IEEE 754 float (1.0-2.8) |
| 0x2C | 1 | White Balance Red | 0-255 (scaled from %) |
| 0x2D | 1 | White Balance Green | 0-255 |
| 0x2E | 1 | White Balance Blue | 0-255 |
| 0xB2 | 4 | MinOE (Brightness) | IEEE 754 float (ns) |
| 0xE98D | 1 | Brightness % | 0-100 |
| 0xE983 | 1 | Brightness Level | 1-16 |

### Advanced Settings
| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| 0x18E | 2 | Data Groups | 16=Normal |
| 0x1E9 | 2 | Grayscale Max | 16380 for 18bit+ |
| 0x25E | 1 | Grayscale Refinement | 0=off, 1=on |
| 0xE99E | 1 | Grayscale Mode | 0x07=Normal, 0x81=18bit+, 0x85=Infi-bit |
| 0xE986 | 1 | Decoder IC | 0x8A=138 Decoder |

### Brightness Timing Formula
MinOE (ns) ≈ Brightness_Level × 10-11 ns

| Level | MinOE |
|-------|-------|
| 1 | 10.80 ns |
| 4 | 40.00 ns |
| 8 | 86.36 ns |

### White Balance Formula
`StoredValue = round(255 × (Percentage / 100))`

---

## Port Configuration Structure

Each output port (J1-J8) has a 40-byte config:

```
Offset  Size  Field       Description
0x00    32    GroupName   ASCII string identifier
0x20    8     GroupFlag   Configuration flags
```

Storage in main struct:
- ValidPortCount: offset 0x30F4
- Port array: offset 0x3115
- Max 8 ports

---

## Still Unknown

1. **BASICROUTE network payload** - How port mapping sent over ethernet
2. **Flash write command** - How to persist config to receiver EEPROM
3. **Packet send sequence** - Order of config packets for full setup

---

## Validation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Display packets (0x55) | ✅ Verified | Working in multiple projects |
| Sync pattern | ✅ Verified | From VHDL templates |
| Brightness (display) | ✅ Verified | Simple format works |
| Brightness (config) | 🟡 Decoded | Needs testing |
| Basic params | 🟡 Partial | .rcvp structure known |
| Routing table | ❌ Unknown | Need payload format |
| Port config | 🟡 Partial | 40-byte struct, need details |

---

## References

- RE Analysis: CLTDevice.dll, CLTNic.dll (Ghidra/IDA)
- VHDL templates embedded in CLTDevice.dll
- .rcvp file comparison (4/8/16/32-scan configs)
- Prior work: chubby75, haraldkubota/colorlight, PanelPlayer
