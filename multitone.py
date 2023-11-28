from itertools import chain
import socket
import sys

from PIL import Image, ImageOps

# c = socket.create_connection((sys.argv[1], 9100))

# c.sendall(bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x61, 1])) # Single head energizing
# c.sendall(bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x32, 1])) # Lowest speed

image = Image.open(sys.argv[1])
image = image.convert('L')

if image.width > 512:
    ratio = 512 / image.width
    image = image.resize((int(image.width * ratio), int(image.height * ratio)))

width = image.width
height = image.height

print(width, height)

image = bytes([p // 17 for p in image.tobytes()])

# A gradient from level 0 to level 15
# image = bytes(list(chain.from_iterable([x] * 31 + [0] for x in range(16))) * height)

colors = [
    [0x00] * 64 * height,
    [0x00] * 64 * height,
    [0x00] * 64 * height,
    [0x00] * 64 * height
]

for index, pixel in enumerate(image):
    x = index % width
    y = index // width

    if not pixel:
        continue

    if pixel & 0b1000:
        plane = 0

    if pixel & 0b0100:
        plane = 1

    if pixel & 0b0010:
        plane = 2

    if pixel & 0b0001:
        plane = 3

    colors[plane][64 * y + x // 8] |= 1 << (7 - index % 8)

for i in range(4):
    print(colors[i][:64])

for index, color_code in enumerate(range(49, 53)):
    data = bytes([
        0x1d, 0x38, 0x4c,

        (10 + len(colors[index]) >> 0)  & 0xff,
        (10 + len(colors[index]) >> 8)  & 0xff,
        (10 + len(colors[index]) >> 16) & 0xff,
        (10 + len(colors[index]) >> 24) & 0xff,

        0x30, 0x70,

        52, # Multi-tone
        1, 1, # No scaling

        color_code,

        (width >> 0) & 0xff, (width >> 8) & 0xff,
        (height >> 0) & 0xff, (height >> 8) & 0xff,
    ]) + bytes(colors[index])

    # c.sendall(data)

# c.sendall(bytes([0x1d, 0x28, 0x4c, 0x02, 0x00, 0x30, 2])) # Print stored data
# c.sendall(bytes([0x1d, 0x56, 65, 100])) # Feed and cut
