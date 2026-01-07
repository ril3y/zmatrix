# ColorLight Protocol Reverse Engineering Notes
# Updated: $(date)

## Overview
- **CLTDevice.dll** - Device configuration, file parsing, protocol building
- **CLTNic.dll** - Raw ethernet via WinPcap, screen rendering

---

## Network Layer

### Ethernet Frame
```
Offset  Size  Field               Value
------  ----  -----               -----
0x00    6     Dst MAC             11:22:33:44:55:66
0x06    6     Src MAC             22:22:33:44:55:66
0x0C    2     EtherType           0x0880 (ColorLight)
0x0E    16    Controller Address  From receiver discovery (zeros if none)
0x1E    8     Sync Pattern        55 66 11 22 33 44 55 66
0x26    1     Packet Type         0x03, 0x05, 0x07, 0x0A, etc
0x27+   var   Payload             Type-specific data
```

### Controller Address (bytes 0x0E-0x1D)
- Initialized to zeros
- Populated from receiver discovery response
- Passed as parameter to Nic_CreateScreen()
- Source: CLTReceiverDetectAll / CLTReceiverDetectAndGetRcvInfo

### WinPcap Usage
- Filter: `ether dst FF:FF:FF:FF:FF:FF` (broadcast receive)
- Functions: pcap_sendqueue_alloc, pcap_sendqueue_transmit

---

## Packet Types (at offset 0x26)

| Code  | Description                    | Section Name                  |
|-------|--------------------------------|-------------------------------|
| 0x02  | Control area                   | CARDAREA                      |
| 0x03  | Routing table                  | BASICROUTE                    |
| 0x05  | Basic parameter                | BASICPARAM                    |
| 0x07  | Discovery request              | -                             |
| 0x08  | Discovery response (0x0805)    | -                             |
| 0x0A  | Brightness control             | -                             |
| 0x1B  | EEPROM parameters              | EEPROM_PARAM                  |
| 0x1F  | Void line information          | VOID_ROWCOL_PARAM             |
| 0x2B  | EEPROM parameters (alt)        | -                             |
| 0x32  | Anti-void line table           | ANTI_VOID_ROWCOL_PARAM        |
| 0x37  | T Anti routing table           | T_Anti_RouteTable             |
| 0x41  | Data remapping table           | DATA_REMAPPING_TABLE_PARAM    |
| 0x55  | Pixel data                     | -                             |
| 0x73  | Separate gamma table           | -                             |
| 0x76  | Gamma table                    | GAMATABLE                     |
| 0x7B  | Gamma calibration gray         | GAMACALIBRATION_GRAY          |
| 0x7F  | Gamma calibration delta        | GAMACALIBRATION_DELTA         |
| 0x83  | Anti routing table             | -                             |

---

## Section Indices (for file format)

| Idx  | Section Name                   |
|------|--------------------------------|
| 0x0C | CARDAREA                       |
| 0x0D | BASICROUTE                     |
| 0x0E | BASICSCAN                      |
| 0x0F | GAMATABLE                      |
| 0x10 | BASICPARAM                     |
| 0x14 | VOID_TABLE                     |
| 0x16 | SCANSCHEDULE                   |
| 0x1D | EEPROM_PARAM                   |
| 0x1E | SWITCH_FRAME_PARAM             |
| 0x1F | VOID_ROWCOL_PARAM              |
| 0x26 | ANTI_VOID_ROWCOL_PARAM         |
| 0x28 | DATA_REMAPPING_TABLE_PARAM     |

---

## Key API Functions

### CLTNic.dll Exports
```c
// Screen management (6 params: screen_id, width, height, 0, mode1, mode2)
Nic_CreateScreen(screenId, width, height, 0, mode1, mode2)
  - screenId: 1-255
  - width/height: max 0x100000 pixels each
  - mode1, mode2: 0-3 (connection style/direction?)

Nic_SetScreenSize(screenId, width, height)  // 3 params

// Brightness (6 params)  
Nic_SetBrightness(???, ???, ???, ???, ???, ???)

// Pixel data
Nic_SendScreenPicture(screenId, dataPtr)
Nic_SendScreenBlackPicture(screenId)

// Control
Nic_SenderStart(adapterName)
Nic_SenderStop()
Nic_Write(dataPtr, length)
Nic_Read(???, ???, ???, ???, ???)
```

