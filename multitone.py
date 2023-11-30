from itertools import chain
import socket
import sys

import numpy as np
from PIL import Image, ImageOps, ImageEnhance

from colorama import init as colorama_init
from colorama import Fore, Style


DITHER_KERNELS = {
    'atkinson': (
        (1, 0, 1 / 8),
        (2, 0, 1 / 8),
        (-1, 1, 1 / 8),
        (0, 1, 1 / 8),
        (1, 1, 1 / 8),
        (0, 2, 1 / 8),
    ),

    'floyd-steinberg': (
        (1, 0, 7 / 16),
        (-1, 1, 3 / 16),
        (0, 1, 5 / 16),
        (1, 1, 1 / 16),
    ),

    'jarvis-judice-ninke': (
        (1, 0, 7 / 48),
        (2, 0, 5 / 48),
        (-2, 1, 3 / 48),
        (-1, 1, 5 / 48),
        (0, 1, 7 / 48),
        (1, 1, 5 / 48),
        (2, 1, 3 / 48),
        (-2, 2, 1 / 48),
        (-1, 2, 3 / 48),
        (0, 2, 5 / 48),
        (1, 2, 3 / 48),
        (2, 2, 1 / 48),
    ),

    'stucki': (
        (1, 0, 8 / 42),
        (2, 0, 4 / 42),
        (-2, 1, 2 / 42),
        (-1, 1, 4 / 42),
        (0, 1, 8 / 42),
        (1, 1, 4 / 42),
        (2, 1, 2 / 42),
        (-2, 2, 1 / 42),
        (-1, 2, 2 / 42),
        (0, 2, 4 / 42),
        (1, 2, 2 / 42),
        (2, 2, 1 / 42),
    ),

    'burkes': (
        (1, 0, 8 / 32),
        (2, 0, 4 / 32),
        (-2, 1, 2 / 32),
        (-1, 1, 4 / 32),
        (0, 1, 8 / 32),
        (1, 1, 4 / 32),
        (2, 1, 2 / 32),
    ),

    'sierra3': (
        (1, 0, 5 / 32),
        (2, 0, 3 / 32),
        (-2, 1, 2 / 32),
        (-1, 1, 4 / 32),
        (0, 1, 5 / 32),
        (1, 1, 4 / 32),
        (2, 1, 2 / 32),
        (-1, 2, 2 / 32),
        (0, 2, 3 / 32),
        (1, 2, 2 / 32),
    ),

    'sierra2': (
        (1, 0, 4 / 16),
        (2, 0, 3 / 16),
        (-2, 1, 1 / 16),
        (-1, 1, 2 / 16),
        (0, 1, 3 / 16),
        (1, 1, 2 / 16),
        (2, 1, 1 / 16),
    ),

    'sierra-lite': (
        (1, 0, 2 / 4),
        (-1, 1, 1 / 4),
        (0, 1, 1 / 4),
    ),

    # https://doi.org/10.1117/12.271597
    'wong-allebach': (
        (1, 0, 0.2911),

        (-1, 1, 0.1373),
        (0, 1, 0.3457),
        (1, 1, 0.2258)
    ),

    # https://doi.org/10.1117/12.2180540
    'fedoseev': (
        (1, 0, 0.5423),
        (2, 0, 0.0533),

        (-2, 1, 0.0246),
        (-1, 1, 0.2191),
        (0, 1, 0.4715),
        (1, 1, -0.0023),
        (2, 1, -0.1241),

        (-2, 2, -0.0065),
        (-1, 2, -0.0692),
        (0, 2, 0.0168),
        (1, 2, -0.0952),
        (2, 2, -0.0304),
    ),

    'fedoseev2': (
        (1, 0, 0.4364),
        (0, 1, 0.5636),
    ),

    'fedoseev3': (
        (1, 0, 0.4473),
        (-1, 1, 0.1654),
        (0, 1, 0.3872),
    ),

    'fedoseev4': (
        (1, 0, 0.5221),
        (-1, 1, 0.1854),
        (0, 1, 0.4689),
        (1, 2, -0.1763),
    ),
}

palette = [0, 63, 127, 190, 255]
lut =     [0, 7, 9, 11, 15]

# 7 colors
palette = [0, 42, 84, 126, 168, 210, 255]
lut =     [0, 6,  7,  8,   10,   11,  15]

# 8 colors
palette = [0, 36, 72, 109, 145, 182, 218, 255]


