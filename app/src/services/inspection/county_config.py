"""County adapter configuration for the inspection scraper.

Each county health department portal has its own quirks — URL structure,
form fields, date formats, CSS selectors, etc. This config captures those
differences so the scraper engine can operate on any county.

The Site Discovery Agent (planned) will auto-generate these configs by
analyzing county portal pages with Playwright + Claude Vision.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CountyConfig:
    """Configuration for a specific county's inspection portal."""

    # Identity
    county_name: str
    state: str = "CA"

    # Portal URL
    portal_url: str = ""

    # CSS Selectors — these target the myhealthdepartment.com platform
    # which is used by Sacramento, Placer, and many other CA counties.
    # Override for counties using different portal software.
    date_picker_selector: str = ".alt-datePicker"
    results_row_selector: str = ".flex-row"
    load_more_selector: str = ".load-more-results-button"
    facility_name_selector: str = "h4.establishment-list-name a"
    address_selector: str = ".establishment-list-address"
    inspection_button_selector: str = ".view-inspections-button"
    date_display_selector: str = ".text-right"
    facility_detail_item_selector: str = ".establishment-info-item"
    info_label_selector: str = ".info-label"
    info_value_selector: str = ".info-value"
    pdf_link_selector: str = 'a:has-text("View Original Inspection PDF")'
    pdf_link_fallback_selector: str = 'a:has-text("PDF")'

    # Date handling
    date_input_format: str = "%m/%d/%Y"  # What the portal expects
    date_range_separator: str = " to "   # How date ranges are formatted
    # If True, use keyboard input with retry (robust but slow).
    # If False, use JavaScript injection (faster but can break on some sites).
    use_keyboard_date_input: bool = True

    # Base URL for constructing absolute URLs from relative paths
    base_url: str = "https://inspections.myhealthdepartment.com"

    # Browser config
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0"
    use_firefox: bool = True  # EMD blocks headless Chrome

    # Rate limiting
    default_rate_limit_seconds: int = 5
    page_load_timeout_ms: int = 60000
    selector_timeout_ms: int = 15000

    # Scraping behavior
    max_load_more_clicks: int = 10
    extract_before_load_more: bool = True  # Safety net for flaky Load More
    parse_date_from_results: bool = True   # Extract date from HTML vs use search date

    # Upload directory suffix (relative to uploads/inspection/)
    upload_subdir: str = ""

    # Program identifier default
    default_program: str = "POOL"


# ── Pre-built configs ────────────────────────────────────────────────

SACRAMENTO = CountyConfig(
    county_name="Sacramento",
    portal_url="https://inspections.myhealthdepartment.com/sacramento/program-rec-health",
    use_keyboard_date_input=True,
    extract_before_load_more=True,
    parse_date_from_results=True,
    upload_subdir="sacramento",
)

# NOTE (2026-04-11): Placer County does NOT publish pool inspection reports
# online. As of this date, Sacramento County is the ONLY California county
# that exposes a public inspection portal we can scrape. This config exists
# as an aspirational placeholder in case Placer ever launches a portal — the
# URL below is a guess and has never been verified to return real data.
# DO NOT add this to COUNTY_CONFIGS or run the daily scraper against it
# until you've confirmed the portal exists and the selectors still match.
PLACER_PLACEHOLDER = CountyConfig(
    county_name="Placer",
    portal_url="https://inspections.myhealthdepartment.com/placer/program-rec-health",
    use_keyboard_date_input=True,
    extract_before_load_more=True,
    parse_date_from_results=True,
    upload_subdir="placer",
)

# Registry of ACTIVE county scrapers. Sacramento is the only county whose
# health department publishes inspection reports online. Other counties we
# serve (Placer, El Dorado, etc.) require manual lookup or in-person requests.
COUNTY_CONFIGS: dict[str, CountyConfig] = {
    "sacramento": SACRAMENTO,
}


def get_county_config(county_slug: str) -> CountyConfig:
    """Get config for a county by slug. Raises KeyError if not found."""
    config = COUNTY_CONFIGS.get(county_slug.lower())
    if not config:
        available = ", ".join(COUNTY_CONFIGS.keys())
        raise KeyError(f"Unknown county '{county_slug}'. Available: {available}")
    return config
