#!/usr/bin/env python3
"""
ColorLight .rcvbp/.rcvp Config File Parser

Parses LEDVISION configuration files to extract panel settings.
Can be used to configure receivers without Windows/LEDVISION.

Usage:
    python3 rcvbp_parser.py config.rcvbp
    python3 rcvbp_parser.py --dump config.rcvbp > config_dump.txt
"""

import argparse
import struct
import zlib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class PanelConfig:
    """Decoded panel configuration from .rcvbp file."""
    # Dimensions
    module_width: int = 0
    module_height: int = 0
    cabinet_width: int = 0
    cabinet_height: int = 0

    # Scan settings
    scan_mode: int = 0
    data_polarity: int = 0
    cascade_direction: int = 0
    data_groups: int = 0

    # Color settings
    gamma_value: float = 0.0
    white_balance_r: int = 0
    white_balance_g: int = 0
    white_balance_b: int = 0

    # Color exchange (channel remapping)
    # Values: 0=Blue, 1=Green, 2=Red (output position)
    color_exchange_r: int = 2  # Default: R outputs to position 2 (R)
    color_exchange_g: int = 1  # Default: G outputs to position 1 (G)
    color_exchange_b: int = 0  # Default: B outputs to position 0 (B)

    # Brightness
    brightness_percent: int = 0
    brightness_level: int = 0
    min_oe_ns: float = 0.0

    # Grayscale
    grayscale_mode: int = 0
    grayscale_max: int = 0
    grayscale_refinement: int = 0

    # Decoder
    decoder_ic: int = 0

    # File info
    is_compressed: bool = False
    raw_size: int = 0

    @property
    def cascade_direction_str(self) -> str:
        """Human-readable cascade direction."""
        directions = {
            0: "Right → Left",
            1: "Left → Right",
            2: "Top → Bottom",
            3: "Bottom → Top"
        }
        return directions.get(self.cascade_direction, f"Unknown ({self.cascade_direction})")

    @property
    def grayscale_mode_str(self) -> str:
        """Human-readable grayscale mode."""
        modes = {
            0x07: "Normal",
            0x81: "18bit+",
            0x85: "Infi-bit"
        }
        return modes.get(self.grayscale_mode, f"Unknown (0x{self.grayscale_mode:02X})")

    @property
    def scan_rate_str(self) -> str:
        """Human-readable scan rate."""
        return f"1:{self.scan_mode} scan"

    @property
    def color_order_str(self) -> str:
        """Human-readable color order based on exchange settings."""
        # Map position values to channel names
        pos_to_channel = {0: 'B', 1: 'G', 2: 'R'}
        # Build output order string
        r_out = pos_to_channel.get(self.color_exchange_r, '?')
        g_out = pos_to_channel.get(self.color_exchange_g, '?')
        b_out = pos_to_channel.get(self.color_exchange_b, '?')

        # Common patterns
        if (self.color_exchange_r, self.color_exchange_g, self.color_exchange_b) == (2, 1, 0):
            return "RGB (default)"
        elif (self.color_exchange_r, self.color_exchange_g, self.color_exchange_b) == (0, 1, 2):
            return "BGR (R↔B swapped)"
        elif (self.color_exchange_r, self.color_exchange_g, self.color_exchange_b) == (1, 0, 2):
            return "GRB"
        elif (self.color_exchange_r, self.color_exchange_g, self.color_exchange_b) == (1, 2, 0):
            return "GBR"
        elif (self.color_exchange_r, self.color_exchange_g, self.color_exchange_b) == (2, 0, 1):
            return "RBG"
        elif (self.color_exchange_r, self.color_exchange_g, self.color_exchange_b) == (0, 2, 1):
            return "BRG"
        else:
            return f"Custom (R→{r_out}, G→{g_out}, B→{b_out})"


