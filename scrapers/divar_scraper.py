import time
import random
from playwright.sync_api import Playwright
from typing import List, Dict, Any, Optional
from playwright.sync_api import sync_playwright, BrowserContext
from scrapers.base_scraper import BaseScraper
from utils.utils import fa_to_en_digits


class DivarScraper(BaseScraper):
    def __init__(self,
                 base_url: str = "https://divar.ir",
                 scraped_links_cache: Optional[str] = None,
                 headless: bool = True):
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
            locale="fa-IR"
        )

    def search(self, search_url: str, target_quota: int = 200) -> list[dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        seen_ids = set()

        with sync_playwright() as p:
            context = self._init_context(p)
            page = context.new_page()
            page.goto(self.base_url)
            page.wait_for_timeout(1500)

            no_new_links_streak = 0
            max_stall_retries = 4

            while len(collected) < target_quota:
                cards = page.query_selector_all("a.kt-post-card__action")
                before_count = len(collected)

                for card in cards:
                    href = card.get_attribute("href")
                    if not href:
                        continue

                    listing_id = href.rstrip("/").split("/")[-1]
                    if listing_id in seen_ids or listing_id in self.scraped_links_cache:
                        continue

                    seen_ids.add(listing_id)

                    expected_count = None
                    badge = card.query_selector(".kt-post-card-thumbnail__badge .kt-tag__text")

                    if badge:
                        expected_count = fa_to_en_digits(badge.inner_text().strip())

                    collected.append({
                        "url": href,
                        "listing_id": listing_id,
                        "expected_photo_count": expected_count,
                    })

                    if len(collected) >= target_quota:
                        break

                if len(collected) == before_count:
                    no_new_links_streak += 1
                else: no_new_links_streak = 0

                page.evaluate("window.scrollBy(0, 900)")
                page.wait_for_timeout(int(random.uniform(1200, 2200)))

                if no_new_links_streak >= 3:
                    load_more_btn = page.query_selector("button.post-list__load-more-btn-be092")
                    if load_more_btn and load_more_btn.is_visible():
                        try:
                            load_more_btn.click()
                            page.wait_for_timeout(int(random.uniform(1200, 2200)))
                            no_new_links_streak = 0
                            max_stall_retries -= 1
                        except Exception:
                            break
                    else:
                        break

                    if max_stall_retries <= 0:
                        break

            context.close()

        return collected

    def extract_listing(self, listing_url: str, retries: int = 3) -> Dict[str, Any]:
        full_url = (f"{self.base_url}/{listing_url}" if listing_url.startswith("/") else listing_url)
        listing_id = listing_url.rstrip("/").split("/")[-1]

        data = None
        for attempt in range(1, retries + 1):
            data = self._extract_listing_once(full_url, listing_id)
            if data['images']:
                return data
            time.sleep(1.5 * attempt)
            
        return data

    def _extract_listing_once(self, full_url: str, listing_id: str):
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
                page.wait_for_selector("article", timeout=10000)
            except Exception as e:
                print(f"Page load failed for {listing_id}: {e}")
                context.close()
                return data

            headers = page.query_selector_all(".kt-group-row__header .kt-group-row-item__title")
            values = page.query_selector_all(".kt-group-row__data-row .kt-group-row-item__value")

            header_text = [h.inner_text().strip() for h in headers]
            value_text = [v.inner_text().strip() for v in values]

            if "رنگ" in header_text:
                idx = header_text.index("رنگ")
                if idx < len(value_text):
                    data["declared_model"] = value_text[idx]

            model_element = page.query_selector(".kt-unexpandable-row__action")
            if model_element:
                data["declared_model"] = model_element.inner_text().strip()

            count_badge = page.query_selector(".kt-base-carousel__fullscreen-control .kt-tag__text")
            if count_badge:
                data['expected_photo_count'] = fa_to_en_digits(count_badge.inner_text().strip())

            carousel = page.query_selector(".kt-base-carousel")
            if carousel:
                carousel.scroll_into_view_if_needed()
                page.wait_for_timeout(300)

            next_button = page.query_selector('button.kt-base-carousel__control[aria-label="تصویر بعدی"]')

            total_slides = data["expected_photo_count"] or len(page.query_selector_all(".kt-base-carousel__slide"))

            img_urls = []
            seen_urls = set()

            def _collect_current():
                for src in _collect_post_image_urls(page):
                    if not src in seen_urls:
                        seen_urls.add(src)
                        img_urls.append(src)

            _collect_current()

            if next_button and total_slides:
                for _ in range(total_slides - 1):
                    try:
                        next_button.click()
                    except Exception:
                        break

                    try:
                        page.wait_for_function(
                            "document.querySelectorAll("
                            "'.kt-base-carousel__slide-loading-overlay--active'"
                            ").length === 0",
                            timeout=6000,
                        )
                    except Exception:
                        pass

                    page.wait_for_timeout(350)
                    _collect_current()

            extra_attempts = 0
            while (
                data["expected_photo_count"]
                and len(img_urls) < data["expected_photo_count"]
                and next_button
                and extra_attempts < 5
            ):
                try:
                    next_button.click()
                except Exception:
                    break

                page.wait_for_timeout(900)
                _collect_current()
                extra_attempts += 1

            data["images"] = img_urls

            if data["expected_photo_count"] and len(img_urls) < data["expected_photo_count"]:
                print(f"Ads {listing_id}: Expected {data['expected_photo_count']} but got {len(img_urls)}")

            context.close()

        return data

def _collect_post_image_urls(page) -> list:
    img_elements = page.query_selector_all(".kt-base-carousel__slide img")
    img_urls = []
    seen = set()

    for img in img_elements:
        src = img.get_attribute("src")
        if src and "web_post" in src and src not in seen:
            seen.add(src)
            img_urls.append(src)
    return img_urls