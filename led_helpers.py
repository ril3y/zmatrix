#!/usr/bin/env python3
"""
LED Matrix Helper Utilities

Simple tools to write to the LED matrix via the daemon.
These don't need root - they just write to /run/ledmatrix.raw or /dev/shm/ledmatrix
"""

import os
import struct
import time
from pathlib import Path
from typing import Tuple, Union

import numpy as np
from PIL import Image


# Default display settings (5x4 grid of 64x32 panels)
DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 128
DEFAULT_FILE = "/run/ledmatrix.raw"
DEFAULT_SHM = "/dev/shm/ledmatrix"


class LEDMatrixWriter:
    """
    Write frames to the LED matrix daemon via file or shared memory.

    Usage:
        writer = LEDMatrixWriter()
        writer.clear((255, 0, 0))  # Red screen
        writer.show_image("image.png")
    """

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        target: str = "file"
    ):
        self.width = width
        self.height = height
        self.frame_size = width * height * 3

        if target == "file":
            self.path = Path(DEFAULT_FILE)
        elif target == "shm":
            self.path = Path(DEFAULT_SHM)
        else:
            self.path = Path(target)

    def write_frame(self, frame: np.ndarray):
        """Write a frame (numpy array HxWx3 RGB) to the buffer."""
        if frame.shape != (self.height, self.width, 3):
            raise ValueError(f"Frame must be {self.height}x{self.width}x3, got {frame.shape}")

        self.path.write_bytes(frame.astype(np.uint8).tobytes())

    def clear(self, color: Tuple[int, int, int] = (0, 0, 0)):
        """Fill display with solid color (RGB tuple)."""
        frame = np.full((self.height, self.width, 3), color, dtype=np.uint8)
        self.write_frame(frame)

    def show_image(self, path: str, fit: str = "fill"):
        """
        Display an image.

        Args:
            path: Path to image file
            fit: How to fit image - "fill" (stretch), "fit" (letterbox), "crop" (fill and crop)
        """
        img = Image.open(path).convert("RGB")

        if fit == "fill":
            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
        elif fit == "fit":
            img.thumbnail((self.width, self.height), Image.Resampling.LANCZOS)
            # Center on black background
            bg = Image.new("RGB", (self.width, self.height), (0, 0, 0))
            offset = ((self.width - img.width) // 2, (self.height - img.height) // 2)
            bg.paste(img, offset)
            img = bg
        elif fit == "crop":
            # Resize to cover, then crop center
            aspect = self.width / self.height
            img_aspect = img.width / img.height

            if img_aspect > aspect:
                # Image is wider, fit height
                new_height = self.height
                new_width = int(img.width * (self.height / img.height))
            else:
                # Image is taller, fit width
                new_width = self.width
                new_height = int(img.height * (self.width / img.width))

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            # Crop center
            left = (new_width - self.width) // 2
            top = (new_height - self.height) // 2
            img = img.crop((left, top, left + self.width, top + self.height))

        self.write_frame(np.array(img))

    def gradient(self, color1: Tuple[int, int, int], color2: Tuple[int, int, int], horizontal: bool = True):
        """Display a gradient between two colors."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        for i in range(3):
            if horizontal:
                frame[:, :, i] = np.linspace(color1[i], color2[i], self.width, dtype=np.uint8)
            else:
                frame[:, :, i] = np.linspace(color1[i], color2[i], self.height, dtype=np.uint8).reshape(-1, 1)

        self.write_frame(frame)

    def test_pattern(self):
        """Display a test pattern (color bars)."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        bar_width = self.width // 8
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
            x_end = (i + 1) * bar_width if i < 7 else self.width
            frame[:, x_start:x_end] = color

        self.write_frame(frame)

    def rainbow_cycle(self, duration: float = 5.0, fps: float = 30):
        """Animate a rainbow cycle for the given duration."""
        frame_time = 1.0 / fps
        frames = int(duration * fps)

        for i in range(frames):
            hue_offset = i / frames
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

            for x in range(self.width):
                hue = (x / self.width + hue_offset) % 1.0
                r, g, b = hsv_to_rgb(hue, 1.0, 1.0)
                frame[:, x] = (int(r * 255), int(g * 255), int(b * 255))

            self.write_frame(frame)
            time.sleep(frame_time)


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[float, float, float]:
    """Convert HSV to RGB (all values 0-1)."""
    if s == 0:
        return v, v, v

    i = int(h * 6)
    f = (h * 6) - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))

    i %= 6
    if i == 0:
        return v, t, p
    elif i == 1:
        return q, v, p
    elif i == 2:
        return p, v, t
    elif i == 3:
        return p, q, v
    elif i == 4:
        return t, p, v
    else:
        return v, p, q


def main():
    """Command-line interface for LED helpers."""
    import argparse

    parser = argparse.ArgumentParser(description="LED Matrix Helper Utilities")
    parser.add_argument("command", choices=["clear", "color", "image", "test", "gradient", "rainbow"],
                        help="Command to run")
    parser.add_argument("--color", "-c", help="Color as R,G,B (e.g., 255,0,0 for red)")
    parser.add_argument("--image", "-i", help="Image path")
    parser.add_argument("--fit", choices=["fill", "fit", "crop"], default="fill",
                        help="Image fit mode")
    parser.add_argument("--duration", "-d", type=float, default=5.0,
                        help="Duration for animations")

    args = parser.parse_args()

    writer = LEDMatrixWriter()

    if args.command == "clear":
        writer.clear()
        print("Display cleared")

    elif args.command == "color":
        if not args.color:
            print("Error: --color required (e.g., --color 255,0,0)")
            return
        r, g, b = map(int, args.color.split(","))
        writer.clear((r, g, b))
        print(f"Display set to RGB({r}, {g}, {b})")

    elif args.command == "image":
        if not args.image:
            print("Error: --image required")
            return
        writer.show_image(args.image, fit=args.fit)
        print(f"Displaying {args.image}")

    elif args.command == "test":
        writer.test_pattern()
        print("Displaying test pattern")

    elif args.command == "gradient":
        writer.gradient((255, 0, 0), (0, 0, 255))
        print("Displaying gradient")

    elif args.command == "rainbow":
        print(f"Running rainbow animation for {args.duration}s...")
        writer.rainbow_cycle(duration=args.duration)


if __name__ == "__main__":
    main()
