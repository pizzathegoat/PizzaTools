from PIL import Image, ImageDraw

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

def _find_logo_circle(img, solid_alpha=200):
    alpha = img.split()[3]
    w, h = img.size
    solid = alpha.point(lambda p: 255 if p >= solid_alpha else 0)
    bbox = solid.getbbox()
    if bbox is None:
        return w / 2, h / 2, min(w, h) / 2
    row = (bbox[1] + bbox[3]) // 2
    col = (bbox[0] + bbox[2]) // 2
    def edges(get, length):
        first = next((i for i in range(length) if get(i) >= solid_alpha), 0)
        last = next((i for i in range(length - 1, -1, -1) if get(i) >= solid_alpha), length - 1)
        return first, last
    left, right = edges(lambda x: alpha.getpixel((x, row)), w)
    top, bottom = edges(lambda y: alpha.getpixel((col, y)), h)
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    r = max(cx - left, right - cx, cy - top, bottom - cy)
    return cx, cy, r

def prepare_mini_logo(img, target_size=(256, 256)):
    return img.convert("RGBA").resize(target_size, Image.LANCZOS)


def make_glow_logo(img, target_size, glow_color=None, intensity=1.0, out_px=None):
    out_px = max(1, int(out_px or target_size[0]))
    supersample = 8
    side = out_px * supersample
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, side - 1, side - 1), fill=255)
    mask = mask.resize((out_px, out_px), Image.Resampling.BOX)
    resized = img.convert("RGB").resize((out_px, out_px), Image.LANCZOS).convert("RGBA")
    resized.putalpha(mask)
    return resized
