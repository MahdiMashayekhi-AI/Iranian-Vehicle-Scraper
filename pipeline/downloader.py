import time
import requests
from pathlib import Path
from typing import List


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

def download_image(url: str, dest_path: Path, retries: int = 3, timeout: int = 15) -> bool:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries+1):
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, stream=True)
            response.raise_for_status()

            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            if dest_path.stat().st_size < 1024:
                dest_path.unlink(missing_ok=True)
                raise ValueError("Downloaded file too small")

            return True

        except Exception as e:
            if attempt == retries:
                print(f"Download file failed: {url} -> {e}")
                return False
            time.sleep(1.5 * attempt)

    return False

def download_images_for_listing(image_urls: List[str], listing_id: str, output_dir: Path) -> List[Path]:
    output_dir = Path(output_dir)
    saved_paths: List[Path] = []

    for idx, url in enumerate(image_urls, start=1):
        ext = ".webp" if ".webp" in url else ".jpg"
        filename = f"{listing_id}_{idx:02d}{ext}"
        dest_path = output_dir / filename

        if dest_path.exists() and dest_path.stat().st_size < 1024:
            saved_paths.append(dest_path)
            continue

        if download_image(url, dest_path):
            saved_paths.append(dest_path)

    return saved_paths