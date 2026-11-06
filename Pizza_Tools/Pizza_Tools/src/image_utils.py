from PIL import Image, ImageDraw, ImageChops


def load_pil_image(filepath):
    return Image.open(filepath).convert("RGBA")


def trim_transparent_padding(img, pad_fraction=0.04):
    img = img.convert("RGBA")
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return img

    cropped = img.crop(bbox)
    w, h = cropped.size
    side = max(w, h)
    pad = int(side * pad_fraction)
    canvas_size = side + pad * 2

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    offset = ((canvas_size - w) // 2, (canvas_size - h) // 2)
    canvas.paste(cropped, offset, cropped)
    return canvas


def prepare_mini_logo(img, target_size, edge_threshold=140, shrink_fraction=0.35):
    img = img.convert("RGBA")
    w, h = img.size
    cx, cy = w / 2, h / 2
    max_r = min(w, h) / 2
    new_r = max_r * (1 - shrink_fraction)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((cx - new_r, cy - new_r, cx + new_r, cy + new_r), fill=255)
    r, g, b, a = img.split()
    a = ImageChops.multiply(a, mask)
    img = Image.merge("RGBA", (r, g, b, a))

    img = img.resize(target_size, Image.LANCZOS)

    r, g, b, a = img.split()
    a = a.point(lambda p: 255 if p >= edge_threshold else 0)
    return Image.merge("RGBA", (r, g, b, a))