def decompress_rcvbp(data: bytes) -> bytes:
    """Decompress .rcvbp file if compressed."""
    # Check for compression flag at offset 0x10
    if len(data) < 0x24:
        raise ValueError("File too small to be valid .rcvbp")

    flags = struct.unpack_from("<I", data, 0x10)[0]

    if flags & 0x0004:
        # Compressed - zlib data starts at offset 0x20
        compressed_data = data[0x20:]
        try:
            return zlib.decompress(compressed_data)
        except zlib.error as e:
            raise ValueError(f"Failed to decompress: {e}")
    else:
        # Uncompressed - data starts at offset 0x14
        return data[0x14:]


def parse_rcvbp(filepath: str) -> PanelConfig:
    """Parse a .rcvbp or .rcvp configuration file."""
    path = Path(filepath)
    raw_data = path.read_bytes()

    config = PanelConfig()
    config.raw_size = len(raw_data)

    # Check if compressed
    if len(raw_data) >= 0x14:
        flags = struct.unpack_from("<I", raw_data, 0x10)[0]
        config.is_compressed = bool(flags & 0x0004)

    # Decompress if needed
    try:
        data = decompress_rcvbp(raw_data)
    except Exception as e:
        print(f"Warning: Could not decompress, trying as raw: {e}")
        data = raw_data

    # Parse fields (offsets are into decompressed data)
    if len(data) >= 0x06:
        config.module_width = data[0x04]
        config.module_height = data[0x05]

    if len(data) >= 0x1D:
        config.data_polarity = data[0x1C]

    if len(data) >= 0x24:
        # Gamma as IEEE 754 float
        config.gamma_value = struct.unpack_from("<f", data, 0x20)[0]

    if len(data) >= 0x25:
        config.scan_mode = data[0x24]

    if len(data) >= 0x2F:
        config.white_balance_r = data[0x2C]
        config.white_balance_g = data[0x2D]
        config.white_balance_b = data[0x2E]

    if len(data) >= 0x33:
        # Color exchange (channel remapping) at offsets 0x30-0x32
        # Values: 0=Blue position, 1=Green position, 2=Red position
        config.color_exchange_r = data[0x30]
        config.color_exchange_g = data[0x31]
        config.color_exchange_b = data[0x32]

    if len(data) >= 0x41:
        config.cascade_direction = data[0x40]

    if len(data) >= 0xB6:
        # MinOE as IEEE 754 float
        config.min_oe_ns = struct.unpack_from("<f", data, 0xB2)[0]

    if len(data) >= 0xC8:
        config.cabinet_width = struct.unpack_from("<H", data, 0xC4)[0]
        config.cabinet_height = struct.unpack_from("<H", data, 0xC6)[0]

    if len(data) >= 0x190:
        config.data_groups = struct.unpack_from("<H", data, 0x18E)[0]

    if len(data) >= 0x1EB:
        config.grayscale_max = struct.unpack_from("<H", data, 0x1E9)[0]

    if len(data) >= 0x25F:
        config.grayscale_refinement = data[0x25E]

    # High offsets (may not exist in all files)
    if len(data) >= 0xE99F:
        config.grayscale_mode = data[0xE99E]

    if len(data) >= 0xE984:
        config.brightness_level = data[0xE983]

    if len(data) >= 0xE987:
        config.decoder_ic = data[0xE986]

    if len(data) >= 0xE98E:
        config.brightness_percent = data[0xE98D]

    return config


