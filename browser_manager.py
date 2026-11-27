"""Async Playwright session manager for Parivahan eChallan automation.

Maintains a single BrowserContext and Page per Telegram user conversation so
session cookies persist across Stage 1 (Vehicle Lookup), Stage 2 (Table
Screenshot & Challan Extraction), and Stage 3 (Sequential PDF Download Loop).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Download,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    Response,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from selectors import (
    ACCUSED_CHALLAN_URL,
    ACCUSED_SELECTORS,
    CHALLAN_PRINT_URL,
    DISPOSED_STATUS_PHRASES,
    INVALID_CAPTCHA_PHRASES,
    NO_CHALLAN_PHRASES,
    PRINT_SELECTORS,
)

logger = logging.getLogger(__name__)

WINDOWS_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

VIEWPORT_CONFIG = {"width": 1366, "height": 768}

STEALTH_INIT_SCRIPT = """
() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
  Object.defineProperty(navigator, 'plugins', {
    get: () => [
      { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
      { name: 'Native Client', filename: 'internal-nacl-plugin' }
    ]
  });
  window.chrome = window.chrome || { runtime: {} };
  const originalQuery = window.navigator.permissions?.query;
  if (originalQuery) {
    window.navigator.permissions.query = (parameters) =>
      parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
  }
}
"""

# Matches standard Indian eChallan numbers (e.g., OD1234567890123456, DL24010123456789)
CHALLAN_NUMBER_REGEX = re.compile(r"\b[A-Z]{2}[A-Z0-9]{0,4}\d{8,18}\b")


@dataclass
class VehicleLookupResult:
    """Outcome of submitting Stage 2 CAPTCHA on /index/accused-challan."""

    status: Literal["ok", "invalid_captcha", "no_challans", "error"]
    screenshot_bytes: bytes | None = None
    captcha_bytes: bytes | None = None
    pending_challans: list[str] = field(default_factory=list)
    total_rows_found: int = 0
    message: str = ""


@dataclass
class PrintDownloadResult:
    """Outcome of submitting Stage 3 CAPTCHA on /index/challan-print."""

    status: Literal["ok", "invalid_captcha", "error"]
    pdf_path: Path | None = None
    captcha_bytes: bytes | None = None
    message: str = ""


def parse_proxy_url(proxy_url: str | None) -> dict[str, str] | None:
    """Parse an optional PROXY_URL into Playwright's proxy configuration dict."""
    if not proxy_url or not proxy_url.strip():
        return None
    parsed = urlparse(proxy_url.strip())
    if not parsed.scheme or not parsed.hostname:
        logger.warning("Ignoring malformed PROXY_URL (missing scheme or host).")
        return None
    port_suffix = f":{parsed.port}" if parsed.port else ""
    config: dict[str, str] = {"server": f"{parsed.scheme}://{parsed.hostname}{port_suffix}"}
    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password
    return config


