from playwright.async_api import BrowserContext, Playwright


async def create_browser_context(
    playwright: Playwright,
    profile_path: str,
    headless: bool = False,
) -> BrowserContext:
    return await playwright.chromium.launch_persistent_context(
        user_data_dir=profile_path,
        headless=headless,
        viewport={
            "width": 1404,
            "height": 720,
        },
    )