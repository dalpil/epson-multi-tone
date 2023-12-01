import logging

import click
import numpy as np
import numba
from PIL import Image, ImageOps, ImageEnhance


logging.basicConfig(level=logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)

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
    9, # 9
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


@click.command()
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
    
    image = dither(np.array(image), DITHER_KERNELS['fedoseev'], True, numba_palette)
    image = Image.fromarray(np.uint8(image), "L")

    if output_image:
        image.save(output_image)
    
    image = ImageOps.invert(image)
    
    image = bytes([p // 17 for p in image.tobytes()])
    
    image = [lut[x] for x in image]

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


    colors = [color0, color1, color2, color3]

    output = b''
    output += bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x61, 1]) # Single head energizing
    output += bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x32, 1]) # Lowest speed

    chunk_size = num_lines

    for chunk_num, chunk in enumerate(range(0, 64 * height, 64 * chunk_size)):
        bitplanes = []

        for color_index, color_code in enumerate(range(49, 53)):
            bitplane = [0x00] * 64 * chunk_size

            image_offset = chunk_num * width * chunk_size
            # print(image_offset, image_offset + width * chunk_size)
            previous = 0
            for index, pixel in enumerate(image[image_offset:image_offset + width * chunk_size]):
                index = image_offset + index
            # for index, pixel in enumerate(image[chunk:chunk + 64 * chunk_size]):
                if index // width != previous:
                    print(index // width)
                    previous = index // width

                if not pixel:
                    continue

                # if pixel & (0b1000 >> color_index):
                #     bitplane[64 * (index // width) + (index % width) // 8] |= 1 << (7 - index % 8)

            bitplanes.append(bitplane)

            data = bytes([
                0x1d, 0x38, 0x4c,

                (10 + len(bitplanes[color_index]) >> 0)  & 0xff,
                (10 + len(bitplanes[color_index]) >> 8)  & 0xff,
                (10 + len(bitplanes[color_index]) >> 16) & 0xff,
                (10 + len(bitplanes[color_index]) >> 24) & 0xff,

                0x30, 0x70,

                52, # Multi-tone
                1, 1, # No scaling

                color_code,

                (width >> 0) & 0xff, (width >> 8) & 0xff,
                (chunk*8 >> 0) & 0xff, (chunk*8 >> 8) & 0xff,
            ]) + bytes(bitplanes[color_index])

            output += data

        output += bytes([0x1d, 0x28, 0x4c, 0x02, 0x00, 0x30, 2]) # Print stored data


    print(color0[:64])

    # for chunk in range(0, 64 * height, 64 * chunk_size):
    #     for index, color_code in enumerate(range(49, 53)):
    #         chunk_height = len(colors[index][chunk:chunk + 64 * chunk_size]) // 64
    #         data = bytes([
    #             0x1d, 0x38, 0x4c,

    #             (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 0)  & 0xff,
    #             (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 8)  & 0xff,
    #             (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 16) & 0xff,
    #             (10 + len(colors[index][chunk:chunk + 64 * chunk_size]) >> 24) & 0xff,

    #             0x30, 0x70,

    #             52, # Multi-tone
    #             1, 1, # No scaling

    #             color_code,

    #             (width >> 0) & 0xff, (width >> 8) & 0xff,
    #             (chunk_height >> 0) & 0xff, (chunk_height >> 8) & 0xff,
    #         ]) + bytes(colors[index][chunk:chunk + 64 * chunk_size])

    #         output += data

    #     output += bytes([0x1d, 0x28, 0x4c, 0x02, 0x00, 0x30, 2]) # Print stored data

    output += bytes([0x1d, 0x56, 65, 0]) # Feed and cut

    with open(output_file, 'wb') as file:
        file.write(output)

    assert(open('reference.bin', 'rb').read() == output)


if __name__ == '__main__':
    main()