### CLTDevice.dll Exports
```c
// Discovery
CLTDiscoveryProcessors()
CLTReceiverDetectAndGetRcvInfo(???, ???)
CLTReceiverDetectAll(???, ???, ???)

// Configuration
CLTReceiverSendCmdParam(???, ???, ???, ???, ???)  // 5 params
CLTReceiverSaveBasicParamFromFile(???, ???, ???, ???, ???)
CLTReceiverSaveBasicParamToFile(???, ???, ???, ???)

// Display control
CLTProcessorSetBrightness(???, ???, ???)  // 3 params
CLTProcessorSetScreenShowOnOrOff(???)
CLTProcessorSetTestMode(???, ???, ???)
```

---

## .rcvbp/.rcvp File Format

### Header
```
Compressed file (32-byte header):
  Offset 0x00-0x0F: File signature/magic
  Offset 0x10-0x13: Flags (0x0004 = compressed?)
  Offset 0x14-0x17: Version (0x0001 0x0701)
  Offset 0x18-0x19: Scan config (rows_per_group, scan_rate)
  Offset 0x1A-0x1F: Reserved
  Offset 0x20+:     zlib compressed data

Uncompressed file (20-byte header):
  Offset 0x00-0x13: Header
  Offset 0x14+:     Raw data chunks
```

### Scan Config Examples
```
8-scan:  0x2008 (32 rows per group, 8 scan lines)
16-scan: 0x1010 (16 rows per group, 16 scan lines)
```

### Data Chunk Format
```
Offset  Size  Field
------  ----  -----
0x00    2     Chunk length (LE)
0x02    1     Unknown
0x03    1     Type marker (0xE4 = config chunk)
0x04+   var   Chunk data
```

---

## VHDL/FPGA Code Generation

The DLL contains VHDL templates for FPGA configuration:
```vhdl
elsif x = 38 then P0_RXD <= X"02";  -- 02 = control area
elsif x = 38 then P0_RXD <= X"03";  -- 03 = routing table
elsif x = 38 then P0_RXD <= X"05";  -- 05 = basic parameter
elsif x = 38 then P0_RXD <= X"76";  -- 76 = gamma table
elsif x = 42 then P0_RXD <= X"00";  -- 00 = 8bit color
elsif x = 42 then P0_RXD <= X"02";  -- 02 = 10bit color
elsif x = 42 then P0_RXD <= X"04";  -- 04 = 12bit color
elsif x = 43 then P0_RXD <= X"02";  -- 02 = HDR mode
elsif x = 43 then P0_RXD <= X"03";  -- 03 = HLG mode
```

---

## Analysis Files Location

