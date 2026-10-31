"""Selected authored colour-pair calculations, supplementary to browser axe checks."""

import json
from pathlib import Path


def luminance(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def test_release_selected_text_palette_contrast():
    pairs = [
        ("body", "#172e40", "#f4f7f9"),
        ("muted", "#496171", "#ffffff"),
        ("button", "#ffffff", "#183b53"),
        ("green", "#23624e", "#e8f4ed"),
        ("amber", "#85520b", "#fff3dc"),
        ("red", "#a1323a", "#fff0f0"),
        ("rail", "#c6d6e1", "#183b53"),
    ]
    results = []
    for label, foreground, background in pairs:
        a, b = sorted([luminance(foreground), luminance(background)])
        ratio = (b + 0.05) / (a + 0.05)
        assert ratio >= 4.5, (label, ratio)
        results.append(
            {
                "pair": label,
                "foreground": foreground,
                "background": background,
                "ratio": round(ratio, 2),
            }
        )
    destination = Path("evidence/rc/accessibility")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "palette.json").write_text(
        json.dumps(
            {
                "kind": "selected authored token pairs, not pixel-complete or WCAG certification",
                "pairs": results,
            },
            indent=2,
        )
        + "\n"
    )