def dither(original, diff_map, serpentine, k=0.0):
    input = original.copy()
    output = np.zeros_like(input)

    direction = 1
    height, width = input.shape

    for y in range(height):
        for x in range(0, width, direction) if direction > 0 else range(width - 1, -1, direction):
            old_pixel = input[y, x]
            # new_pixel = 0 if old_pixel + (k * (original[y, x] - 127)) <= 127 + noise_multiplier * np.random.uniform(-127, 127) else 255

            # new_pixel = min(palette, key=lambda x:abs(x - max(0, min(255, (old_pixel + (k * (original[y, x] - 127)))))))
            new_pixel = min(palette, key=lambda x:abs(x - old_pixel))

            quantization_error = old_pixel - new_pixel
            output[y, x] = new_pixel

            for dx, dy, diffusion_coefficient in diff_map:
                # Reverse the kernel if we are going right to left
                if direction < 0:
                    dx *= -1

                xn, yn = x + dx, y + dy

                if (0 <= xn < width) and (0 <= yn < height):
                    # Some kernels use negative coefficients, so we cannot clamp this value between 0.0-1.0
                    input[yn, xn] = max(0, min(255, input[yn, xn] + round(quantization_error * diffusion_coefficient)))

            if serpentine and ((direction > 0 and x >= (width - 1)) or (direction < 0 and x <= 0)):
                direction *= -1

    return output


image = Image.open(sys.argv[2])

if image.width > 512:
    ratio = 512 / image.width
    image = image.resize((int(image.width * ratio), int(image.height * ratio)))

image = image.convert('L')
image = ImageEnhance.Sharpness(image)
image = image.enhance(3.0)

# image = ImageOps.invert(image)

# pixels = np.array(image, dtype=np.float64)
# pixels /= 255.0
# pixels = np.where(pixels <= 0.04045, pixels/12.92, ((pixels+0.055)/1.055)**2.4)
# image = Image.fromarray(np.uint8(pixels * 255.0), 'L')

width = image.width
height = image.height

image = dither(np.array(image), DITHER_KERNELS['fedoseev'], True, k=1.0)
# breakpoint()
image = Image.fromarray(np.uint8(image), "L")
hist = image.histogram()
print("Num colors:", len(list(filter(None, hist))))
image.save('output.png')
image = ImageOps.invert(image)
# breakpoint()

# image = Image.open(sys.argv[2])
# image = ImageOps.invert(image)
# image = ImageOps.flip(image)
# image = ImageOps.mirror(image)

image = bytes([p // 17 for p in image.tobytes()])

lut =     [0, 6,  7,  8,   10,   11,  15]

lut = [
    0,  # 0
    5,  # 1
    6,  # 2
    6,  # 3
    6,  # 4
    7,  # 5
    7,  # 6
    8,  # 7
    8,  # 8
    9, # 9
    10, # 10
    11, # 11
    12, # 12
    13, # 13
    14, # 14
    15, # 15
]

{0, 2, 5, 7, 10, 12, 15}

# breakpoint()
image = [lut[x] for x in image]


# image = np.array(image)
# image //= 17
# image = np.interp(image, (0, 15), (4, 15))
# image = [round(x) for x in image.flatten().tolist()]


# A gradient from level 0 to level 15
# width = 512
# height = 100
# image = bytes(list(chain.from_iterable([x] * 31 + [0] for x in range(16))) * height)

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
    if not pixel:
        continue

    x = index % width
    y = index // width

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

# c = socket.create_connection((sys.argv[1], 9100))

# c.sendall(bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x61, 1])) # Single head energizing
# c.sendall(bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x32, 1])) # Lowest speed

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


previous_chunk = 0
# for chunk in range(415 * 64, 64 * height, 415 * 64):
chunk_size = 415
chunk_size = 256
for chunk in range(0, 64 * height, 64 * chunk_size):
    print(chunk // 64, min(height, (chunk + 64 * chunk_size) // 64))
    for index, color_code in enumerate(range(49, 53)):
        chunk_height = len(colors[index][chunk:chunk + 64 * chunk_size]) // 64
        data = bytes([
            0x1d, 0x38, 0x4c,

            (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 0)  & 0xff,
            (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 8)  & 0xff,
            (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 16) & 0xff,
            (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 24) & 0xff,

            0x30, 0x70,

            52, # Multi-tone
            1, 1, # No scaling

            color_code,

            (width >> 0) & 0xff, (width >> 8) & 0xff,
            (chunk_height >> 0) & 0xff, (chunk_height >> 8) & 0xff,
        ]) + bytes(colors[index][chunk:chunk + 64 * chunk_size])

        logline = ' '.join('{:02x}'.format(x) for x in data[:24])
        print('d: ', logline[:50], Style.DIM, end='', sep='')
        print(logline[50:], Style.RESET_ALL)
        # c.sendall(data)

    # c.sendall(bytes([0x1d, 0x28, 0x4c, 0x02, 0x00, 0x30, 2])) # Print stored data

# c.sendall(bytes([0x1d, 0x56, 65, 0])) # Feed and cut

# c.close()
