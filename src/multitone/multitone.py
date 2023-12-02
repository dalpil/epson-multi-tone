import logging

import click
import numpy as np
import numba
from PIL import Image, ImageOps, ImageEnhance


logging.basicConfig(level=logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)

DITHER_KERNEL = (
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
)

palette = [0, 36, 72, 109, 145, 182, 218, 255]

lut = [
    4,  # 0
    5,  # 1
    6,  # 2
    6,  # 3
    7,  # 4
    7,  # 5
    7,  # 6
    8,  # 7
    8,  # 8
    9,  # 9
    10, # 10
    11, # 11
    12, # 12
    13, # 13
    14, # 14
    15, # 15
]

@numba.njit
def dither(original, diff_map, serpentine, palette):
    input = original.copy()
    output = np.zeros_like(input)

    direction = 1
    height, width = input.shape

    for y in range(height):
        for x in range(0, width, direction) if direction > 0 else range(width - 1, -1, direction):
            old_pixel = input[y, x]

            old_distance = 255
            new_pixel = 0
            for each in palette:
                distance = abs(each - old_pixel)

                if distance < old_distance:
                    old_distance = distance
                    new_pixel = each

            quantization_error = old_pixel - new_pixel
            output[y, x] = new_pixel

            for dx, dy, diffusion_coefficient in diff_map:
                # Reverse the kernel if we are going right to left
                if direction < 0:
                    dx *= -1

                xn, yn = x + dx, y + dy

                if (0 <= xn < width) and (0 <= yn < height):
                    input[yn, xn] = max(0, min(255, input[yn, xn] + round(quantization_error * diffusion_coefficient)))

            if serpentine and ((direction > 0 and x >= (width - 1)) or (direction < 0 and x <= 0)):
                direction *= -1

    return output


@click.command(context_settings={'show_default': True})
@click.option('--output-file', type=click.Path(), required=True, help="The binary file to send to the Epson printer")
@click.option('--output-image', type=click.Path())
@click.option('--num-lines', default=100, help='Should be less than half of 415')
@click.option('--sharpen', default=4.0)
@click.argument('image', type=click.File(mode='rb'))
def main(image, output_file, output_image, num_lines, sharpen):
    image = Image.open(image)

    if image.width > 512:
        ratio = 512 / image.width
        image = image.resize((int(image.width * ratio), int(image.height * ratio)))

    image = image.convert('L')
    image = ImageEnhance.Sharpness(image)
    image = image.enhance(sharpen)

    width = image.width
    height = image.height

    numba_palette = numba.typed.List()
    for x in palette:
        numba_palette.append(x)

    image = dither(np.array(image), DITHER_KERNEL, True, numba_palette)
    image = Image.fromarray(np.uint8(image), "L")

    if output_image:
        image.save(output_image)

    image = ImageOps.invert(image)
    image = bytes([p // 17 for p in image.tobytes()])
    image = [lut[x] for x in image]


    output = b''
    output += bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x61, 1]) # Single head energizing
    output += bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x32, 1]) # Lowest speed

    for chunk_num, chunk in enumerate(range(0, 64 * height, 64 * num_lines)):
        for color_index, color_code in enumerate(range(49, 53)):
            bitplane = [0x00] * 64 * num_lines
            image_offset = chunk_num * (width * num_lines)

            for index, pixel in enumerate(image[image_offset:image_offset + width * num_lines]):
                if pixel & (0b1000 >> color_index):
                    bitplane[64 * (index // width) + (index % width) // 8] |= 1 << (7 - index % 8)

            data = bytes([
                0x1d, 0x38, 0x4c,

                (10 + len(bitplane) >> 0)  & 0xff,
                (10 + len(bitplane) >> 8)  & 0xff,
                (10 + len(bitplane) >> 16) & 0xff,
                (10 + len(bitplane) >> 24) & 0xff,

                0x30, 0x70,

                52, # Multi-tone
                1, 1, # No scaling

                color_code,

                (width >> 0) & 0xff, (width >> 8) & 0xff,
                (num_lines >> 0) & 0xff, (num_lines >> 8) & 0xff,
            ]) + bytes(bitplane)

            output += data

        output += bytes([0x1d, 0x28, 0x4c, 0x02, 0x00, 0x30, 2]) # Print stored data

    output += bytes([0x1d, 0x56, 65, 0]) # Feed and cut

    with open(output_file, 'wb') as file:
        file.write(output)


if __name__ == '__main__':
    main()
