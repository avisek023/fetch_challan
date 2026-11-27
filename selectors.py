"""Centralized CSS/XPath selectors for Parivahan eChallan portals.

Provides ordered primary and fallback selector chains for both:
1. https://echallan.parivahan.gov.in/index/accused-challan
2. https://echallan.parivahan.gov.in/index/challan-print

Parivahan occasionally updates element IDs or wrapper classes across state
deployments; keeping selectors centralized with ordered fallbacks allows
quick maintenance without touching browser automation logic.
"""

from __future__ import annotations

from dataclasses import dataclass

ACCUSED_CHALLAN_URL = "https://echallan.parivahan.gov.in/index/accused-challan"
CHALLAN_PRINT_URL = "https://echallan.parivahan.gov.in/index/challan-print"


@dataclass(frozen=True)
class AccusedChallanSelectors:
    """Selectors for /index/accused-challan (Stage 1 & Stage 2)."""

    # Radio / tab selector to switch lookup mode to Vehicle Number
    vehicle_tab: tuple[str, ...] = (
        "#vehicle_no",
        "input[type='radio'][value='vehicle_no']",
        "input[type='radio'][value='vehicle']",
        "input[id*='vehicle' i][type='radio']",
        "label:has-text('Vehicle Number')",
        "a:has-text('Vehicle Number')",
        "li:has-text('Vehicle Number')",
        "button:has-text('Vehicle Number')",
    )

    # Vehicle registration number input box
    vehicle_input: tuple[str, ...] = (
        "#vehicle_number",
        "#vehicleNo",
        "input[name='vehicle_number']",
        "input[name='vehicle_no']",
        "input[id*='vehicle' i][type='text']",
        "input[placeholder*='Vehicle' i]",
    )

    # CAPTCHA image element
    captcha_image: tuple[str, ...] = (
        "#captcha_img",
        "#captchaImage",
        "img#captcha",
        "img[id*='captcha' i]",
        "img[src*='captcha' i]",
        "img[alt*='captcha' i]",
        ".captcha-image img",
        ".captcha img",
    )

    # CAPTCHA refresh button/link
    captcha_refresh: tuple[str, ...] = (
        "#refresh_captcha",
        "#refreshCaptcha",
        "a[id*='refresh' i]",
        "button[id*='refresh' i]",
        "a[onclick*='captcha' i]",
        "button[onclick*='captcha' i]",
        "a[title*='Refresh' i]",
        "button[title*='Refresh' i]",
        ".refresh-captcha",
        "i.fa-refresh",
        "i.fa-sync",
    )

    # CAPTCHA text input
    captcha_input: tuple[str, ...] = (
        "#captcha",
        "#captcha_code",
        "#txt_captcha",
        "input[name='captcha']",
        "input[name*='captcha' i]",
        "input[id*='captcha' i][type='text']",
        "input[placeholder*='Captcha' i]",
        "input[placeholder*='Security' i]",
    )

    # Submit / Get Detail button
    submit_button: tuple[str, ...] = (
        "#get_detail",
        "#getDetail",
        "#btn_get_detail",
        "button:has-text('Get Detail')",
        "input[type='submit'][value*='Get Detail' i]",
        "input[type='button'][value*='Get Detail' i]",
        "button:has-text('Submit')",
        "button[type='submit']",
    )

    # Pending challans table and wrapper
    challan_table: tuple[str, ...] = (
        "#challan_list_table",
        "#accused_challan_table",
        "table.dataTable",
        "table:has(th:has-text('Challan'))",
        "table.table",
        ".table-responsive table",
    )

    # Error / alert containers
    error_banner: tuple[str, ...] = (
        ".alert-danger",
        ".alert-warning",
        "#error_msg",
        "#err_msg",
        ".error-message",
        ".toast-error",
        ".toast-message",
        ".swal2-html-container",
        ".swal2-title",
        ".bootbox-body",
        ".modal-body",
    )


