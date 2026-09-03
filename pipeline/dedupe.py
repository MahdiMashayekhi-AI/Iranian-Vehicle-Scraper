import shutil
import imagehash
from pathlib import Path
from typing import List
from PIL import Image
from numpy.f2py.auxfuncs import isintent_dict

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']


def compute_phash(image_path: Path):
    try:
        with Image.open(image_path) as image:
            return imagehash.phash(image)
    except Exception as e:
        print(f"Error: {e}")
        return None

def dedupe_folder(image_dir: Path, threshold: int = 5) -> List[Path]:
    image_dir = Path(image_dir)
    duplicates_dir = image_dir / '_duplicates'
    duplicates_dir.mkdir(exist_ok=True)

    image_files = [p for p in image_dir.iterdir() if p.is_file() and p.suffix in IMAGE_EXTENSIONS]

    hashes = {}
    moved: List[Path] = []

    for path in image_files:
        h = compute_phash(path)
        if h is None:
            continue

        is_duplicate = False
        for existing_hash in hashes:
            if h - existing_hash <= threshold:
                is_duplicate = True
                break

        if is_duplicate:
            dest = duplicates_dir / path.name
            shutil.move(str(path), str(dest))
            moved.append(dest)
        else:
            hashes[h] = path

    print(f"Deduping {len(hashes)} images")
    return moved