def sanitize_filename_token(raw_value: str) -> str:
    """Sanitize a challan number for safe use in /tmp/<CHALLAN_NO>.pdf."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", raw_value.strip())
    return cleaned or "challan_receipt"


class ParivahanBrowserSession:
    """Stateful async Playwright session persisted inside context.user_data."""

    def __init__(
        self,
        headless: bool = True,
        proxy_url: str | None = None,
        navigation_timeout_ms: int = 45_000,
    ) -> None:
        self.headless = headless
        self.proxy_url = proxy_url
        self.navigation_timeout_ms = navigation_timeout_ms

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def start(self) -> None:
        """Launch headless Chromium with stealth settings and create BrowserContext + Page."""
        async with self._lock:
            if self.page is not None and not self._closed:
                return

            self._closed = False
            self._playwright = await async_playwright().start()

            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--window-size=1366,768",
            ]

            launch_kwargs: dict[str, Any] = {
                "headless": self.headless,
                "args": launch_args,
            }
            proxy_config = parse_proxy_url(self.proxy_url)
            if proxy_config:
                launch_kwargs["proxy"] = proxy_config
                logger.info("Launching Chromium via proxy server: %s", proxy_config["server"])

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            self.context = await self._browser.new_context(
                viewport=VIEWPORT_CONFIG,
                user_agent=WINDOWS_CHROME_UA,
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                accept_downloads=True,
                ignore_https_errors=True,
                extra_http_headers={
                    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            await self.context.add_init_script(STEALTH_INIT_SCRIPT)
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.navigation_timeout_ms)
            self.page.set_default_navigation_timeout(self.navigation_timeout_ms)

    async def close(self) -> None:
        """Strictly close page, context, browser, and Playwright instance."""
        async with self._lock:
            self._closed = True
            for resource_name, resource, method in (
                ("page", self.page, "close"),
                ("context", self.context, "close"),
                ("browser", self._browser, "close"),
                ("playwright", self._playwright, "stop"),
            ):
                if resource is not None:
                    try:
                        await getattr(resource, method)()
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Ignoring cleanup error for %s: %s", resource_name, exc)
            self.page = None
            self.context = None
            self._browser = None
            self._playwright = None

    def _require_page(self) -> Page:
        if self.page is None or self.context is None or self._closed:
            raise RuntimeError("Playwright session is not active.")
        return self.page

    async def _locate_first(
        self,
        selectors: tuple[str, ...],
        *,
        page: Page | None = None,
        timeout_ms: int = 8_000,
        visible_only: bool = True,
    ) -> Locator:
        """Resolve the first matching selector in an ordered primary/fallback chain."""
        target_page = page or self._require_page()
        per_selector_timeout = max(1_200, timeout_ms // max(len(selectors), 1))
        state = "visible" if visible_only else "attached"

        for selector in selectors:
            locator = target_page.locator(selector).first
            try:
                await locator.wait_for(state=state, timeout=per_selector_timeout)
                return locator
            except PlaywrightTimeoutError:
                continue
            except PlaywrightError:
                continue

        raise RuntimeError(f"Unable to locate any element matching selectors: {selectors[:3]}")

    async def _try_locate_first(
        self,
        selectors: tuple[str, ...],
        *,
        page: Page | None = None,
        timeout_ms: int = 2_500,
        visible_only: bool = True,
    ) -> Locator | None:
        """Best-effort version of _locate_first returning None when absent."""
        try:
            return await self._locate_first(
                selectors,
                page=page,
                timeout_ms=timeout_ms,
                visible_only=visible_only,
            )
        except RuntimeError:
            return None

    async def _capture_captcha_bytes(self, selectors: tuple[str, ...]) -> bytes:
        """Wait for CAPTCHA image rendering and capture a cropped PNG screenshot."""
        page = self._require_page()
        captcha_locator = await self._locate_first(selectors, timeout_ms=15_000)

        # Wait until the <img> has non-zero natural dimensions
        try:
            await captcha_locator.evaluate(
                """(el) => new Promise((resolve) => {
                    if (el.tagName !== 'IMG') return resolve(true);
                    if (el.complete && el.naturalWidth > 0) return resolve(true);
                    const done = () => resolve(true);
                    el.addEventListener('load', done, { once: true });
                    el.addEventListener('error', done, { once: true });
                    setTimeout(done, 4000);
                })"""
            )
        except PlaywrightError:
            pass

        await captcha_locator.scroll_into_view_if_needed()
        return await captcha_locator.screenshot(type="png")

    async def _dismiss_blocking_dialogs(self, page: Page) -> None:
        """Close modal/SweetAlert overlays if Parivahan displays one after error."""
        dismiss_selectors = (
            ".swal2-confirm",
            "button.confirm",
            ".bootbox-accept",
            ".modal.show button:has-text('OK')",
            ".modal.in button:has-text('OK')",
            ".modal.show button.close",
        )
        btn = await self._try_locate_first(dismiss_selectors, page=page, timeout_ms=1_200)
        if btn is not None:
            try:
                await btn.click(timeout=2_000)
                await page.wait_for_timeout(300)
            except PlaywrightError:
                pass

    async def _collect_notice_text(self, page: Page, error_selectors: tuple[str, ...]) -> str:
        """Gather visible error/toast/alert messages from the current page."""
        fragments: list[str] = []
        for selector in error_selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                for idx in range(min(count, 4)):
                    item = loc.nth(idx)
                    if await item.is_visible():
                        text = (await item.inner_text()).strip()
                        if text:
                            fragments.append(text)
            except PlaywrightError:
                continue
        return " | ".join(fragments)

    # -------------------------------------------------------------------------
    # Stage 1: Vehicle Lookup Setup
    # -------------------------------------------------------------------------
    async def open_vehicle_lookup(self, vehicle_number: str) -> bytes:
        """Navigate to /index/accused-challan, select Vehicle Number tab, fill input, return CAPTCHA."""
        await self.start()
        page = self._require_page()

        logger.info("Navigating to %s for vehicle %s", ACCUSED_CHALLAN_URL, vehicle_number)
        await page.goto(ACCUSED_CHALLAN_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=12_000)
        except PlaywrightTimeoutError:
            pass

        # Select "Vehicle Number" tab/radio button
        vehicle_tab = await self._try_locate_first(
            ACCUSED_SELECTORS.vehicle_tab,
            timeout_ms=10_000,
            visible_only=False,
        )
        if vehicle_tab is not None:
            try:
                await vehicle_tab.click(force=True)
            except PlaywrightError:
                await vehicle_tab.dispatch_event("click")
            await page.wait_for_timeout(400)

        # Enter normalized vehicle registration number
        vehicle_input = await self._locate_first(ACCUSED_SELECTORS.vehicle_input, timeout_ms=12_000)
        await vehicle_input.click()
        await vehicle_input.fill("")
        await vehicle_input.fill(vehicle_number)

        return await self._capture_captcha_bytes(ACCUSED_SELECTORS.captcha_image)

    async def refresh_captcha(self, stage: Literal["list", "print"]) -> bytes:
        """Click the portal's CAPTCHA refresh control and return the new cropped PNG."""
        page = self._require_page()
        selectors = ACCUSED_SELECTORS if stage == "list" else PRINT_SELECTORS

        await self._dismiss_blocking_dialogs(page)

        previous_bytes: bytes | None = None
        try:
            previous_bytes = await self._capture_captcha_bytes(selectors.captcha_image)
        except Exception:  # noqa: BLE001
            previous_bytes = None

        refresh_btn = await self._try_locate_first(selectors.captcha_refresh, timeout_ms=6_000)
        if refresh_btn is not None:
            await refresh_btn.click(force=True)
            # Wait briefly for image bytes to change
            for _ in range(10):
                await page.wait_for_timeout(350)
                new_bytes = await self._capture_captcha_bytes(selectors.captcha_image)
                if previous_bytes is None or new_bytes != previous_bytes:
                    return new_bytes
            return await self._capture_captcha_bytes(selectors.captcha_image)

        # Fallback: trigger cache-busting src reload on the CAPTCHA <img>
        img = await self._locate_first(selectors.captcha_image, timeout_ms=8_000)
        await img.evaluate(
            """(el) => {
                if (el.src) {
                    const sep = el.src.includes('?') ? '&' : '?';
                    el.src = el.src.split('&_ts=')[0] + sep + '_ts=' + Date.now();
                }
            }"""
        )
        await page.wait_for_timeout(800)
        return await self._capture_captcha_bytes(selectors.captcha_image)

    # -------------------------------------------------------------------------
    # Stage 2: Submit CAPTCHA, Capture Full-Page Table Screenshot, Extract Queue
    # -------------------------------------------------------------------------
    async def submit_vehicle_captcha(self, captcha_text: str) -> VehicleLookupResult:
        """Submit Stage 1/2 CAPTCHA, check for errors, screenshot results, and parse Pending Challans."""
        page = self._require_page()

        captcha_input = await self._locate_first(ACCUSED_SELECTORS.captcha_input, timeout_ms=10_000)
        await captcha_input.click()
        await captcha_input.fill("")
        await captcha_input.fill(captcha_text.strip())

        submit_btn = await self._locate_first(ACCUSED_SELECTORS.submit_button, timeout_ms=10_000)
        await submit_btn.click()

        # Allow AJAX/form submission to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=12_000)
        except PlaywrightTimeoutError:
            pass
        await page.wait_for_timeout(1_500)

        notice_text = await self._collect_notice_text(page, ACCUSED_SELECTORS.error_banner)
        body_text_lower = (await page.inner_text("body")).lower()
        combined_lower = f"{notice_text.lower()}\n{body_text_lower}"

        # Check for invalid CAPTCHA first
        if any(phrase in notice_text.lower() for phrase in INVALID_CAPTCHA_PHRASES) or any(
            phrase in body_text_lower for phrase in INVALID_CAPTCHA_PHRASES
        ):
            await self._dismiss_blocking_dialogs(page)
            new_captcha = await self._capture_captcha_bytes(ACCUSED_SELECTORS.captcha_image)
            return VehicleLookupResult(
                status="invalid_captcha",
                captcha_bytes=new_captcha,
                message=notice_text or "Invalid CAPTCHA entered.",
            )

        # Check if results table is present
        table = await self._try_locate_first(ACCUSED_SELECTORS.challan_table, timeout_ms=6_000)

        if table is None:
            if any(phrase in combined_lower for phrase in NO_CHALLAN_PHRASES):
                return VehicleLookupResult(
                    status="no_challans",
                    message=notice_text or "No pending challans found.",
                )
            # If notice text exists without a table, surface it cleanly
            if notice_text:
                return VehicleLookupResult(status="error", message=notice_text)
            return VehicleLookupResult(
                status="no_challans",
                message="No pending challan table was returned by Parivahan.",
            )

        # Expand DataTables page length if pagination dropdown exists so screenshot captures all rows
        try:
            length_select = page.locator("select[name*='_length']").first
            if await length_select.is_visible(timeout=1_000):
                options = await length_select.locator("option").all_text_contents()
                for target in ("100", "50", "All"):
                    if any(target.lower() in opt.lower() for opt in options):
                        await length_select.select_option(label=target)
                        await page.wait_for_timeout(600)
                        break
        except PlaywrightError:
            pass

        # Capture full-page screenshot of the pending challans table
        await table.scroll_into_view_if_needed()
        screenshot_bytes = await page.screenshot(full_page=True, type="png")

        # Parse table rows for Pending Challan Numbers
        pending_challans, total_rows = await self._extract_pending_challans(page, table)

        if not pending_challans:
            return VehicleLookupResult(
                status="no_challans",
                screenshot_bytes=screenshot_bytes,
                total_rows_found=total_rows,
                message="Challan table loaded, but 0 pending challans were found.",
            )

        return VehicleLookupResult(
            status="ok",
            screenshot_bytes=screenshot_bytes,
            pending_challans=pending_challans,
            total_rows_found=total_rows,
            message=f"Found {len(pending_challans)} pending challan(s).",
        )

    async def _extract_pending_challans(self, page: Page, table: Locator) -> tuple[list[str], int]:
        """Parse the HTML results table to extract all Pending Challan Numbers."""
        parsed: dict[str, Any] = await table.evaluate(
            """(tbl) => {
                const headers = Array.from(tbl.querySelectorAll('thead th, tr:first-child th'))
                    .map((th) => (th.innerText || th.textContent || '').trim().toLowerCase());

                const bodyRows = Array.from(tbl.querySelectorAll('tbody tr'));
                const rows = (bodyRows.length ? bodyRows : Array.from(tbl.querySelectorAll('tr')).slice(1))
                    .map((tr) => {
                        const cells = Array.from(tr.querySelectorAll('td')).map((td) =>
                            (td.innerText || td.textContent || '').trim()
                        );
                        return {
                            cells,
                            rowText: (tr.innerText || tr.textContent || '').trim()
                        };
                    })
                    .filter((r) => r.cells.length > 0);

                return { headers, rows };
            }"""
        )

        headers: list[str] = parsed.get("headers", [])
        rows: list[dict[str, Any]] = parsed.get("rows", [])

        challan_col_idx: int | None = None
        status_col_idx: int | None = None
        for idx, header in enumerate(headers):
            if challan_col_idx is None and "challan" in header and ("no" in header or "number" in header or "id" in header):
                challan_col_idx = idx
            if status_col_idx is None and "status" in header:
                status_col_idx = idx

        pending_challans: list[str] = []
        seen: set[str] = set()

        for row in rows:
            cells: list[str] = row["cells"]
            row_text: str = row["rowText"]
            row_text_lower = row_text.lower()

            # Skip empty DataTables placeholder row ("No data available in table")
            if "no data available" in row_text_lower or "no matching records" in row_text_lower:
                continue

            # Filter out Disposed / Paid / Settled challans
            status_text = (
                cells[status_col_idx].lower()
                if status_col_idx is not None and status_col_idx < len(cells)
                else row_text_lower
            )
            if any(disposed in status_text for disposed in DISPOSED_STATUS_PHRASES):
                continue

            candidate: str | None = None
            if challan_col_idx is not None and challan_col_idx < len(cells):
                cell_val = cells[challan_col_idx].strip()
                match = CHALLAN_NUMBER_REGEX.search(cell_val.upper())
                if match:
                    candidate = match.group(0)
                elif re.fullmatch(r"[A-Za-z0-9/-]{8,30}", cell_val):
                    candidate = cell_val.upper()

            if not candidate:
                match = CHALLAN_NUMBER_REGEX.search(row_text.upper())
                if match:
                    candidate = match.group(0)

            if candidate and candidate not in seen:
                seen.add(candidate)
                pending_challans.append(candidate)

        return pending_challans, len(rows)

    # -------------------------------------------------------------------------
    # Stage 3: Challan Print Navigation & PDF Capture
    # -------------------------------------------------------------------------
    async def open_challan_print(self, challan_no: str) -> bytes:
        """Navigate to /index/challan-print using persisted session cookies and capture CAPTCHA."""
        page = self._require_page()

        logger.info("Navigating to %s for challan %s", CHALLAN_PRINT_URL, challan_no)
        await page.goto(CHALLAN_PRINT_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=12_000)
        except PlaywrightTimeoutError:
            pass

        # Click Challan Number radio tab if present
        challan_tab = await self._try_locate_first(
            PRINT_SELECTORS.challan_tab,
            timeout_ms=2_000,
            visible_only=False,
        )
        if challan_tab is not None:
            try:
                await challan_tab.click(force=True)
            except PlaywrightError:
                pass

        challan_input = await self._locate_first(PRINT_SELECTORS.challan_input, timeout_ms=12_000)
        await challan_input.click()
        await challan_input.fill("")
        await challan_input.fill(challan_no)

        return await self._capture_captcha_bytes(PRINT_SELECTORS.captcha_image)

    async def submit_print_captcha_and_download(
        self,
        challan_no: str,
        captcha_text: str,
        tmp_dir: str = "/tmp",
    ) -> PrintDownloadResult:
        """Submit Stage 3 CAPTCHA and save the generated challan PDF to /tmp/<CHALLAN_NO>.pdf."""
        page = self._require_page()
        context = self.context
        assert context is not None

        safe_token = sanitize_filename_token(challan_no)
        pdf_path = Path(tmp_dir) / f"{safe_token}.pdf"
        if pdf_path.exists():
            pdf_path.unlink(missing_ok=True)

        captured_pdf_bytes: list[bytes] = []

        async def _on_response(response: Response) -> None:
            try:
                content_type = (response.headers.get("content-type") or "").lower()
                if "application/pdf" in content_type and response.status == 200:
                    body = await response.body()
                    if body.startswith(b"%PDF"):
                        captured_pdf_bytes.append(body)
            except Exception:  # noqa: BLE001
                pass

        context.on("response", _on_response)
        popup_page: Page | None = None

        try:
            captcha_input = await self._locate_first(PRINT_SELECTORS.captcha_input, timeout_ms=10_000)
            await captcha_input.click()
            await captcha_input.fill("")
            await captcha_input.fill(captcha_text.strip())

            submit_btn = await self._locate_first(PRINT_SELECTORS.submit_button, timeout_ms=10_000)

            # Watch simultaneously for a direct download or popup tab triggered by Submit
            download_task = asyncio.create_task(self._wait_for_download(page, timeout_ms=7_000))
            popup_task = asyncio.create_task(self._wait_for_popup(context, timeout_ms=7_000))

            await submit_btn.click()

            download: Download | None = await download_task
            popup_page = await popup_task

            if download is not None:
                await download.save_as(str(pdf_path))
                if self._is_valid_pdf(pdf_path):
                    return PrintDownloadResult(status="ok", pdf_path=pdf_path)

            if captured_pdf_bytes:
                pdf_path.write_bytes(captured_pdf_bytes[-1])
                if self._is_valid_pdf(pdf_path):
                    return PrintDownloadResult(status="ok", pdf_path=pdf_path)

            # Wait for DOM update if neither immediate download nor popup happened
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            await page.wait_for_timeout(1_000)

            # Check for invalid CAPTCHA before attempting receipt extraction
            notice_text = await self._collect_notice_text(page, PRINT_SELECTORS.error_banner)
            body_text_lower = (await page.inner_text("body")).lower()
            if any(phrase in notice_text.lower() for phrase in INVALID_CAPTCHA_PHRASES) or any(
                phrase in body_text_lower for phrase in INVALID_CAPTCHA_PHRASES
            ):
                await self._dismiss_blocking_dialogs(page)
                new_captcha = await self._capture_captcha_bytes(PRINT_SELECTORS.captcha_image)
                return PrintDownloadResult(
                    status="invalid_captcha",
                    captcha_bytes=new_captcha,
                    message=notice_text or "Invalid CAPTCHA entered.",
                )

            # If a popup receipt window opened, extract PDF from it
            if popup_page is not None:
                await self._save_pdf_from_page(popup_page, pdf_path, captured_pdf_bytes)
                if self._is_valid_pdf(pdf_path):
                    return PrintDownloadResult(status="ok", pdf_path=pdf_path)

            # If the page now shows a "Print" / "Download" button in the result row, click it
            receipt_trigger = await self._try_locate_first(
                PRINT_SELECTORS.receipt_trigger,
                page=page,
                timeout_ms=5_000,
            )
            if receipt_trigger is not None:
                dl_task_2 = asyncio.create_task(self._wait_for_download(page, timeout_ms=8_000))
                pop_task_2 = asyncio.create_task(self._wait_for_popup(context, timeout_ms=8_000))
                await receipt_trigger.click()
                download_2 = await dl_task_2
                popup_2 = await pop_task_2

                if download_2 is not None:
                    await download_2.save_as(str(pdf_path))
                    if self._is_valid_pdf(pdf_path):
                        return PrintDownloadResult(status="ok", pdf_path=pdf_path)

                if captured_pdf_bytes:
                    pdf_path.write_bytes(captured_pdf_bytes[-1])
                    if self._is_valid_pdf(pdf_path):
                        return PrintDownloadResult(status="ok", pdf_path=pdf_path)

                if popup_2 is not None:
                    popup_page = popup_2
                    await self._save_pdf_from_page(popup_2, pdf_path, captured_pdf_bytes)
                    if self._is_valid_pdf(pdf_path):
                        return PrintDownloadResult(status="ok", pdf_path=pdf_path)

            # Check for embedded PDF iframe or rendered HTML receipt directly on current page
            await self._save_pdf_from_page(page, pdf_path, captured_pdf_bytes)
            if self._is_valid_pdf(pdf_path):
                return PrintDownloadResult(status="ok", pdf_path=pdf_path)

            return PrintDownloadResult(
                status="error",
                message=notice_text or f"Could not capture PDF receipt for challan {challan_no}.",
            )
        finally:
            try:
                context.remove_listener("response", _on_response)
            except Exception:  # noqa: BLE001
                pass
            if popup_page is not None and not popup_page.is_closed():
                try:
                    await popup_page.close()
                except Exception:  # noqa: BLE001
                    pass

    async def _wait_for_download(self, page: Page, timeout_ms: int) -> Download | None:
        try:
            return await page.wait_for_event("download", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            return None
        except PlaywrightError:
            return None

    async def _wait_for_popup(self, context: BrowserContext, timeout_ms: int) -> Page | None:
        try:
            return await context.wait_for_event("page", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            return None
        except PlaywrightError:
            return None

    async def _save_pdf_from_page(
        self,
        target_page: Page,
        pdf_path: Path,
        captured_pdf_bytes: list[bytes],
    ) -> None:
        """Attempt direct PDF fetch from iframe/URL, then fallback to Chromium page.pdf()."""
        context = self.context
        assert context is not None

        try:
            await target_page.wait_for_load_state("networkidle", timeout=10_000)
        except PlaywrightTimeoutError:
            pass
        await target_page.wait_for_timeout(600)

        if captured_pdf_bytes:
            pdf_path.write_bytes(captured_pdf_bytes[-1])
            if self._is_valid_pdf(pdf_path):
                return

        # 1. Check if the target page URL itself returns a PDF stream
        if ".pdf" in target_page.url.lower() or "print-challan" in target_page.url.lower():
            try:
                api_resp = await context.request.get(target_page.url)
                ct = (api_resp.headers.get("content-type") or "").lower()
                raw = await api_resp.body()
                if "application/pdf" in ct or raw.startswith(b"%PDF"):
                    pdf_path.write_bytes(raw)
                    if self._is_valid_pdf(pdf_path):
                        return
            except PlaywrightError:
                pass

        # 2. Check embedded <iframe / embed / object> PDF sources
        embed = await self._try_locate_first(PRINT_SELECTORS.pdf_embed, page=target_page, timeout_ms=2_000)
        if embed is not None:
            src = await embed.get_attribute("src") or await embed.get_attribute("data")
            if src:
                full_url = urljoin(target_page.url, src)
                try:
                    api_resp = await context.request.get(full_url)
                    raw = await api_resp.body()
                    if raw.startswith(b"%PDF"):
                        pdf_path.write_bytes(raw)
                        if self._is_valid_pdf(pdf_path):
                            return
                except PlaywrightError:
                    pass

        # 3. Render HTML receipt view via Chromium's native print-to-PDF engine (headless mode)
        if self.headless:
            try:
                await target_page.emulate_media(media="print")
                await target_page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"},
                )
            except PlaywrightError as exc:
                logger.warning("Chromium page.pdf() fallback failed: %s", exc)

    @staticmethod
    def _is_valid_pdf(pdf_path: Path) -> bool:
        """Verify that the saved file exists, is non-empty, and starts with %PDF header."""
        if not pdf_path.exists() or pdf_path.stat().st_size < 256:
            return False
        with pdf_path.open("rb") as fh:
            return fh.read(4) == b"%PDF"


def get_headless_flag() -> bool:
    """Parse HEADLESS_MODE environment variable safely (defaults to True)."""
    return os.getenv("HEADLESS_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}
