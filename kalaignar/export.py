"""Stage 7 — Export: write animation strips in the game's convention, a
select-screen portrait, and an asset-ledger row."""

from datetime import date
from pathlib import Path

from . import smear as smear_mod
from .poses import CHARACTER_POSES
from .render import PuppetRenderer
from .segment import Part


def export_character(
    parts: dict[str, Part], character: str, out_dir: Path, artist: str = "team",
    smear: bool = False,
) -> list[Path]:
    """Render every animation for `character` into out_dir. Returns paths.
    Strip names follow the game convention: <anim>@<frames>x<fps>.png.
    smear: add motion trails to non-looping animations (see smear.py)."""
    if character not in CHARACTER_POSES:
        known = ", ".join(sorted(CHARACTER_POSES))
        raise ValueError(f"unknown character '{character}' (have: {known})")
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = PuppetRenderer(parts)
    written: list[Path] = []

    anims = CHARACTER_POSES[character]
    for anim, (fps, loop, poses) in anims.items():
        if smear and not loop:
            strip = smear_mod.render_animation(renderer, poses)
        else:
            strip = renderer.render_animation(poses)
        path = out_dir / f"{anim}@{len(poses)}x{fps}.png"
        strip.save(path)
        written.append(path)

    portrait = renderer.render_frame(anims["idle"][2][0])
    portrait_path = out_dir / "portrait.png"
    portrait.save(portrait_path)
    written.append(portrait_path)

    ledger = out_dir / "ledger_row.md"
    ledger.write_text(
        f"| `assets/sprites/{character}/**` | Sprites | Hand-drawn by {artist}, "
        f"processed by Kalaignar ({date.today().isoformat()}) | Original — created "
        "for this project, all rights ours | No (deterministic tool, no ML) | "
        "Source drawing + this pipeline |\n",
        encoding="utf-8",
    )
    written.append(ledger)
    return written
