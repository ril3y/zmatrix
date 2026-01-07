"""
ColorLight 5A-75B LED Matrix Driver

Protocol implementation for driving LED panels via ColorLight 5A-75B receiver card.
Uses raw ethernet sockets for high performance.

Protocol Reference: Reverse engineered from CLTDevice.dll / CLTNic.dll

═══════════════════════════════════════════════════════════════════════════════
FRAME FORMATS
═══════════════════════════════════════════════════════════════════════════════

Display Data Frame (pixel streaming):
  Offset  Size  Field
  0x00    6     Dst MAC             11:22:33:44:55:66
  0x06    6     Src MAC             22:22:33:44:55:66
  0x0C    1     Packet Type         0x55 (pixel data), 0x01 (display), 0x0A (brightness)
  0x0D+   var   Payload             Type-specific

Config Frame (board configuration):
  Offset  Size  Field
  0x00    6     Dst MAC             11:22:33:44:55:66
  0x06    6     Src MAC             22:22:33:44:55:66
  0x0C    2     EtherType           0x0880 (ColorLight config)
  0x0E    24    Protocol Header     (sequence, receiver ID, etc.)
  0x26    1     Packet Type         0x03 (routing), 0x05 (params), etc.
  0x27+   var   Payload             Type-specific

═══════════════════════════════════════════════════════════════════════════════
PACKET TYPES
═══════════════════════════════════════════════════════════════════════════════

Display packets (offset 0x0C):
  0x01 - Display frame (refresh trigger, brightness)
  0x0A - Brightness control
  0x55 - Pixel row data (BGR format)

Config packets (offset 0x26, EtherType 0x0880):
  0x02 - Control area (CARDAREA)
  0x03 - Routing table (BASICROUTE) - J1-J8 port mapping
  0x05 - Basic parameter (BASICPARAM) - dimensions, scan rate
  0x07 - Discovery request
  0x08 - Discovery response
  0x1B - EEPROM parameters
  0x1F - Void line information
  0x41 - Data remapping table
  0x76 - Gamma table (GAMATABLE)

Color depth (offset 0x2A in config packets):
  0x00 - 8-bit color
  0x02 - 10-bit color
  0x04 - 12-bit color

HDR mode (offset 0x2B in config packets):
  0x02 - HDR mode
  0x03 - HLG mode
"""

import socket
import struct
import time
from typing import Optional

import numpy as np
from PIL import Image


