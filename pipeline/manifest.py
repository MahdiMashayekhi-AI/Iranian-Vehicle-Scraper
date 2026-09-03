import csv
import json
import threading
from pathlib import Path
from typing import Dict, Any, List


MANIFEST_FIELDNAMES = [
    "filename",
    "listing_id",
    "source",
    "model_name",
    "declared_model",
    "declared_color",
    "query_model",
    "query_color",
    "source_url",
    "photo_count_expected",
    "photo_count_downloaded",
    "scraped_at",
]


class ManifestStore:
    def __int__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)

        self.links_path = self.project_dir / "scraped_links.json"
        self.manifest_path = self.project_dir / "manifest.json"

        self._lock = threading.Lock()
        self._links_cache: Dict[str, Dict[str, Any]] = self._load_links()

        if not self.manifest_path.exists():
            with open(self.manifest_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDNAMES)
                writer.writeheader()

    def _load_links(self) -> Dict[str, Dict[str, Any]]:
        if self.links_path.exists():
            try:
                with open(self.links_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_links(self):
        tmp_path = self.links_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._links_cache, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.links_path)

    @property
    def scraped_ids(self) -> set:
        return {listing_id for listing_id, info in self._links_cache.items() if info.get("status") == "done"}

    def is_done(self, listing_id: str) -> bool:
        info = self._links_cache.get(listing_id)
        return bool(info and info.get("status") == "done")

    def mark(self, listing_id: str, status: str, **extra) -> None:
        with self._lock:
            self._links_cache[listing_id] = {"status": status, **extra}
            self._save_links()

    def append_rows(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        with self._lock:
            with open(self.manifest_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDNAMES)
                for row in rows:
                    clean_row = {k: row.get(k, "") for k in MANIFEST_FIELDNAMES}
                    writer.writerow(clean_row)
