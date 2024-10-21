import logging
import logging.config
import time

import click
import numpy as np

try:
    import numba
except ImportError:
    _has_numba = False
else:
    _has_numba = True

from PIL import Image, ImageEnhance


def dither(original, diff_map, serpentine, palette):
    input = original.copy()
    output = np.zeros_like(input)

    direction = 1
    height, width = input.shape

    for y in range(height):
        for x in range(0, width, direction) if direction > 0 else range(width - 1, -1, direction):
            # Do not dither black or white
            if original[y, x] == 0 or original[y, x] == 255:
                output[y, x] = original[y, x]
                continue 

            old_pixel = input[y, x]
            new_pixel = palette[np.argmin(np.abs(palette - old_pixel))]
            quantization_error = old_pixel - new_pixel
            output[y, x] = new_pixel

            for dx, dy, diffusion_coefficient in diff_map:
                # Reverse the kernel if we are going right to left
                if direction < 0:
                    dx *= -1

                xn, yn = x + dx, y + dy

                if (0 <= xn < width) and (0 <= yn < height):
                    input[yn, xn] = max(0, min(255, input[yn, xn] + round(quantization_error * diffusion_coefficient)))

        if serpentine:
            direction *= -1

    return output

if _has_numba:
    dither = numba.njit(dither)


@click.command(context_settings={'show_default': True})
@click.option('--output-file', type=click.Path(), required=True, help='The binary file to send to the Epson printer')
@click.option('--output-image', type=click.Path())
@click.option('--num-lines', default=100, help='Should be less than half of 415')
@click.option('--resize', type=int)
@click.option('--sharpness', default=2.0, help='Sharpening the image usually leads to a better result when printed')
@click.option('--contrast', default=1.2, help='Increasing the contrast might make the print look better, try 1.2 for example')
@click.option('--cut/--no-cut', default=False)
@click.option('--speed', default=1, help='The slowest possible speed is recommended')
@click.option('--heads-energizing', default=1, help='Single-head energizing is highly recommended')
@click.option('--loglevel', default='INFO', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False))
@click.argument('image', type=click.File(mode='rb'))
def main(image, output_file, output_image, num_lines, resize, sharpness, contrast, cut, speed, heads_energizing, loglevel):
    logging.basicConfig(level=loglevel, format='[%(asctime)s] %(levelname)s: %(message)s')
    logging.getLogger('numba').setLevel('CRITICAL')
    logging.getLogger('PIL').setLevel('CRITICAL')

    log = logging.getLogger(__name__)

    log.debug(f'Opening image "{image.name}"')
    image = Image.open(image)

    if image.mode == 'RGBA':
        log.debug('Input image has transparency channel, setting all transparent pixels to white')
        white_background = Image.new('RGBA', image.size, 'WHITE')
        white_background.paste(image, mask=image)
        image = white_background

    # Resize the image if requested by the user, or if the image is wider than 512 pixels
    if resize or image.width > 512:
        ratio = (resize or 512) / image.width
        image = image.resize((round(image.width * ratio), round(image.height * ratio)))
        log.debug(f'Resized image to {image.width}x{image.height}')

    width = image.width
    width_nbytes = (width + 8 - 1) // 8
    height = image.height

    # Apply image adjustments
    image = image.convert('L')
    if sharpness:
        image = ImageEnhance.Sharpness(image)
        image = image.enhance(sharpness)
        log.debug(f'Modified sharpness of image with factor {sharpness}')

    if contrast:
        image = ImageEnhance.Contrast(image)
        image = image.enhance(contrast)
        log.debug(f'Modified contrast of image image with factor {contrast}')

    dither_kernel = (
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

    # This LUT was selected by printing a calibration sheet with each of the 16
    # "colors". I then scanned the receipt and measured the average color of
    # each calibration square, giving me a percentage between full black and
    # full white. This percentage was then mapped to values between 0 and 255.
    lut = {
        0: 15,
        9: 13,
        45: 12,
        54: 11,
        98: 10,
        107: 9,
        157: 8,
        210: 7,
        242: 6,
        251: 5,
        255: 4
    }

    if _has_numba:
        log.debug('Dithering input image with JIT')
    else:
        log.debug('Dithering input image without JIT, this might take a while...')

    time_dither_start = time.time()
    image = dither(np.array(image, dtype=np.int16), dither_kernel, True, np.array(list(lut.keys())))
    image = Image.fromarray(np.uint8(image), 'L')
    log.debug(f'Dithering finished, took {time.time() - time_dither_start} seconds')

    if output_image:
        image.save(output_image)
        log.debug(f'Wrote output image to {output_image}')

    # Apply LUT
    log.debug('Applying LUT to image')
    image = [lut[p] for p in image.tobytes()]

    output = b''
    output += bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x61, heads_energizing])
    output += bytes([0x1d, 0x28, 0x4b, 0x02, 0x00, 0x32, speed])

    # Large images needs to be sent to the printer in smaller slices to avoid banding while 
    # printing. The height of these slices should preferably be less than half of 415 according
    # to Epson. Maximum slice height will vary depending on the transport layer.
    for slice_y_start in range(0, height, num_lines):
        slice_y_end = min(slice_y_start + num_lines, height)
        slice_height = slice_y_end - slice_y_start

        slice = image[width * slice_y_start :
                      width * slice_y_end]
        
        for color_index, color_code in enumerate(range(49, 53)):
            bitplane = [0x00] * width_nbytes * slice_height

            for index, pixel in enumerate(slice):
                if pixel & (0b1000 >> color_index):
                    bitplane[width_nbytes * (index // width) + (index % width) // 8] |= 1 << (7 - index % 8)

            data = bytes([
                0x1d, 0x38, 0x4c, # GS 8 L 

                (10 + len(bitplane) >> 0)  & 0xff,
                (10 + len(bitplane) >> 8)  & 0xff,
                (10 + len(bitplane) >> 16) & 0xff,
                (10 + len(bitplane) >> 24) & 0xff,

                0x30, 0x70, # Function 112

                52, # Multi-tone
                1, 1, # No scaling

                color_code,

                (width >> 0) & 0xff, (width >> 8) & 0xff,
                (slice_height >> 0) & 0xff, (slice_height >> 8) & 0xff,
            ]) + bytes(bitplane)

            output += data

        output += bytes([0x1d, 0x28, 0x4c, 0x02, 0x00, 0x30, 2]) # Print stored data

    if cut:
        output += bytes([0x1d, 0x56, 65, 0]) # Feed and cut

    with open(output_file, 'wb') as file:
        file.write(output)
        log.debug(f'Wrote output binary file to {output_file}')


if __name__ == '__main__':
    main()