class ColorLight5A75B:
    """
    Driver for ColorLight 5A-75B LED receiver card.

    The 5A-75B must be pre-configured with LEDVISION software to match
    your physical panel layout. This driver just sends pixel data.
    """

    # Fixed MAC addresses (hardcoded in ColorLight protocol)
    SRC_MAC = bytes.fromhex("222233445566")
    DST_MAC = bytes.fromhex("112233445566")

    # EtherType for config packets
    ETHERTYPE_CONFIG = 0x0880

    # FPGA Sync Pattern (offset 0x1E-0x25 in config packets)
    # The receiver FPGA looks for this to locate packet type
    SYNC_PATTERN = bytes([0x55, 0x66, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66])

    # Display packet types (at offset 0x0C, no EtherType)
    PKT_DISPLAY = 0x01   # Display frame / refresh trigger
    PKT_BRIGHTNESS = 0x0A  # Brightness control
    PKT_IMAGE = 0x55     # Row pixel data

    # Config packet types (at offset 0x26, with EtherType 0x0880)
    CFG_CONTROL_AREA = 0x02      # CARDAREA - control area (10 bytes/card)
    CFG_ROUTING = 0x03           # BASICROUTE - port mapping (3 bytes/port)
    CFG_BASIC_PARAM = 0x05       # BASICPARAM - dimensions, scan
    CFG_DISCOVERY_REQ = 0x07     # Discovery request
    CFG_DISCOVERY_RSP = 0x08     # Discovery response
    CFG_BRIGHTNESS = 0x0A        # Brightness control
    CFG_ANTIROUTE_SAVE = 0x1A    # Anti-route / Save command
    CFG_EEPROM_VOLATILE = 0x1B   # EEPROM params (RAM only - volatile!)
    CFG_CHIP_REALTIME = 0x1C     # Chip real-time params
    CFG_VOID_LINE = 0x1F         # Void line info
    CFG_EEPROM_PERSIST = 0x2B    # EEPROM params (FLASH - persistent!)
    CFG_ANTI_PIXEL = 0x32        # Anti pixel sequence
    CFG_T_ANTIROUTE = 0x37       # T Anti-route table
    CFG_DATA_REMAP = 0x41        # Data remapping table
    CFG_GAMMA_SEP = 0x73         # Separate gamma table
    CFG_GAMMA = 0x76             # Gamma table
    CFG_GAMMA_GRAY = 0x7B        # Gamma calibration gray
    CFG_GAMMA_DELTA = 0x7F       # Gamma calibration delta
    CFG_ANTI_SCAN = 0x83         # Anti-scan parameters
    CFG_GAMMA_NEW = 0x87         # New gamma calibration

    # Color depth values (offset 0x2A in config)
    COLOR_8BIT = 0x00
    COLOR_10BIT = 0x02
    COLOR_12BIT = 0x04

    # Protocol limits
    MAX_PIXELS_PER_PACKET = 497  # Stay within ethernet MTU
    CONFIG_HEADER_SIZE = 40      # Full config header (MAC+EtherType+Ctrl+Sync+Type+Seq)

    # Color order presets (maps input RGB to output channel positions)
    # Format: [R_out_pos, G_out_pos, B_out_pos] where 0=B, 1=G, 2=R in BGR output
    COLOR_ORDERS = {
        'RGB': [2, 1, 0],  # R→R(2), G→G(1), B→B(0) - standard
        'RBG': [2, 0, 1],  # R→R(2), G→B(0), B→G(1)
        'GRB': [1, 2, 0],  # R→G(1), G→R(2), B→B(0)
        'GBR': [1, 0, 2],  # R→G(1), G→B(0), B→R(2)
        'BRG': [0, 2, 1],  # R→B(0), G→R(2), B→G(1)
        'BGR': [0, 1, 2],  # R→B(0), G→G(1), B→R(2)
    }

    def __init__(self, width: int, height: int, interface: str = "eth0",
                 color_order: str = "BGR"):
        """
        Initialize the ColorLight driver.

        Args:
            width: Total display width in pixels
            height: Total display height in pixels
            interface: Network interface name (e.g., "eth0", "enp1s0")
            color_order: Panel color order - 'RGB', 'BGR', 'GRB', 'RBG', 'BRG', 'GBR'
        """
        self.width = width
        self.height = height
        self.interface = interface
        self.socket: Optional[socket.socket] = None
        self.brightness = 255  # 0-255
        self.rgb_brightness = (255, 255, 255)  # Per-channel brightness

        # Color order for panel (default BGR - most common)
        self.set_color_order(color_order)

        # Framebuffer (RGB format, will convert based on color_order when sending)
        self.framebuffer = np.zeros((height, width, 3), dtype=np.uint8)

    def set_color_order(self, order: str):
        """
        Set the color channel order for the panel.

        Args:
            order: One of 'RGB', 'BGR', 'GRB', 'RBG', 'BRG', 'GBR'

        Different LED panels have different color channel orderings depending
        on the LED driver IC used. If colors appear swapped, try different orders.
        """
        order = order.upper()
        if order not in self.COLOR_ORDERS:
            raise ValueError(f"Invalid color order '{order}'. Must be one of: {list(self.COLOR_ORDERS.keys())}")
        self.color_order = order
        self._color_map = self.COLOR_ORDERS[order]

    def open(self):
        """Open raw ethernet socket."""
        try:
            # AF_PACKET for raw ethernet, SOCK_RAW for raw frames
            self.socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
            self.socket.bind((self.interface, 0))
            print(f"Opened raw socket on {self.interface}")
        except PermissionError:
            raise PermissionError(
                "Raw socket requires root privileges. Run with sudo or add CAP_NET_RAW capability."
            )

    def close(self):
        """Close the socket."""
        if self.socket:
            self.socket.close()
            self.socket = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _send_packet(self, packet_type: int, payload: bytes):
        """
        Send a display packet (simple format).

        Format: DST_MAC(6) + SRC_MAC(6) + TYPE(1) + PAYLOAD(N)
        """
        if not self.socket:
            raise RuntimeError("Socket not open. Call open() first or use context manager.")

        frame = self.DST_MAC + self.SRC_MAC + bytes([packet_type]) + payload
        self.socket.send(frame)

    def _send_config_packet(self, packet_type: int, payload: bytes,
                            controller_addr: bytes = None, sequence: int = 0):
        """
        Send a config packet (complex format with sync pattern).

        Format:
          0x00-0x05: DST MAC
          0x06-0x0B: SRC MAC
          0x0C-0x0D: EtherType (0x0880)
          0x0E-0x1D: Controller addressing (16 bytes)
          0x1E-0x25: Sync pattern (55:66:11:22:33:44:55:66)
          0x26:      Packet type
          0x27:      Sequence number
          0x28+:     Payload
        """
        if not self.socket:
            raise RuntimeError("Socket not open. Call open() first or use context manager.")

        # Default controller address (16 bytes of zeros)
        if controller_addr is None:
            controller_addr = bytes(16)
        elif len(controller_addr) < 16:
            controller_addr = controller_addr + bytes(16 - len(controller_addr))

        # Build config frame
        frame = bytearray()
        frame.extend(self.DST_MAC)                              # 0x00-0x05
        frame.extend(self.SRC_MAC)                              # 0x06-0x0B
        frame.extend(struct.pack(">H", self.ETHERTYPE_CONFIG))  # 0x0C-0x0D (0x0880)
        frame.extend(controller_addr[:16])                      # 0x0E-0x1D
        frame.extend(self.SYNC_PATTERN)                         # 0x1E-0x25
        frame.append(packet_type)                               # 0x26
        frame.append(sequence & 0xFF)                           # 0x27
        frame.extend(payload)                                   # 0x28+

        self.socket.send(bytes(frame))

    def send_discovery(self):
        """
        Send discovery request to find connected receiver cards.

        Returns responses via receive (not implemented yet).
        """
        # Discovery request is packet type 0x07 with empty payload
        self._send_config_packet(self.CFG_DISCOVERY_REQ, bytes(64))

    def send_port_routing(self, port_config: list):
        """
        Send port routing table (BASICROUTE 0x03).

        Args:
            port_config: List of tuples [(port_index, flags_high, flags_low), ...]
                         Max 8 ports (J1-J8), 3 bytes each

        Example:
            driver.send_port_routing([
                (0, 0x00, 0x01),  # J1 enabled
                (1, 0x00, 0x01),  # J2 enabled
            ])
        """
        # Build routing payload: 1 byte reserved + 3 bytes per port
        payload = bytearray([0x00])  # Reserved byte at 0x28

        for port_idx, flags_hi, flags_lo in port_config[:8]:
            payload.append(port_idx & 0x07)
            payload.append(flags_hi & 0xFF)
            payload.append(flags_lo & 0xFF)

        # Pad to 25 bytes (1 reserved + 8 ports × 3 bytes)
        while len(payload) < 25:
            payload.append(0x00)

        self._send_config_packet(self.CFG_ROUTING, bytes(payload))

    def send_control_area(self, card_index: int = 0, area_data: bytes = None):
        """
        Send control area configuration (CARDAREA 0x02).

        Args:
            card_index: Receiver card index (0-255)
            area_data: 10 bytes of control area data
        """
        if area_data is None:
            area_data = bytes(10)

        payload = bytearray([0x00])  # Reserved
        payload.append(card_index & 0xFF)
        payload.extend(area_data[:10])

        self._send_config_packet(self.CFG_CONTROL_AREA, bytes(payload))

    def send_basic_params(self, width: int, height: int, scan_mode: int = 16,
                          color_depth: int = 0, module_w: int = 64, module_h: int = 32):
        """
        Send basic parameters (BASICPARAM 0x05).

        Args:
            width: Total display width
            height: Total display height
            scan_mode: Scan rate (4, 8, 16, 32)
            color_depth: 0=8bit, 2=10bit, 4=12bit
            module_w: Single module width
            module_h: Single module height
        """
        payload = bytearray(32)

        # Width/height at offset 0-3 (in payload, after header)
        payload[0] = width & 0xFF
        payload[1] = (width >> 8) & 0xFF
        payload[2] = height & 0xFF
        payload[3] = (height >> 8) & 0xFF

        # Color depth at offset 4 (maps to 0x2A in full packet)
        payload[4] = color_depth & 0xFF

        # Module dimensions
        payload[6] = module_w & 0xFF
        payload[7] = module_h & 0xFF

        # Scan mode
        payload[8] = scan_mode & 0xFF

        self._send_config_packet(self.CFG_BASIC_PARAM, bytes(payload))

    def save_to_flash(self):
        """
        Save current configuration to receiver's flash memory.

        CRITICAL: This persists config across power cycles!
        Uses packet type 0x2B (EEPROM_PERSIST).
        """
        # Full save payload
        payload = bytearray(16)
        payload[0] = 0x0F  # Full save flag
        payload[1] = 0x01  # Send flag

        self._send_config_packet(self.CFG_EEPROM_PERSIST, bytes(payload))
        print("Config saved to flash!")

    def configure_receiver(self, width: int, height: int,
                           scan_mode: int = 16, ports: list = None,
                           save: bool = False):
        """
        Full receiver configuration sequence.

        Args:
            width: Total display width
            height: Total display height
            scan_mode: Scan rate (4, 8, 16, 32)
            ports: List of port configs [(idx, flags_hi, flags_lo), ...]
            save: If True, persist to flash (survives power cycle)

        Config sequence:
            1. CARDAREA (0x02) - Control area
            2. BASICROUTE (0x03) - Port routing
            3. BASICPARAM (0x05) - Basic params
            4. EEPROM_VOLATILE (0x1B) - EEPROM params
            5. EEPROM_PERSIST (0x2B) - Save to flash (if save=True)
        """
        print(f"Configuring receiver: {width}x{height}, {scan_mode}-scan")

        # Phase 1: Send config (volatile)
        time.sleep(0.01)
        self.send_control_area()

        time.sleep(0.01)
        if ports:
            self.send_port_routing(ports)
        else:
            # Default: enable all 8 ports
            default_ports = [(i, 0x00, 0x01) for i in range(8)]
            self.send_port_routing(default_ports)

        time.sleep(0.01)
        self.send_basic_params(width, height, scan_mode)

        time.sleep(0.01)
        self._send_config_packet(self.CFG_EEPROM_VOLATILE, bytes(16))

        # Phase 2: Persist to flash (if requested)
        if save:
            time.sleep(0.05)  # Wait for volatile writes to complete
            self.save_to_flash()
        else:
            print("Config sent (volatile - will be lost on power cycle)")
            print("Use save=True to persist to flash")

    def send_display_frame(self):
        """
        Send display frame packet (0x01).

        This triggers the display to show the buffered image data.
        Should be sent after all row data, with ~5ms delay after last row.

        Packet structure (98 bytes after type):
          Byte 0:     0x07 (fixed)
          Bytes 1-21: Padding (zeros)
          Byte 22:    Overall brightness (0-255, linear)
          Byte 23:    0x05 (fixed)
          Byte 24:    0x00 (fixed)
          Bytes 25-27: RGB brightness (linear)
          Rest:       Padding (zeros)
        """
        payload = bytearray(98)
        payload[0] = 0x07
        # Bytes 1-21 are padding (already zeros)
        payload[22] = self.brightness
        payload[23] = 0x05
        payload[24] = 0x00
        payload[25] = self.rgb_brightness[0]  # R
        payload[26] = self.rgb_brightness[1]  # G
        payload[27] = self.rgb_brightness[2]  # B
        # Rest is padding (already zeros)

        self._send_packet(self.PKT_DISPLAY, bytes(payload))

    def send_brightness(self, brightness: int = None, rgb: tuple = None):
        """
        Send brightness control packet (0x0A).

        This packet is optional - brightness can also be set in display frame.

        Args:
            brightness: Overall brightness 0-255 (non-linear)
            rgb: Per-channel brightness tuple (R, G, B)

        Packet structure (63 bytes after type):
          Bytes 0-2: RGB brightness (non-linear)
          Byte 3:    0xFF (fixed)
          Rest:      Padding (zeros)
        """
        if brightness is not None:
            self.brightness = max(0, min(255, brightness))
        if rgb is not None:
            self.rgb_brightness = tuple(max(0, min(255, c)) for c in rgb)

        payload = bytearray(63)
        payload[0] = self.rgb_brightness[0]  # R
        payload[1] = self.rgb_brightness[1]  # G
        payload[2] = self.rgb_brightness[2]  # B
        payload[3] = 0xFF
        # Rest is padding (already zeros)

        self._send_packet(self.PKT_BRIGHTNESS, bytes(payload))

    def send_row(self, row: int, bgr_data: bytes, offset: int = 0):
        """
        Send a single row of pixel data (0x55).

        For rows wider than 497 pixels, call multiple times with offset.

        Args:
            row: Row number (0 to height-1)
            bgr_data: BGR format pixel data
            offset: Horizontal pixel offset (for wide displays)

        Packet structure (after type byte):
          Bytes 0-1: Row number (big-endian)
          Bytes 2-3: Horizontal pixel offset (big-endian)
          Bytes 4-5: Pixel count (big-endian)
          Byte 6:    0x08 (fixed)
          Byte 7:    0x88 (fixed)
          Bytes 8+:  BGR pixel data
        """
        pixel_count = len(bgr_data) // 3

        # Build header (big-endian per protocol spec)
        header = struct.pack(">HHHBB",
                            row,          # Row number (2 bytes BE)
                            offset,       # Pixel offset (2 bytes BE)
                            pixel_count,  # Pixel count (2 bytes BE)
                            0x08,         # Fixed
                            0x88)         # Fixed (was 0x80 in some implementations)

        payload = header + bgr_data
        self._send_packet(self.PKT_IMAGE, payload)

    def send_frame(self, image: np.ndarray = None):
        """
        Send a complete frame to the display.

        Args:
            image: Optional numpy array (height, width, 3) in RGB format.
                   If None, sends the internal framebuffer.
        """
        if image is not None:
            if image.shape != (self.height, self.width, 3):
                raise ValueError(f"Image must be {self.height}x{self.width}x3, got {image.shape}")
            self.framebuffer = image.astype(np.uint8)

        # Send each row
        for row in range(self.height):
            # Get row data and remap color channels based on panel's color order
            row_rgb = self.framebuffer[row]
            # Apply color channel remapping: _color_map specifies output position for each input channel
            # Input is RGB (0=R, 1=G, 2=B), output position determined by _color_map
            row_reordered = np.zeros_like(row_rgb)
            row_reordered[:, self._color_map[0]] = row_rgb[:, 0]  # R input → mapped position
            row_reordered[:, self._color_map[1]] = row_rgb[:, 1]  # G input → mapped position
            row_reordered[:, self._color_map[2]] = row_rgb[:, 2]  # B input → mapped position
            row_data = row_reordered.tobytes()

            # Handle wide displays (>497 pixels) by splitting into chunks
            if self.width <= self.MAX_PIXELS_PER_PACKET:
                self.send_row(row, row_data)
            else:
                # Split row into multiple packets
                for offset in range(0, self.width, self.MAX_PIXELS_PER_PACKET):
                    chunk_pixels = min(self.MAX_PIXELS_PER_PACKET, self.width - offset)
                    chunk_start = offset * 3
                    chunk_end = chunk_start + (chunk_pixels * 3)
                    self.send_row(row, row_data[chunk_start:chunk_end], offset)

        # Wait 5ms then send display frame to trigger refresh
        time.sleep(0.005)
        self.send_display_frame()

    def clear(self, color: tuple = (0, 0, 0)):
        """Clear display to a solid color (RGB tuple)."""
        self.framebuffer[:] = color
        self.send_frame()

    def set_pixel(self, x: int, y: int, color: tuple):
        """Set a single pixel (doesn't send until send_frame called)."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.framebuffer[y, x] = color

    def load_image(self, path: str, resize: bool = True) -> np.ndarray:
        """Load an image file and optionally resize to display dimensions."""
        img = Image.open(path).convert("RGB")
        if resize:
            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
        return np.array(img)

    def show_image(self, path: str):
        """Load and display an image file."""
        self.send_frame(self.load_image(path, resize=True))


def test_pattern(driver: ColorLight5A75B):
    """Generate and display a color bar test pattern."""
    print(f"Generating test pattern for {driver.width}x{driver.height} display...")

    pattern = np.zeros((driver.height, driver.width, 3), dtype=np.uint8)
    bar_width = driver.width // 8
    colors = [
        (255, 255, 255),  # White
        (255, 255, 0),    # Yellow
        (0, 255, 255),    # Cyan
        (0, 255, 0),      # Green
        (255, 0, 255),    # Magenta
        (255, 0, 0),      # Red
        (0, 0, 255),      # Blue
        (0, 0, 0),        # Black
    ]

    for i, color in enumerate(colors):
        x_start = i * bar_width
        x_end = (i + 1) * bar_width if i < 7 else driver.width
        pattern[:, x_start:x_end] = color

    driver.send_frame(pattern)
    print("Test pattern sent!")


def main():
    """CLI interface."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ColorLight 5A-75B LED Matrix Driver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Your setup: 5x4 grid of 64x32 panels
  sudo python3 colorlight.py --panels-x 5 --panels-y 4 --panel-width 64 --panel-height 32 --test

  # Or specify total resolution directly
  sudo python3 colorlight.py -W 320 -H 128 --test

  # Display an image
  sudo python3 colorlight.py -W 320 -H 128 --image photo.png

  # If colors are wrong (red/blue swapped), try different color orders:
  sudo python3 colorlight.py -W 320 -H 128 --test -c RGB
  sudo python3 colorlight.py -W 320 -H 128 --test -c GRB

  # Just show config info (no root needed)
  python3 colorlight.py --info

