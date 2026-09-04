import sys
from pathlib import Path
from datetime import datetime
from config.divar_config import TARGET_PER_COLOR, QUERIES
from scrapers.divar_scraper import DivarScraper
from pipeline.manifest import ManifestStore
from pipeline.downloader import download_images_for_listing
from pipeline import quality_filter, dedupe

sys.path.append(str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / 'output'


def run_for_model(model_name: str, color_queries: dict, manifest: ManifestStore):
    raw_dir = OUTPUT_ROOT / model_name / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    scraper = DivarScraper(scraped_links_cache=manifest.scraped_ids, headless=False)

    for color_name, url in color_queries.items():
        if not url:
            print(f"Skipped ({model_name}/{color_name}): Link not yet defined in config")
            continue

        print(f"\n=== {model_name} / {color_name} ===")
        listings = scraper.search(url, target_quota=TARGET_PER_COLOR)
        print(f"{len(listings)} new (unique) listings found.")

        for item in listings:
            listing_id = item['listing_id']

            if manifest.is_done(listing_id):
                continue

            print(f"Processing listing {listing_id} ...")
            details = scraper.extract_listing(item["url"])

            if not details["images"]:
                print("No images found, skipped.")
                manifest.mark(listing_id, status="failed", model=model_name, color_query=color_name)
                continue

            saved_paths = download_images_for_listing(details["images"], listing_id, raw_dir)

            rows = [
                {
                    "filename": path.name,
                    "listing_id": listing_id,
                    "source": "divar",
                    "model_name": model_name,
                    "declared_model": details.get("declared_model") or "",
                    "declared_color": details.get("declared_color") or "",
                    "query_model": model_name,
                    "query_color": color_name,
                    "source_url": details["source_url"],
                    "photo_count_expected": details.get("expected_photo_count") or "",
                    "photo_count_downloaded": len(saved_paths),
                    "scraped_at": datetime.now().isoformat(timespec="seconds"),
                }
                for path in saved_paths
            ]

            manifest.append_rows(rows)
            manifest.mark(listing_id, status="done", model=model_name, color_query=color_name, image_count=len(saved_paths))
            print(f"{len(saved_paths)} photos downloaded.")

    print(f"\n--- Quality filtering on {raw_dir} ---")
    quality_filter.filter_folder(raw_dir)

    print(f"--- Deduplication on {raw_dir} ---")
    dedupe.dedupe_folder(raw_dir)

    print(f"\n✅ {model_name} finished. Remaining images in {raw_dir} are ready for manual review.")

def main():
    manifest = ManifestStore(project_dir=str(PROJECT_ROOT / "state"))

    for model_name, color_queries in QUERIES.items():
        run_for_model(model_name, color_queries, manifest)

    print("\nAll models processed.")


if __name__ == "__main__":
    main()