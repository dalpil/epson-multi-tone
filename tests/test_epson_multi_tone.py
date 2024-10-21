from pathlib import Path
from hashlib import sha1

from click.testing import CliRunner
from PIL import Image, ImageDraw

from epson_multi_tone import main


def generate_linear_gradient(width=256, height=50):
    image = Image.new('L', (width, height))
    draw = ImageDraw.Draw(image)

    for x in range(256):
        draw.rectangle([(x, 0), (x, height)], fill=x)

    return image


def test_epson_multi_tone(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        td = Path(td)

        image = generate_linear_gradient(256, 50)
        image_path = str(td / "gradient.png")
        image.save(image_path)

        output_path = td / "output.bin"
        output_image_path = td / "output.png"

        runner.invoke(main, [image_path, f'--output-image={output_image_path}', f'--output-file={output_path}', '--sharpness=0.0', '--contrast=0.0'])

        with open(output_path, 'rb') as output:
            assert sha1(output.read()).hexdigest() == 'f4b7d16d8ea5967a32f7369054c3772bfc6b2754'