@dataclass(frozen=True)
class ChallanPrintSelectors:
    """Selectors for /index/challan-print (Stage 3)."""

    # Challan number radio/tab (if print page offers tabs)
    challan_tab: tuple[str, ...] = (
        "#challan_no_radio",
        "input[type='radio'][value='challan_no']",
        "label:has-text('Challan Number')",
    )

    # Challan number text input
    challan_input: tuple[str, ...] = (
        "#challan_no",
        "#challanNo",
        "#challan_number",
        "input[name='challan_no']",
        "input[name='challan_number']",
        "input[id*='challan' i][type='text']",
        "input[placeholder*='Challan' i]",
    )

    # CAPTCHA image element
    captcha_image: tuple[str, ...] = (
        "#captcha_img",
        "#captchaImage",
        "img#captcha",
        "img[id*='captcha' i]",
        "img[src*='captcha' i]",
        "img[alt*='captcha' i]",
        ".captcha img",
    )

    # CAPTCHA refresh button/link
    captcha_refresh: tuple[str, ...] = (
        "#refresh_captcha",
        "#refreshCaptcha",
        "a[id*='refresh' i]",
        "button[id*='refresh' i]",
        "a[onclick*='captcha' i]",
        "button[onclick*='captcha' i]",
        "a[title*='Refresh' i]",
        "button[title*='Refresh' i]",
        ".refresh-captcha",
        "i.fa-refresh",
        "i.fa-sync",
    )

    # CAPTCHA input box
    captcha_input: tuple[str, ...] = (
        "#captcha",
        "#captcha_code",
        "#txt_captcha",
        "input[name='captcha']",
        "input[name*='captcha' i]",
        "input[id*='captcha' i][type='text']",
        "input[placeholder*='Captcha' i]",
    )

    # Submit / Get Detail / Print button
    submit_button: tuple[str, ...] = (
        "#get_detail",
        "#getDetail",
        "#print_challan",
        "button:has-text('Get Detail')",
        "button:has-text('Print')",
        "input[type='submit'][value*='Get Detail' i]",
        "input[type='submit'][value*='Print' i]",
        "button:has-text('Submit')",
        "button[type='submit']",
    )

    # Secondary receipt download/print triggers shown after table loads
    receipt_trigger: tuple[str, ...] = (
        "a[href*='print-challan']",
        "a[href*='challan-print']",
        "a[href*='receipt' i]",
        "a[href*='.pdf' i]",
        "a:has-text('Challan Print')",
        "a:has-text('Print')",
        "button:has-text('Print')",
        "a:has-text('Download')",
        "button:has-text('Download')",
        ".btn-print",
        "a:has(i.fa-print)",
        "button:has(i.fa-print)",
        "a:has(i.fa-file-pdf-o)",
        "a:has(i.fa-file-pdf)",
    )

    # Embedded PDF viewer or printable receipt container
    pdf_embed: tuple[str, ...] = (
        "iframe[src*='.pdf' i]",
        "iframe[src*='print' i]",
        "iframe[src*='receipt' i]",
        "embed[type='application/pdf']",
        "object[type='application/pdf']",
    )

    receipt_container: tuple[str, ...] = (
        "#challan_receipt",
        "#print_area",
        "#printableArea",
        ".challan-receipt",
        ".print-container",
    )

    # Error / alert containers
    error_banner: tuple[str, ...] = (
        ".alert-danger",
        ".alert-warning",
        "#error_msg",
        "#err_msg",
        ".error-message",
        ".toast-error",
        ".toast-message",
        ".swal2-html-container",
        ".swal2-title",
        ".bootbox-body",
        ".modal-body",
    )


# Text matchers used to interpret Parivahan portal messages cleanly
INVALID_CAPTCHA_PHRASES: tuple[str, ...] = (
    "invalid captcha",
    "incorrect captcha",
    "wrong captcha",
    "captcha does not match",
    "captcha mismatch",
    "please enter valid captcha",
    "enter valid captcha",
    "invalid security code",
)

NO_CHALLAN_PHRASES: tuple[str, ...] = (
    "no challan found",
    "no record found",
    "no records found",
    "challan details not found",
    "challan not found",
    "no pending challan",
    "0 challan",
)

DISPOSED_STATUS_PHRASES: tuple[str, ...] = (
    "disposed",
    "paid",
    "settled",
    "cancelled",
    "canceled",
    "closed",
)

ACCUSED_SELECTORS = AccusedChallanSelectors()
PRINT_SELECTORS = ChallanPrintSelectors()
