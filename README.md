# Iranian Car Dataset Collector

A scraping pipeline that collects images of Iranian car models (currently **Renault Tondar 90 / L90**, with **Pikan Vanet** support ready to configure) from **Divar** and **Bama**, the two largest classified-ads marketplaces in Iran. Built for assembling a labeled image dataset — collection, quality filtering, and deduplication are automated; final curation is left to a human reviewer.

## Features

- 🔍 **Dual-source scraping** — dedicated adapters for Divar and Bama behind a shared interface, so both feed the same downstream pipeline
- 🎯 **Color-balanced collection** — searches are split per color (white / black / silver) using each site's native filters, so no single color dominates the dataset
- 🧠 **Metadata-driven filtering** — accepts images based on the seller-declared model/color fields on each listing, not guesswork
- 🔁 **Resumable** — every processed listing is recorded in a local state file, so interrupted runs pick up where they left off without re-downloading anything
- 🧹 **Automatic quality control** — resolution/blur filtering and perceptual-hash deduplication run after every collection pass
- 🖼️ **Optional CLIP-based visual filter** — flags images that likely don't contain the target car for review (off by default)
- 🛠️ **Utility scripts** — e.g. bulk WebP → JPG conversion for downstream tooling compatibility

## Project Structure

```
divar_project/
├── config/
│   ├── divar_config.py       # Per-model, per-color Divar search URLs + quota
│   └── bama_config.py        # Per-model, per-color Bama search URLs + quota
├── scrapers/
│   ├── base_scraper.py       # Shared interface every site adapter implements
│   ├── divar_scraper.py      # Divar adapter (Playwright-driven)
│   └── bama_scraper.py       # Bama adapter (Playwright-driven)
├── pipeline/
│   ├── manifest.py           # De-dup state + manifest.csv writer
│   ├── downloader.py         # Image download with retries
│   ├── dedupe.py             # Perceptual-hash duplicate detection
│   ├── quality_filter.py     # Resolution + blur filtering
│   └── vision_filter.py      # Optional CLIP-based sanity filter
├── scripts/
│   ├── run_divar_collection.py
│   └── run_bama_collection.py
├── output/                   # Downloaded images land here (git-ignored)
├── state/                    # scraped_links.json + manifest.csv (git-ignored)
└── requirements.txt
```

## Installation

```bash
pip install -r requirements.txt --break-system-packages
playwright install chromium
```

## Configuration

Before running, open `config/divar_config.py` and `config/bama_config.py` and fill in the search URLs for each model/color combination. Each site exposes native filters for model and color — grab the filtered URL directly from the site rather than relying on free-text search, since that's what makes per-color quotas and model accuracy reliable.

```python
DIVAR_QUERIES = {
    "L90": {
        "white": "https://divar.ir/s/iran/car/renault/tondar-90?...&color=...",
        "black": "https://divar.ir/s/iran/car/renault/tondar-90?...&color=...",
        "silver": "https://divar.ir/s/iran/car/renault/tondar-90?...&color=...",
    },
    "Pikan_Vanet": { ... },
}
```

`TARGET_PER_COLOR` controls how many raw listings are pulled per color (default: 240, aiming for ~700 raw images per model across three colors after accounting for multi-photo listings).

## Usage

Run one of python files:

```bash
python -m scripts.run_divar_collection
python -m scripts.run_bama_collection
```

Each run will:

1. Search listings per model/color, respecting the configured quota
2. Skip any listing already recorded as processed in `state/scraped_links.json`
3. Visit each new listing, extract the declared model/color and full-resolution image URLs
4. Download images into `output/<model>/raw/`
5. Log one row per image in `state/manifest.csv`
6. Run quality filtering (resolution + blur) and deduplication (perceptual hashing) on the raw folder

Interrupted mid-run? Just re-run the same command — completed listings are skipped automatically.

## Manual Review (required)

Automated filtering only removes clear failures (low-res, blurry, duplicate). It does **not** replace a human pass. After each model finishes, review `output/<model>/raw/` and:

1. Confirm quality and environment diversity (street, lot, showroom, etc.)
2. Confirm angle diversity (front, rear, side, three-quarter)
3. Confirm color balance across the three target colors
4. Move the final curated set (typically 500 images) into `output/<model>/images/`

That `images/` folder is the deliverable structure — no labels or `.txt` files needed at this stage.

## Optional: CLIP-based Visual Filter

`pipeline/vision_filter.py` can flag images that likely don't show the target car, using CLIP zero-shot classification. It's not wired into the default run — install its dependencies first if you want it:

```bash
pip install open_clip_torch torch --break-system-packages
```

```python
from pipeline import vision_filter

vision_filter.flag_folder(
    raw_dir,
    positive_prompt="a photo of a Renault Tondar 90 (L90) car",
    negative_prompts=["a photo of a car interior", "a photo with no car in it"],
)
```

Flagged images are moved to `_flagged_for_review/`, never deleted outright.

## Utility: WebP → JPG Conversion

Both source sites serve images as WebP. If your downstream tooling needs JPG:

```bash
python scripts/convert_webp_to_jpg.py output/L90/images
python scripts/convert_webp_to_jpg.py output/L90/images --quality 90 --delete-original
```

Transparent WebP images are flattened onto a white background before saving (JPG has no alpha channel).

## Notes & Troubleshooting

- Both scrapers run headless by default (`headless=True`) for speed. Set `headless=False` when debugging to watch the browser interact with the page.
- Randomized delays are used between scrolls/clicks to keep behavior less bot-like. If you hit CAPTCHAs or blocks, lower `TARGET_PER_COLOR` and space out runs.
- Both sites virtualize their listing feeds (off-screen cards are unmounted from the DOM), so links are collected incrementally during scrolling rather than read once at the end — don't "simplify" this without re-testing, it's load-bearing.
- `state/` and `output/` are meant to be local working directories — exclude them from version control.