def dump_hex(data: bytes, offset: int = 0, length: int = 256) -> str:
    """Hex dump of data."""
    lines = []
    for i in range(0, min(length, len(data)), 16):
        hex_part = " ".join(f"{b:02X}" for b in data[i:i+16])
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data[i:i+16])
        lines.append(f"{offset+i:04X}: {hex_part:<48} {ascii_part}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Parse ColorLight .rcvbp config files")
    parser.add_argument("file", help="Path to .rcvbp or .rcvp file")
    parser.add_argument("--dump", action="store_true", help="Dump hex of decompressed data")
    parser.add_argument("--raw", action="store_true", help="Show raw file hex")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    try:
        config = parse_rcvbp(args.file)
    except Exception as e:
        print(f"Error parsing file: {e}")
        return 1

    if args.json:
        import json
        print(json.dumps({
            "module_width": config.module_width,
            "module_height": config.module_height,
            "cabinet_width": config.cabinet_width,
            "cabinet_height": config.cabinet_height,
            "scan_mode": config.scan_mode,
            "cascade_direction": config.cascade_direction,
            "cascade_direction_str": config.cascade_direction_str,
            "gamma_value": config.gamma_value,
            "white_balance": {
                "r": config.white_balance_r,
                "g": config.white_balance_g,
                "b": config.white_balance_b
            },
            "color_exchange": {
                "r": config.color_exchange_r,
                "g": config.color_exchange_g,
                "b": config.color_exchange_b,
                "order": config.color_order_str
            },
            "brightness_percent": config.brightness_percent,
            "brightness_level": config.brightness_level,
            "min_oe_ns": config.min_oe_ns,
            "grayscale_mode": config.grayscale_mode_str,
            "is_compressed": config.is_compressed
        }, indent=2))
        return 0

    if args.dump or args.raw:
        path = Path(args.file)
        raw_data = path.read_bytes()

        if args.raw:
            print("=== RAW FILE ===")
            print(dump_hex(raw_data, 0, len(raw_data)))

        if args.dump:
            try:
                data = decompress_rcvbp(raw_data)
                print("\n=== DECOMPRESSED DATA ===")
                print(dump_hex(data, 0, min(4096, len(data))))
            except Exception as e:
                print(f"Could not decompress: {e}")
        return 0

    # Default: human-readable output
    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║  ColorLight Panel Configuration: {Path(args.file).name:<26} ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  File Info                                                   ║")
    print(f"║    Compressed: {'Yes' if config.is_compressed else 'No':<44} ║")
    print(f"║    Raw Size: {config.raw_size:,} bytes{' '*(40-len(f'{config.raw_size:,}'))} ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Panel Dimensions                                            ║")
    print(f"║    Module: {config.module_width}×{config.module_height} pixels{' '*(43-len(f'{config.module_width}×{config.module_height}'))} ║")
    print(f"║    Cabinet: {config.cabinet_width}×{config.cabinet_height} pixels{' '*(42-len(f'{config.cabinet_width}×{config.cabinet_height}'))} ║")
    print(f"║    Scan Rate: {config.scan_rate_str:<44} ║")
    print(f"║    Cascade: {config.cascade_direction_str:<46} ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Color Settings                                              ║")
    print(f"║    Gamma: {config.gamma_value:.2f}{' '*(49-len(f'{config.gamma_value:.2f}'))} ║")
    print(f"║    White Balance: R={config.white_balance_r} G={config.white_balance_g} B={config.white_balance_b}{' '*(30-len(f'R={config.white_balance_r} G={config.white_balance_g} B={config.white_balance_b}'))} ║")
    print(f"║    Color Order: {config.color_order_str:<42} ║")
    print(f"║    Data Polarity: {'Reversed' if config.data_polarity else 'Normal':<40} ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Brightness                                                  ║")
    print(f"║    Level: {config.brightness_level}/16{' '*(47-len(f'{config.brightness_level}/16'))} ║")
    print(f"║    Percent: {config.brightness_percent}%{' '*(46-len(f'{config.brightness_percent}%'))} ║")
    print(f"║    MinOE: {config.min_oe_ns:.2f} ns{' '*(45-len(f'{config.min_oe_ns:.2f} ns'))} ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Grayscale                                                   ║")
    print(f"║    Mode: {config.grayscale_mode_str:<49} ║")
    print(f"║    Max: {config.grayscale_max}{' '*(51-len(str(config.grayscale_max)))} ║")
    print(f"║    Refinement: {'On' if config.grayscale_refinement else 'Off':<43} ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")

    return 0


if __name__ == "__main__":
    exit(main())
