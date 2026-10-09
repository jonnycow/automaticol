import asyncio

from playwright.async_api import async_playwright

from app.config import settings
from app.facebook.browser import create_browser_context
from app.facebook.marketplace import open_marketplace


async def main() -> None:
    async with async_playwright() as playwright:
        context = await create_browser_context(
            playwright=playwright,
            profile_path=settings.facebook_profile_path,
            headless=settings.facebook_headless,
        )

        page = (
            context.pages[0]
            if context.pages
            else await context.new_page()
        )

        await page.goto(
            settings.facebook_base_url,
            wait_until="domcontentloaded",
        )

        print()
        print("===================================")
        print(" Facebook abierto")
        print("===================================")
        print()
        print("Inicia sesión manualmente si es necesario.")
        print("No cierres la ventana del navegador.")
        print()

        await page.wait_for_timeout(15000)

        await open_marketplace(
            page=page,
            base_url=settings.facebook_base_url,
        )

        print("Marketplace abierto.")
        print("La sesión quedará guardada en:")
        print(settings.facebook_profile_path)
        print()
        print("Presiona Ctrl+C para terminar.")

        try:
            while True:
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\nCerrando...")


if __name__ == "__main__":
    asyncio.run(main())