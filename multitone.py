from itertools import chain
import socket
import sys

import numpy as np
from PIL import Image, ImageOps

c = socket.create_connection((sys.argv[1], 9100))

c.sendall(bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x61, 1])) # Single head energizing
c.sendall(bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x32, 1])) # Lowest speed

image = Image.open(sys.argv[2])
image = image.convert('L')
image = ImageOps.invert(image)


if image.width > 512:
    ratio = 512 / image.width
    image = image.resize((int(image.width * ratio), int(image.height * ratio)))

width = image.width
height = image.height

print(width, height)

image = bytes([p // 17 for p in image.tobytes()])

# lut = [
#     4,  # 0
#     4,  # 1
#     4,  # 2
#     4,  # 3
#     4,  # 4
#     5,  # 5
#     6,  # 6
#     7,  # 7
#     8,  # 8
#     10, # 9
#     10, # 10
#     12, # 11
#     12, # 12
#     13, # 13
#     15, # 14
#     15, # 15
# ]

# image = [lut[x] for x in image]


# image = np.array(image)
# image //= 17
# image = np.interp(image, (0, 15), (4, 15))
# image = [round(x) for x in image.flatten().tolist()]


# A gradient from level 0 to level 15
width = 512
height = 100
image = bytes(list(chain.from_iterable([x] * 31 + [0] for x in range(16))) * height)

colors = [
    [0x00] * 64 * height,
    [0x00] * 64 * height,
    [0x00] * 64 * height,
    [0x00] * 64 * height
]


color0 = [0x00] * 64 * height
color1 = [0x00] * 64 * height
color2 = [0x00] * 64 * height
color3 = [0x00] * 64 * height

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

    if pixel & 0b1000:
        color0[64 * y + x // 8] |= 1 << (7 - index % 8)

    if pixel & 0b0100:
        color1[64 * y + x // 8] |= 1 << (7 - index % 8)

    if pixel & 0b0010:
        color2[64 * y + x // 8] |= 1 << (7 - index % 8)

    if pixel & 0b0001:
        color3[64 * y + x // 8] |= 1 << (7 - index % 8)

    # colors[plane][64 * y + x // 8] |= 1 << (7 - index % 8)


colors = [color0, color1, color2, color3]
# colors = list(reversed(colors))
# colors = [bytes(x) for x in colors]

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

    c.sendall(data)

c.sendall(bytes([0x1d, 0x28, 0x4c, 0x02, 0x00, 0x30, 2])) # Print stored data
c.sendall(bytes([0x1d, 0x56, 65, 0])) # Feed and cut

c.close()
