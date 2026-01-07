#!/usr/bin/env python3
"""
LED Matrix Framebuffer Daemon

Continuously reads from a framebuffer source and sends to ColorLight 5A-75B.
This allows any application to write to the LED matrix by writing to the buffer.

Usage:
    sudo python3 led_daemon.py --interface eth0 --source file --fps 60

Sources:
    - file: Reads from /run/ledmatrix.raw (simple, works with any app)
    - fb: Reads from /dev/fb1 (Linux framebuffer device)
    - shm: Reads from shared memory (fastest, needs compatible apps)
"""

import argparse
import mmap
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

from colorlight import ColorLight5A75B


class FramebufferSource:
    """Base class for framebuffer sources."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.frame_size = width * height * 3  # RGB

    def read_frame(self) -> Optional[np.ndarray]:
        """Read a frame from the source. Returns None if no update."""
        raise NotImplementedError

    def open(self):
        """Open the source."""
        pass

    def close(self):
        """Close the source."""
        pass


class FileSource(FramebufferSource):
    """
    Read frames from a raw file.

    Applications write raw RGB data to /run/ledmatrix.raw
    Format: 320*128*3 bytes = 122,880 bytes (RGB, row-major)
    """

    def __init__(self, width: int, height: int, path: str = "/run/ledmatrix.raw"):
        super().__init__(width, height)
        self.path = Path(path)
        self.last_mtime = 0

    def open(self):
        # Create the file if it doesn't exist
        if not self.path.exists():
            self.path.write_bytes(bytes(self.frame_size))
            os.chmod(self.path, 0o666)  # Allow any user to write
            print(f"Created framebuffer file: {self.path} ({self.frame_size} bytes)")

    def read_frame(self) -> Optional[np.ndarray]:
        try:
            # Check if file was modified
            mtime = self.path.stat().st_mtime
            if mtime == self.last_mtime:
                return None  # No change
            self.last_mtime = mtime

            # Read and reshape
            data = self.path.read_bytes()
            if len(data) < self.frame_size:
                data = data + bytes(self.frame_size - len(data))
            elif len(data) > self.frame_size:
                data = data[:self.frame_size]

            return np.frombuffer(data, dtype=np.uint8).reshape((self.height, self.width, 3))

        except (FileNotFoundError, OSError):
            return None


class SharedMemorySource(FramebufferSource):
    """
    Read frames from POSIX shared memory.

    Fastest option for inter-process communication.
    Creates /dev/shm/ledmatrix
    """

    def __init__(self, width: int, height: int, name: str = "ledmatrix"):
        super().__init__(width, height)
        self.name = name
        self.shm_path = Path(f"/dev/shm/{name}")
        self.mm: Optional[mmap.mmap] = None
        self.fd: Optional[int] = None

    def open(self):
        # Create shared memory file
        if not self.shm_path.exists():
            self.shm_path.write_bytes(bytes(self.frame_size))
            os.chmod(self.shm_path, 0o666)

        self.fd = os.open(str(self.shm_path), os.O_RDWR)
        self.mm = mmap.mmap(self.fd, self.frame_size)
        print(f"Opened shared memory: {self.shm_path}")

    def read_frame(self) -> Optional[np.ndarray]:
        if not self.mm:
            return None

        self.mm.seek(0)
        data = self.mm.read(self.frame_size)
        return np.frombuffer(data, dtype=np.uint8).reshape((self.height, self.width, 3)).copy()

    def close(self):
        if self.mm:
            self.mm.close()
        if self.fd:
            os.close(self.fd)


class LinuxFramebufferSource(FramebufferSource):
    """
    Read from a Linux framebuffer device (/dev/fbX).

    This allows using a virtual framebuffer as the source.
    """

    def __init__(self, width: int, height: int, device: str = "/dev/fb1"):
        super().__init__(width, height)
        self.device = device
        self.fd: Optional[int] = None
        self.mm: Optional[mmap.mmap] = None

    def open(self):
        try:
            self.fd = os.open(self.device, os.O_RDONLY)
            # Try to mmap the framebuffer
            # Note: actual fb size may differ, this is simplified
            self.mm = mmap.mmap(self.fd, self.frame_size, prot=mmap.PROT_READ)
            print(f"Opened framebuffer device: {self.device}")
        except (OSError, PermissionError) as e:
            print(f"Warning: Could not open {self.device}: {e}")
            print("Falling back to file source")
            raise

    def read_frame(self) -> Optional[np.ndarray]:
        if not self.mm:
            return None

        self.mm.seek(0)
        data = self.mm.read(self.frame_size)
        return np.frombuffer(data, dtype=np.uint8).reshape((self.height, self.width, 3)).copy()

    def close(self):
        if self.mm:
            self.mm.close()
        if self.fd:
            os.close(self.fd)


class LEDMatrixDaemon:
    """Main daemon that reads from source and sends to LED matrix."""

    def __init__(
        self,
        width: int,
        height: int,
        interface: str,
        source: FramebufferSource,
        fps: int = 60,
        brightness: int = 128
    ):
        self.driver = ColorLight5A75B(width, height, interface)
        self.source = source
        self.target_fps = fps
        self.frame_time = 1.0 / fps
        self.brightness = brightness
        self.running = False
        self.frames_sent = 0
        self.last_frame: Optional[np.ndarray] = None

    def start(self):
        """Start the daemon loop."""
        self.running = True
        self.driver.open()
        self.driver.brightness = self.brightness
        self.source.open()

        # Send initial config
        self.driver.send_config()
        self.driver.send_brightness()

        print(f"LED Matrix Daemon started")
        print(f"  Resolution: {self.driver.width}x{self.driver.height}")
        print(f"  Interface: {self.driver.interface}")
        print(f"  Target FPS: {self.target_fps}")
        print(f"  Brightness: {self.brightness}")
        print(f"Press Ctrl+C to stop")

        start_time = time.time()
        last_stats_time = start_time

        try:
            while self.running:
                loop_start = time.perf_counter()

                # Read frame from source
                frame = self.source.read_frame()

                # If source returns None (no change) and we're using file source,
                # we can skip sending. For shm/fb, always send for consistent timing.
                if frame is not None:
                    self.last_frame = frame

                if self.last_frame is not None:
                    self.driver.send_frame(self.last_frame)
                    self.frames_sent += 1

                # Maintain frame rate
                elapsed = time.perf_counter() - loop_start
                sleep_time = self.frame_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

                # Print stats every 5 seconds
                now = time.time()
                if now - last_stats_time >= 5.0:
                    actual_fps = self.frames_sent / (now - start_time)
                    print(f"Stats: {self.frames_sent} frames, {actual_fps:.1f} fps")
                    last_stats_time = now

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop()

    def stop(self):
        """Stop the daemon."""
        self.running = False
        self.driver.clear((0, 0, 0))  # Turn off display
        self.source.close()
        self.driver.close()


def main():
    parser = argparse.ArgumentParser(
        description="LED Matrix Framebuffer Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start daemon reading from file (simplest)
  sudo python3 led_daemon.py -i eth0 --source file

  # Start daemon with shared memory (fastest)
  sudo python3 led_daemon.py -i eth0 --source shm

  # Write to the LED matrix from another program:
  # File method: write 122880 bytes (320x128x3 RGB) to /run/ledmatrix.raw
  # SHM method: write to /dev/shm/ledmatrix

  # Example with ffmpeg (play video to LED matrix):
  ffmpeg -i video.mp4 -vf "scale=320:128" -f rawvideo -pix_fmt rgb24 /run/ledmatrix.raw
        """
    )

    parser.add_argument("-i", "--interface", default="eth0",
                        help="Network interface (default: eth0)")
    parser.add_argument("-W", "--width", type=int, default=320,
                        help="Display width (default: 320)")
    parser.add_argument("-H", "--height", type=int, default=128,
                        help="Display height (default: 128)")
    parser.add_argument("-f", "--fps", type=int, default=60,
                        help="Target frame rate (default: 60)")
    parser.add_argument("-b", "--brightness", type=int, default=128,
                        help="Brightness 0-255 (default: 128)")
    parser.add_argument("-s", "--source", choices=["file", "shm", "fb"],
                        default="file", help="Framebuffer source (default: file)")
    parser.add_argument("--fb-device", default="/dev/fb1",
                        help="Framebuffer device for 'fb' source")
    parser.add_argument("--file-path", default="/run/ledmatrix.raw",
                        help="File path for 'file' source")

    args = parser.parse_args()

    # Create appropriate source
    if args.source == "file":
        source = FileSource(args.width, args.height, args.file_path)
    elif args.source == "shm":
        source = SharedMemorySource(args.width, args.height)
    elif args.source == "fb":
        try:
            source = LinuxFramebufferSource(args.width, args.height, args.fb_device)
        except OSError:
            print("Falling back to file source")
            source = FileSource(args.width, args.height, args.file_path)

    # Create and start daemon
    daemon = LEDMatrixDaemon(
        width=args.width,
        height=args.height,
        interface=args.interface,
        source=source,
        fps=args.fps,
        brightness=args.brightness
    )

    # Handle signals gracefully
    def signal_handler(sig, frame):
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    daemon.start()


if __name__ == "__main__":
    main()
