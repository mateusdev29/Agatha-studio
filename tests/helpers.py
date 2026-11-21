"""Geradores de imagens/arquivos para os testes de upload."""
import io

from PIL import Image


def image_bytes(fmt="PNG", size=(40, 30), color=(200, 30, 30), **save_kwargs) -> bytes:
    buf = io.BytesIO()
    mode = "RGB" if fmt == "JPEG" else "RGBA"
    Image.new(mode, size, color if mode == "RGB" else (*color, 255)).save(buf, fmt, **save_kwargs)
    return buf.getvalue()


def jpeg_with_exif(size=(40, 20), orientation=None, gps=True) -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "CameraMaker"                     # Make
    if orientation:
        exif[0x0112] = orientation
    if gps:
        exif[0x8825] = {1: "S", 2: (12.0, 58.0, 0.0), 3: "W", 4: (38.0, 28.0, 0.0)}   # GPS IFD
    return image_bytes("JPEG", size, exif=exif)


def upload(name, data, content_type="image/png"):
    return (io.BytesIO(data), name, content_type)
