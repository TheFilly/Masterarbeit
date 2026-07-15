"""Image normalization and ink-mask generation for handwriting assets."""


from PIL import Image

_WHITE_THRESHOLD = 245
_ALPHA_CUTOFF = 8
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


# Input: `image` als Generatorausgabe und Hintergrundmodus.
# Output: L-Modus-Alpha-Maske mit erhaltener Tintenintensitaet.
# Transparente Assets bewahren vorhandene Alpha-Werte. Graue ScrabbleGAN-
# Ausgaben ohne Alpha werden ueber die Weissdistanz in eine weiche Alpha-Maske
# umgerechnet, damit Anti-Aliasing nicht als harte Schwarzflaeche endet.
def _build_mask(image, background):
    # type: (Image.Image, str) -> Image.Image
    if "A" in image.getbands():
        alpha = image.getchannel("A")
        alpha_min, alpha_max = alpha.getextrema()
        if alpha_min < alpha_max or alpha_max < 255:
            return alpha.point(lambda value: value if value > _ALPHA_CUTOFF else 0)

    grayscale = image.convert("L")
    return grayscale.point(_grayscale_to_alpha)


# Input: `value` als Graustufenwert zwischen 0 und 255.
# Output: Alpha-Wert mit niedrigen Werten fuer weisse Flaechen.
# Die Funktion bildet Dunkelheit weich auf Alpha ab und unterdrueckt nur sehr
# schwache Hintergrundabweichungen, damit Graustufen und Kanten erhalten bleiben.
def _grayscale_to_alpha(value):
    # type: (int) -> int
    if value >= _WHITE_THRESHOLD:
        return 0
    alpha = int(((_WHITE_THRESHOLD - value) * 255) / _WHITE_THRESHOLD)
    return alpha if alpha > _ALPHA_CUTOFF else 0


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
