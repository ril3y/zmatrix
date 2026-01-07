from scapy.all import *
from scapy.layers.l2 import Ether
from time import sleep
from PIL import Image
from pyColorLight import PyColorLight
# Set the source and destination MAC addresses
src_mac = "22:22:33:44:55:66"
dst_mac = "11:22:33:44:55:66"


def print_bytes(var):
    hex_chars = ['{:02x}'.format(b) for b in var]
    for i in range(0, len(var), 16):
        row = hex_chars[i:i + 16]
        ascii_row = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in var[i:i + 16])
        print('{:04x}: {:48} {}'.format(i, ' '.join(row), ascii_row))
    print(len(var))



# packet_column_sync = {
#     "src_mac": src_mac,
#     "dst_mac": dst_mac,
#     "eth_type": 0x107,
#     "data": b'\x00\x00\x00\x00' + b'\x00\ * 17' + b'\xff\x05\x00\xff\xff\xff' + 'b\x00' * 67
# }


def send_column_sync(data):
    eth_type = 0x0107


img = Image.open("zelda.bmp")
img = img.convert("RGB")
width, height = img.size
print(f"IMAGE SIZE: {height}x{width}")

for row in range(height):
    pixel_data = b''
    for col in range(width):
        r, g, b = img.getpixel((col, row))
        pixel_data += bytes([r, g, b])

# Set the Ethernet type to 0x5500
eth_type = 0x5500

pyc = PyColorLight(256,256,"11:22:33:44:55:66")
pyc.test()

#init_packet = b'\x00\x00\x00\x00\x00\x08\x88' + b'\x00\x00\xff' * 128
#column_switch = b'\x00\x00\x00\x00\x00\x08\x88' + b'\x00\x00\xff' * 128
# eth_frame = Ether(src=src_mac, dst=dst_mac, type=eth_type) / Raw(load=init_packet)
#
# sendp(eth_frame, iface="Ethernet")

# Loop through the values 0x00 to 0x7F for the first byte of the payload data
while (1):
    for payload_byte in range(256):
        #sleep(.001)
        # Set the payload data using byte substitutions and the payload_byte variable
        payload_data = bytes([payload_byte]) + b'\x00\x00\x00\x80\x08\x88' + b'\x00\x00\xff' * 128

        # Create the Ethernet II frame
        eth_frame = Ether(src=src_mac, dst=dst_mac, type=eth_type) / Raw(load=payload_data)

        # Send the Ethernet II frame out through the network interface
        sendp(eth_frame, iface="Ethernet")