- Ghidra project: ~/ghidra_projects/colorlight/ColorLightRE
- IDA databases: ~/colorlight_re/*.idb
- IDA disassembly: ~/colorlight_re/*.asm
- Original binaries: C:/Program Files (x86)/ColorLight/

---

## VERIFIED .rcvbp Config Fields (Decompressed Data)

### Complete Field Map
| Offset | Size | Field | Values/Notes |
|--------|------|-------|--------------|
| 0x04 | 1 | Module Width | pixels (e.g., 32) |
| 0x05 | 1 | Module Height | pixels (e.g., 32) |
| 0x1C | 1 | Data Polarity | 0=Normal, 2=Reversed |
| 0x20 | 4 | Gamma Value | IEEE 754 float (1.0-2.8) |
| 0x24 | 1 | Scan Mode | 4/8/16/32 |
| 0x2C | 1 | White Balance Red | 0-255 (scaled from %) |
| 0x2D | 1 | White Balance Green | 0-255 (scaled from %) |
| 0x2E | 1 | White Balance Blue | 0-255 (scaled from %) |
| 0x40 | 1 | Cascade Direction | 0=R->L, 1=L->R, 2=T->B, 3=B->T |
| 0xB2 | 4 | MinOE (Brightness) | IEEE 754 float (ns) |
| 0xC4 | 2 | Cabinet Width | little-endian |
| 0xC6 | 2 | Cabinet Height | little-endian |
| 0x18E | 2 | Data Groups | 16=Normal 16 Groups |
| 0x1E9 | 2 | Grayscale Max | 16380 for 18bit+ |
| 0x25E | 1 | Grayscale Refinement | 0=off, 1=on |
| 0xE99E | 1 | Grayscale Mode | 0x07=Normal, 0x81=18bit+, 0x85=Infi-bit |
| 0xE983 | 1 | Brightness Level | 1-16 |
| 0xE986 | 1 | Decoder IC | 0x8A=138 Decoder |
| 0xE98D | 1 | Brightness % | 0-100 |
| 0xE997 | 2 | Width (dup) | little-endian |
| 0xE999 | 2 | Height (dup) | little-endian |
| 0xE9C2 | 2 | Calibration Low | RGB threshold |
| 0xE9C6 | 2 | Calibration High | RGB threshold |

### Brightness via MinOE Timing
| Brightness Level | MinOE Value |
|------------------|-------------|
| 1 | 10.80 ns |
| 4 | 40.00 ns |
| 6 | 64.77 ns |
| 8 | 86.36 ns |

Formula: MinOE (ns) ≈ Brightness_Level × 10-11 ns

### White Balance Encoding (Offsets 0x2C-0x2E)
White balance values are stored as scaled bytes (0-255) from percentage (0-100%):

| UI Percentage | Stored Value | Formula |
|---------------|--------------|---------|
| 100% | 255 | 255 × 1.00 = 255 |
| 75% | 191 | 255 × 0.75 ≈ 191 |
| 60% | 153 | 255 × 0.60 = 153 |
| 50% | 128 | 255 × 0.50 ≈ 128 |

Formula: `StoredValue = round(255 × (Percentage / 100))`

### Grayscale Mode Encoding (Offset 0xE99E)
| UI Mode | Stored Value | Binary |
|---------|--------------|--------|
| Normal | 0x07 (7) | 0000 0111 |
| 18bit+ | 0x81 (129) | 1000 0001 |
| Infi-bit | 0x85 (133) | 1000 0101 |

Note: Bit 7 (0x80) appears to indicate enhanced grayscale mode.
Bits 0-2 may encode specific mode parameters.

### Calculated Values (NOT stored)
- **Refresh Rate** - calculated from dimensions/timing
- **DCLK** - calculated from dimensions/timing

---

## BASICROUTE (0x03) Network Payload

Port routing table sent over wire. Decoded from VHDL testbench in CLTDevice.dll.

### Packet Structure
```
Offset   Size   Description
------   ----   -----------
0x00-0x0D       Ethernet header (DST+SRC MAC)
0x0C-0x0D       EtherType 0x0880
0x0E-0x1D       Controller address (16 bytes)
0x1E-0x25       Sync pattern (55 66 11 22 33 44 55 66)
0x26            Packet type = 0x03
0x27            Serial/sequence number
0x28            Reserved = 0x00
0x29+           Port routing data (3 bytes per port)
```

### Port Entry Format (3 bytes each)
```
Byte 0: Port index (0-7 for J1-J8)
Byte 1: Config flags (high)
Byte 2: Config flags (low)
```

Total: 8 ports × 3 bytes = 24 bytes of routing data

---

## Flash Write / EEPROM Save Commands

### Volatile vs Persistent Writes
| Packet Type | Operation | Persistence |
|-------------|-----------|-------------|
| 0x1B | Write EEPROM params | RAM only (volatile) |
| 0x2B | Save EEPROM params | Flash (persistent) |

### Save Command Structure (0x1A variant)
```
Offset   Value   Description
------   -----   -----------
0x26     0x1A    Packet type
0x27     0x00    Serial number
0x28     0x00    Reserved
0x29     0x00    RcvCard Index
0x2A     0x00    Reserved
0x2B     0x03    Operate Type: 0x01=Write, 0x03=Save
0x2C     0x0F    AntiRouteTable Flag (0x0F = full save)
0x2D     0x01    Send Flag
0x2E-0x2F 0x00   Reserved
0x30-0x33        Additional params (1024 byte indicator)
```

**Critical:** Use 0x2B (not 0x1B) to persist config across power cycles!

---

## Configuration Packet Sequence

Full config upload sequence (from CReceiverLayoutTool::DoSendLayout):

### Phase 1: Send Configuration (Volatile)
```
1. 0x02 (CARDAREA)     - Control area data (10 bytes/card)
2. 0x03 (BASICROUTE)   - Port routing table
3. 0x05 (BASICPARAM)   - Basic parameters
4. 0x76 (GAMATABLE)    - Gamma tables (optional)
5. 0x1B (EEPROM_PARAM) - EEPROM params (volatile)
```

### Phase 2: Persist to Flash
```
6. 0x2B (EEPROM_SAVE)  - Commit all to flash
   OR
   0x1A with OpType=0x03 - Save command
```

### Key API Functions
- `CLTReceiverSendCmdParam()` - Send single command
- `CLTReceiverGetSendCMDData()` - Get send data
- `CLTReceiverGetSaveCMDData()` - Get save data
- `CReceiverOP::DoSendCmdParamToScreenGroup()` - Send with progress

---

## Complete Packet Type Registry

| Code | Name | Description |
|------|------|-------------|
| 0x02 | CARDAREA | Control area (10 bytes/card) |
| 0x03 | BASICROUTE | Port routing table |
| 0x05 | BASICPARAM | Basic parameters |
| 0x07 | DISCOVERY | Receiver discovery request |
| 0x08 | DISCOVERY_RESP | Discovery response |
| 0x0A | BRIGHTNESS | Brightness control |
| 0x1A | ANTIROUTE_R8 | R8 Anti-RouteTable / Save cmd |
| 0x1B | EEPROM_PARAM | EEPROM params (volatile) |
| 0x1C | CHIP_REALTIME | Chip real-time params |
| 0x1F | VOID_LINE | Void line information |
| 0x2B | EEPROM_SAVE | EEPROM params (persistent) |
| 0x32 | ANTI_PIXEL | Anti pixel sequence |
| 0x37 | T_ANTIROUTE | T Anti-RouteTable |
| 0x41 | DATA_REMAP | Data remapping table |
| 0x55 | PIXEL_DATA | Pixel data stream |
| 0x73 | GAMMA_SEP | Separate gamma table |
| 0x76 | GAMATABLE | Gamma table |
| 0x7B | GAMMA_GRAY | Gamma calibration gray |
| 0x7F | GAMMA_DELTA | Gamma calibration delta |
| 0x83 | ANTI_SCAN | Anti-scan parameters |
| 0x87 | GAMMA_NEW | New gamma calibration |

---

## Next Steps

1. **Wireshark capture** - Validate packet formats against live traffic

## Brightness Packet Structure (from sub_10003460)

Total size: 93 bytes (0x5D)

### Stack Variable to Packet Mapping:
```
Var       Offset   Value        Description
-------   ------   -----        -----------
var_78    0x00     0x70 (112)   Packet length
var_74    0x02     0x70 (112)   Duplicate length
var_70    0x04     11:22:33:44  DST MAC [0:3]
var_6C    0x08     55:66:22:22  DST MAC [4:5] + SRC MAC [0:1]
var_68    0x0C     33:44:55:66  SRC MAC [2:5]
var_64    0x10     0x01         Flag
var_63    0x11     0x07         Frame type marker
var_62    0x12     (16 zeros)   Reserved
+0Ah      0x1C     0x4D ('M')   Magic marker
+0Eh      0x20     0x4D ('M')   Magic marker
var_52+2  0x22     DST MAC      Repeated
var_4C    0x26     SRC MAC      
var_48    0x2A     SRC MAC cont
var_44    0x2E     0x0A         COMMAND: Brightness
var_43-41 0x2F     MAC bytes    Controller address (3 bytes from param)
var_40    0x32     0xFF         Brightness value (0-255)
var_3F+   0x33     zeros        Padding to 93 bytes
```

### Key Fields:
- Offset 0x11: Frame type = 0x07
- Offset 0x2E: Command = 0x0A (brightness)
- Offset 0x32: Brightness value = 0x00-0xFF (0-255)

### Input Parameters (from [ebx+0x98]):
- Bytes 0-2: Controller address (goes to offset 0x2F)
- Bytes 3-6: Additional address bytes

---
## RE Session Summary

### What We Know:
1. **Ethernet Header**: DST=11:22:33:44:55:66, SRC=22:22:33:44:55:66, EtherType=0x0880
2. **Protocol Header**: 37 bytes (0x25) for pixel frames, different for config
3. **Packet Types at ~offset 0x26-0x2E**:
   - 0x0A = Brightness (confirmed)
   - 0x07 = Discovery/frame marker
   - 0x03 = Routing table
   - 0x05 = Basic params

### Brightness Packet (0x0A) - 93 bytes:
- Offset 0x11: Frame marker (0x07)
- Offset 0x2E: Command (0x0A)
- Offset 0x32: Brightness value (0-255)
- Contains controller address from parameter bytes

### Port Configuration:
- Up to 8 ports (J1-J8)
- ~1000 bytes per port config struct
- Functions: CLTProcessorVAddScreenGroupOutputPort (9616 bytes params)

### File Formats:
- .rcvp = uncompressed binary config
- .rcvbp = zlib compressed config  
- 20-32 byte headers
- Scan rate at offset 0x18

### Next Steps for Complete Protocol:
1. **Wireshark Capture** - Watch traffic while:
   - Launching LEDVISION (discovery)
   - Setting panel type
   - Setting output mapping (J1-J8)
   - Setting display size
   - Clicking "Save to Receiver"

2. **Compare captures** to RE findings to map:
   - Exact header format
   - Payload structures
   - Packet sequence

### Tools Ready:
- Ghidra: ~/ghidra_projects/colorlight/ColorLightRE
- IDA: ~/colorlight_re/*.idb
- Disassembly: ~/colorlight_re/*.asm

## Port Configuration Structure (from sub_1005E140)

### Layout:
- **ValidPortCount**: Stored at main_struct + 0x30F4 (1 byte)
- **Port Array Start**: main_struct + 0x3115
- **Port Count**: 8 maximum (J1-J8)
- **Port Struct Size**: 0x28 = 40 bytes per port

### Port Struct (40 bytes):
```
Offset  Size  Field       Description
------  ----  -----       -----------
0x00    32    GroupName   ASCII string (32 chars max)
0x20    8     GroupFlag   8-byte flags/config
```

### XML Field Names Used:
- ValidPortCount
- Port%d (Port0, Port1, etc.)
- GroupName
- GroupFlag

### Other Config Fields Found:
| Offset     | Field Name                |
|------------|---------------------------|
| +0x150F8h  | OutputWayParam           |
| +0x494Ch   | BackupStyle              |
| +0x15090h  | NetportConfig            |
| +0x150D8h  | VirtualPixState          |
| +0x150DBh  | VirtualPixTrace          |
| +0x150DCh  | VirtualPixRowOffset      |
| +0x150DDh  | VirtualPixColOffset      |
| +0x14E84h  | EnableAutoSleep          |
| +0x14E86h  | AutoSleepTime            |
| +0x15105h  | HDROnOff                 |
| +0x1508Bh  | NewHdrState              |


---

## Complete Protocol Header (Decoded from VHDL Templates)

The VHDL templates embedded in CLTDevice.dll reveal the exact byte-by-byte
protocol header format used by the receiver FPGA:

### Sync Pattern: 55 66 11 22 33 44 55 66
This 8-byte pattern at offset 0x1E-0x25 serves as frame synchronization
for the FPGA receiver logic.

---

## BASICPARAM Structure (from .rcvp file analysis)

Decoded from comparing config files with different scan rates:

### .rcvp File Header (First 0x50 bytes)
### Scan Rate Field Verification
| Config File       | Offset 0x19 | Decimal | Scan Type |
|-------------------|-------------|---------|-----------|
| four scan.rcvp    | 0x04        | 4       | 4-scan    |
| eight scan.rcvp   | 0x08        | 8       | 8-scan    |
| sixteen scan.rcvp | 0x10        | 16      | 16-scan   |
| thirty-two scan   | 0x20        | 32      | 32-scan   |

### Key Parameters for Panel Configuration
- Scan Number: Offset 0x19 (and duplicate at 0x38)
- Module Width: Offset 0x18
- Additional config: Offset 0x3B differentiates 8-scan vs others

---

## Chip-Specific Functions

The DLL supports multiple chip families with suffixed function names:
- 6618: SetScanNum6618, GetScanNum6618, SetModuleWH6618, GetModuleWH6618
- 6619: SetScanNum6619, GetScanNum6619, SetModuleWH6619, GetModuleWH6619
- Generic: SetScanNum, GetScanNum, SetModuleWH, GetModuleWH

Other per-chip APIs:
- GetGenParamBufLen, GetGenParamToBuf (gets full config buffer)
- SetBrightness, GetBrightness
- SetRefreshRate, GetRefreshRate
- SetFieldFrequence, GetFieldFrequence
- SetShiftClock, GetShiftClock
- SetGammaMode, SetGammaStep
