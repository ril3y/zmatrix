# ColorLight Protocol - Decoded Structures
# Last Updated: Session analysis of CLTDevice.dll

## Complete Protocol Header (from VHDL Templates)

The VHDL templates in CLTDevice.dll define exact byte positions:

### Full Header Layout (40+ bytes)
```
Byte  Offset  Value   Description
----  ------  -----   -----------
0-5   0x00    DST     11:22:33:44:55:66 (fixed destination MAC)
6-11  0x06    SRC     22:22:33:44:55:66 (fixed source MAC)
12-13 0x0C    Type    0x0880 (EtherType for ColorLight)
14-29 0x0E    ???     16 bytes (controller addressing - TBD)
30    0x1E    0x55    Sync pattern byte 1
31    0x1F    0x66    Sync pattern byte 2
32    0x20    0x11    Sync pattern byte 3
33    0x21    0x22    Sync pattern byte 4
34    0x22    0x33    Sync pattern byte 5
35    0x23    0x44    Sync pattern byte 6
36    0x24    0x55    Sync pattern byte 7
37    0x25    0x66    Sync pattern byte 8
38    0x26    TYPE    Packet type code
39    0x27    0x00    Serial number / sequence
40+   0x28+   DATA    Type-specific payload
```

### Sync Pattern
The sequence `55 66 11 22 33 44 55 66` at offset 0x1E-0x25 is the
frame sync marker for the receiver FPGA.

### Packet Type Codes (at offset 0x26)
- 0x02 = Control area (CARDAREA)
- 0x03 = Routing table (BASICROUTE)
- 0x05 = Basic parameter (BASICPARAM)
- 0x07 = Discovery request
- 0x0A = Brightness control
- 0x73 = Separate gamma table
- 0x76 = Gamma table (GAMATABLE)
- 0x83 = Anti routing table

---

## .rcvp File Structure (BASICPARAM)

Decoded by comparing 4/8/16/32-scan config files:

### File Header (First 0x50 bytes)
```
Offset  Size  Field           Value/Notes
------  ----  -----           -----------
0x00    16    Signature       Magic bytes / checksum
0x10    4     Flags           0x00000004 (version?)
0x14    2     Unknown         0x0001
0x16    2     Version?        0x0701
0x18    1     ModuleWidth     Width in pixels: 4, 16, 32, 64
0x19    1     ScanNumber      Scan lines: 4, 8, 16, 32
0x1A    1     Unknown         0x01 (constant)
0x1B-1F 5     Padding         0x00
0x20    1     Unknown         0x02
0x21-33 19    Padding         0x00
0x34    4     Float?          0x40333333 (2.8f in IEEE754?)
0x38    1     ScanNumber2     Duplicate of 0x19
0x39    1     Unknown         0x07
0x3A    1     Unknown         0x00
0x3B    1     Config1         0x0C=8scan, 0x0B=16/32scan
0x3C    1     Unknown         0x01
0x3D-3E 2     Config2         0x0000=8scan, 0x0019=others
0x40    4     Mask?           0x03FFFFFF
0x44    1     Config3         0x02
0x45-47 3     Variable        Scan-type dependent
0x48    1     Constant        0x32 (50)
0x49    1     Constant        0x14 (20)
0x4A-4D 4     Constant        0x2B2B2B2B ("++++" ASCII)
```

### Verified Scan Rate Values
| Config File           | Offset 0x19 | Offset 0x38 | Scan Type |
|-----------------------|-------------|-------------|-----------|
| four scan.rcvp        | 0x04        | 0x04        | 4-scan    |
| eight scan.rcvp       | 0x08        | 0x08        | 8-scan    |
| sixteen scan.rcvp     | 0x10        | 0x10        | 16-scan   |
| thirty-two scan.rcvp  | 0x20        | 0x20        | 32-scan   |

### Key Fields Summary
- **Scan Number**: Offset 0x19 (duplicated at 0x38)
- **Module Width**: Offset 0x18
- **Scan Type Indicator**: Offset 0x3B (0x0C for 8-scan, 0x0B for others)

---

## Port Configuration Structure

From sub_1005E140 analysis:

### Memory Layout
- ValidPortCount at: main_struct + 0x30F4 (1 byte, max=8)
- Port array at: main_struct + 0x3115
- Port struct size: 40 bytes (0x28) each

### Port Struct (40 bytes per port)
```
Offset  Size  Field       Type
------  ----  -----       ----
0x00    32    GroupName   ASCII string
0x20    8     GroupFlag   Flags/config bytes
```

### XML Names (from code)
- ValidPortCount
- Port0, Port1, Port2... Port7
- GroupName
- GroupFlag

---

## Chip-Specific Functions

The DLL uses suffixed function names for different chip variants:

### 6618 Series
- SetScanNum6618 / GetScanNum6618
- SetModuleWH6618 / GetModuleWH6618
- GetGenParamBufLen6618 / GetGenParamToBuf6618

### 6619 Series
- SetScanNum6619 / GetScanNum6619
- SetModuleWH6619 / GetModuleWH6619
- GetGenParamBufLen6619 / GetGenParamToBuf6619

### Generic (6660?)
- SetScanNum / GetScanNum
- SetModuleWH / GetModuleWH
- GetGenParamBufLen / GetGenParamToBuf

### Common APIs (all chips)
- SetBrightness / GetBrightness
- SetRefreshRate / GetRefreshRate
- SetFieldFrequence / GetFieldFrequence
- SetShiftClock / GetShiftClock
- SetGammaMode / SetGammaStep
- SetMaxCurrent

---

## What's Still Unknown

1. **Bytes 0x0E-0x1D** (16 bytes) - Purpose in protocol header
2. **Height field** - Not found in .rcvp; may be computed from width/scan
3. **Packet send sequence** - Order for full configuration
4. **Flash write command** - How to save config to receiver EEPROM

---

## Validation Approach

To verify these structures:
1. Capture Wireshark traffic while LEDVISION is running
2. Compare captured bytes to VHDL template offsets
3. Modify panel settings and observe byte changes
4. Compare config packet payload to .rcvp file contents
