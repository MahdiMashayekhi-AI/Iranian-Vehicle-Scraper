import cv2
import shutil
from pathlib import Path
from typing import List, Tuple
from PIL import Image


IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]

MIN_WIDTH = 720
MIN_HEIGHT = 720
BLUR_THRESHOLD = 100


def check_resolution(image_path: Path) -> bool:
    try:
        with Image.open(image_path) as image:
            width, height = image.size
            return width >= MIN_WIDTH and height >= MIN_HEIGHT
    except Exception:
        return False


def check_blur(image_path: Path) -> Tuple[bool, float]:
    image = cv2.imread(str(image_path))
    if image is None:
        return False, 0.0

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()

    return variance < BLUR_THRESHOLD, variance


def filter_folder(image_dir: Path) -> List[Path]:
    image_dir = Path(image_dir)
    rejected_dir = image_dir / "_rejected"
    rejected_dir.mkdir(exist_ok=True)

    image_files = [p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]

    rejected: List[Path] = []

    for path in image_files:
        reason = None
        if not check_resolution(path):
            reason = "resolution"
        else:
            is_sharp, variance = check_blur(path)
            if not is_sharp:
                reason = f"blur(var={variance:.1f})"

        if reason:
            dest_path = rejected_dir / path.name
            shutil.move(str(path), str(dest_path))
            rejected.append(dest_path)
            print(f"Failed for {reason}: {path.name}")

    print(f"Quality filtering complete for {len(rejected)} images.")
    return rejected