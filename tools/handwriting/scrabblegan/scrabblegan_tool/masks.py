"""Image normalization and ink-mask generation for handwriting assets."""


from PIL import Image

_WHITE_THRESHOLD = 245
_ALPHA_THRESHOLD = 0
_INK_RGB = {
    "black": (20, 20, 20),
    "gray": (110, 110, 110),
    "white": (255, 255, 255),
}


# Input: rohe Generator-Ausgabe und Zielpfade fuer PNG und Maske.
# Output: Metadaten mit `ink_bbox` und `image_size`.
# Die Funktion normalisiert das Bild deterministisch auf RGBA, erzeugt eine
# separate L-Maske und schreibt beide Dateien.
def build_asset_images(raw_path, image_path, mask_path, ink_color, background):
    # type: (Path, Path, Path, str, str) -> dict
    source = Image.open(raw_path).convert("RGBA")
    mask = _build_mask(source, background)
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError(f"Generated asset has an empty ink mask: {raw_path}")

    normalized = _normalize_rgba(source, mask, ink_color, background)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.save(image_path)
    mask.save(mask_path)

    return {
        "ink_bbox": {
            "x": bbox[0],
            "y": bbox[1],
            "width": bbox[2] - bbox[0],
            "height": bbox[3] - bbox[1],
        },
        "image_size": {"width": source.size[0], "height": source.size[1]},
    }


# Input: `image` als RGBA und Hintergrundmodus.
# Output: L-Modus-Maske mit sichtbarer Tinte.
# Transparente Assets nutzen Alpha, weisse Hintergruende nutzen Distanz zu
# Weiss als deterministische Schwelle.
def _build_mask(image, background):
    # type: (Image.Image, str) -> Image.Image
    if background == "transparent":
        return image.getchannel("A").point(
            lambda value: 255 if value > _ALPHA_THRESHOLD else 0
        )

    rgb = image.convert("RGB")
    mask = Image.new("L", image.size, 0)
    rgb_pixels = rgb.load()
    mask_pixels = mask.load()
    for y in range(image.size[1]):
        for x in range(image.size[0]):
            red, green, blue = rgb_pixels[x, y]
            if min(abs(red - 255), abs(green - 255), abs(blue - 255)) > (
                255 - _WHITE_THRESHOLD
            ):
                mask_pixels[x, y] = 255
    return mask


# Input: Quellbild, Maske, Tintenfarbe und Hintergrundmodus.
# Output: Normalisiertes RGBA-Bild.
# Die Funktion ersetzt Farbvarianz der Rohgenerierung durch die vereinbarten
# v1-Farbklassen und bewahrt Transparenz beziehungsweise weissen Hintergrund.
def _normalize_rgba(source, mask, ink_color, background):
    # type: (Image.Image, Image.Image, str, str) -> Image.Image
    if background == "white":
        base = Image.new("RGBA", source.size, (255, 255, 255, 255))
    else:
        base = Image.new("RGBA", source.size, (0, 0, 0, 0))

    ink_layer = Image.new("RGBA", source.size, _INK_RGB[ink_color] + (255,))
    return Image.composite(ink_layer, base, mask)

