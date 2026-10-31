"""Generate the bundled region icons (run once; committed with the project)."""
from pathlib import Path

COLORS = {
    "eu": "#1a4fd6",
    "europe": "#2f6fed",
    "north_america": "#0a7d3c",
    "latam": "#b35a00",
    "mena": "#a03bb5",
    "africa": "#c45a00",
    "asia_pacific": "#0071e3",
    "worldwide": "#6e6e73",
}

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" role="img" aria-hidden="true">'
    '<rect width="48" height="48" rx="12" fill="{color}1a"/>'
    '<g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round">'
    '<circle cx="24" cy="24" r="12"/>'
    '<ellipse cx="24" cy="24" rx="5.5" ry="12"/>'
    '<path d="M12 24h24M13.8 18h20.4M13.8 30h20.4"/>'
    "</g></svg>"
)


def main() -> None:
    target = Path(__file__).resolve().parent.parent / "static" / "regions"
    target.mkdir(parents=True, exist_ok=True)
    for name, color in COLORS.items():
        (target / f"{name}.svg").write_text(SVG.format(color=color), encoding="utf-8")
    print(f"wrote {len(COLORS)} region icons to {target}")


if __name__ == "__main__":
    main()
