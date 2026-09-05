import time
import random
from encodings.base64_codec import base64_decode
from typing import Dict, Any, List, Optional
from scrapers.base_scraper import BaseScraper
from playwright.sync_api import sync_playwright, BrowserContext, Playwright, expect


class BamaScraper(BaseScraper):
    def __init__(self,
                 base_url: str = "https://bama.ir",
                 scraped_links_cache: Optional[set] = None,
                 headless: bool = True):
        super().__init__()
        self.base_url = base_url
        self.scraped_links_cache = scraped_links_cache or set()
        self.headless = headless

    def _init_context(self, p: Playwright) -> BrowserContext:
        browser = p.chromium.launch(channel="chrome", headless=self.headless)
        return browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="fa-IR",
        )

    def search(self, search_url: str, target_quota: int = 200) -> List[str]:
        collected: List[Dict[str, Any]] = []
        seen_ids = set()

        with sync_playwright() as p:
            context = self._init_context(p)
            page = context.new_page()
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1800)

            no_new_streak = 0
            no_height_change_streak = 0
            last_height = 0

            while len(collected) < target_quota:
                cards = page.query_selector_all('article a[href^="/car/detail-"]')
                before_count = len(collected)

                for card in cards:
                    href = card.get_attribute("href")
                    if not href:
                        continue

                    listing_id = _extract_bama_id(href)
                    if not listing_id or listing_id in seen_ids or listing_id in self.scraped_links_cache:
                        continue

                    seen_ids.add(listing_id)

                    expected_count = None
                    badge = page.query_selector(".absolute.bottom-2.left-2 span")
                    if badge:
                        badge_text = badge.inner_text().strip()
                        if badge_text.isdigit():
                            expected_count = int(badge_text)

                    collected.append({
                        "url": href,
                        "listing_id": listing_id,
                        "expected_photo_count": expected_count,
                    })

                    if len(collected) >= target_quota:
                        break

                if len(collected) == before_count:
                    no_new_streak += 1
                else:
                    no_new_streak = 0

                current_height = page.evaluate("document.body.scrollHeight")
                page.evaluate("window.scrollBy(0, 900)")
                page.wait_for_timeout(int(random.uniform(1500, 2500)))

                if current_height == last_height:
                    no_height_change_streak += 1
                else:
                    no_height_change_streak = 0
                last_height = current_height

                if no_new_streak >= 5 and no_height_change_streak >= 3:
                    break

            context.close()

        return collected

    def extract_listing(self, listing_url: str, retries: int = 3) -> Dict[str, Any]:
        full_url = f"{self.base_url}{listing_url}" if listing_url.startswith("/") else listing_url
        listing_id = _extract_bama_id(listing_url) or listing_url

        data = None
        for attempt in range(1, retries+1):
            data = self._extract_listing_once(full_url, listing_id)
            if data["images"]:
                return data
            time.sleep(1.5 * attempt)

        return data

    def _extract_listing_once(self, full_url: str, listing_id: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "listing_id": listing_id,
            "source_url": full_url,
            "declared_model": None,
            "declared_color": None,
            "expected_photo_count": None,
            "images": [],
        }

        with sync_playwright() as p:
            context = self._init_context(p)
            page = context.new_page()

            try:
                page.goto(full_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_selector("h1", timeout=10000)
            except Exception as e:
                print(f"Failed to load page: {full_url} -> {e}")
                context.close()
                return data

            h1 = page.query_selector("h1")
            trim_span = page.query_selector("h1 + span")

            model_parts = []
            if h1:
                model_parts.append(" ".join(h1.inner_text().split()))
            if trim_span:
                trim_text = " ".join(trim_span.inner_text().split())
                if trim_text:
                    model_parts.append(trim_text)

            data["declared_model"] = " ".join(model_parts) if model_parts else None

            spec_blocks = page.query_selector_all(".flex.flex-col.items-center.gap-2")
            for block in spec_blocks:
                spans = block.query_selector_all("span")
                if len(spans) >= 2:
                    label = spans[0].inner_text().strip()
                    value = spans[1].inner_text().strip()
                    if label == "رنگ بدنه":
                        data["declared_color"] = value
                        break

            all_carousels = page.query_selector_all(".carousel")
            main_carousel = all_carousels[0] if all_carousels else None

            img_urls: List[str] = []
            seen_urls = set()

            def collect_current():
                if not main_carousel:
                    return
                imgs = main_carousel.query_selector_all("img[data-nuxt-img]")
                for img in imgs:
                    url = _best_srcset_url(img)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        img_urls.append(url)

            collect_current()

            if main_carousel:
                dot_buttons = main_carousel.query_selector_all(".absolute.bottom-4 button")
                total_slides = len(dot_buttons) if dot_buttons else 1
                data["expected_photo_count"] = total_slides if total_slides > 1 else None

                next_button = main_carousel.query_selector("button.absolute.end-4")

                if next_button and total_slides > 1:
                    for _ in range(total_slides - 1):
                        try:
                            next_button.click()
                        except Exception:
                            break
                        page.wait_for_timeout(500)
                        collect_current()

            data["images"] = img_urls

            if data["expected_photo_count"] and len(img_urls) < data["expected_photo_count"]:
                print(f"Ads {listing_id}: Expected {data['expected_photo_count']} but got {len(img_urls)}")

            context.close()

        return data


def _extract_bama_id(href: str) -> Optional[str]:
    # href: /car/detail-56z2rs8m-renault-tondar90-e2-1392  =>  56z2rs8m
    marker = "detail-"
    idx = href.find(marker)
    if idx == -1:
        return None
    rest = href[idx + len(marker):]
    return rest.split("-")[0] if rest else None


def _best_srcset_url(img) -> Optional[str]:
    srcset = img.get_attribute("srcset")
    if srcset:
        candidates = []
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            bits = part.rsplit(" ", 1)

            url = bits[0].strip()
            if not (url.startswith("http://") or url.startswith("https://") or url.startswith("//")):
                continue

            width = 0
            if len(bits) == 2 and bits[1].endswith("w"):
                try:
                    width = int(bits[1][:-1])
                except ValueError:
                    width = 0

            candidates.append((width, url))

        if candidates:
            candidates.sort(key=lambda c: c[0])
            best_url = candidates[-1][1]
            if best_url.startswith("//"):
                best_url = "https:" + best_url
            return best_url

    src = img.get_attribute("src")
    if src and (src.startswith("http://") or src.startswith("https://") or src.startswith("//")):
        if src.startswith("//"):
            src = "https:" + src
        return src

    return None