Note: The 5A-75B can now be configured entirely from Linux! Use --configure.
Different panels have different color orderings - use -c/--color-order if colors look wrong.
        """
    )

    # Display size options
    size = parser.add_argument_group("Display Size")
    size.add_argument("-W", "--width", type=int, help="Total width in pixels")
    size.add_argument("-H", "--height", type=int, help="Total height in pixels")
    size.add_argument("--panels-x", type=int, default=5, help="Panels horizontally (default: 5)")
    size.add_argument("--panels-y", type=int, default=4, help="Panels vertically (default: 4)")
    size.add_argument("--panel-width", type=int, default=64, help="Single panel width (default: 64)")
    size.add_argument("--panel-height", type=int, default=32, help="Single panel height (default: 32)")

    # Connection
    conn = parser.add_argument_group("Connection")
    conn.add_argument("-i", "--interface", default="eth0", help="Network interface (default: eth0)")

    # Display settings
    disp = parser.add_argument_group("Display Settings")
    disp.add_argument("-b", "--brightness", type=int, default=128, help="Brightness 0-255 (default: 128)")
    disp.add_argument("-c", "--color-order", default="BGR",
                      choices=["RGB", "BGR", "GRB", "RBG", "BRG", "GBR"],
                      help="Panel color order (default: BGR). Try different orders if colors are wrong.")

    # Actions
    act = parser.add_argument_group("Actions")
    act.add_argument("--test", action="store_true", help="Show color bar test pattern")
    act.add_argument("--image", help="Display an image file")
    act.add_argument("--color", help="Fill with solid color R,G,B (e.g., 255,0,0)")
    act.add_argument("--info", action="store_true", help="Show config info and exit")

    # Configuration (NEW - Linux-only config!)
    cfg = parser.add_argument_group("Receiver Configuration")
    cfg.add_argument("--configure", action="store_true",
                     help="Configure receiver (sends config packets)")
    cfg.add_argument("--scan-mode", type=int, choices=[4, 8, 16, 32], default=16,
                     help="Scan rate (default: 16)")
    cfg.add_argument("--save-flash", action="store_true",
                     help="Save config to flash (survives power cycle)")
    cfg.add_argument("--discovery", action="store_true",
                     help="Send discovery request")

    args = parser.parse_args()

    # Calculate display size
    if args.width and args.height:
        width, height = args.width, args.height
    else:
        width = args.panels_x * args.panel_width
        height = args.panels_y * args.panel_height

    # Info mode (no root needed)
    if args.info:
        print("Display Configuration:")
        print(f"  Resolution:    {width} x {height} pixels")
        print(f"  Panel grid:    {args.panels_x} x {args.panels_y}")
        print(f"  Panel size:    {args.panel_width} x {args.panel_height}")
        print(f"  Total panels:  {args.panels_x * args.panels_y}")
        print(f"  Total pixels:  {width * height:,}")
        print(f"  Frame size:    {width * height * 3:,} bytes (RGB)")
        print(f"  Bandwidth:     {width * height * 3 * 60 / 1_000_000:.1f} MB/s @ 60fps")
        print(f"  Interface:     {args.interface}")
        print(f"  Color order:   {args.color_order}")
        return

    # Actions that require root
    with ColorLight5A75B(width, height, args.interface, args.color_order) as driver:
        driver.brightness = args.brightness
        print(f"Display: {width}x{height} @ brightness {args.brightness}, color order: {args.color_order}")

        if args.discovery:
            print("Sending discovery request...")
            driver.send_discovery()
            print("Discovery sent (response handling not yet implemented)")

        elif args.configure:
            print("=" * 60)
            print("CONFIGURING RECEIVER (No LEDVISION needed!)")
            print("=" * 60)
            driver.configure_receiver(
                width=width,
                height=height,
                scan_mode=args.scan_mode,
                save=args.save_flash
            )
            print("=" * 60)

        elif args.test:
            test_pattern(driver)
        elif args.image:
            driver.show_image(args.image)
            print(f"Displayed: {args.image}")
        elif args.color:
            r, g, b = map(int, args.color.split(","))
            driver.clear((r, g, b))
            print(f"Filled with RGB({r}, {g}, {b})")
        else:
            test_pattern(driver)


if __name__ == "__main__":
    main()
