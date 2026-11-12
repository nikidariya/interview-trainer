"""Run manually: python tests/browser_guest_smoke.py http://localhost:8502

Requires Playwright and its Chromium browser. Does not call the LLM or create users.
"""
import sys
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=os.getenv("PLAYWRIGHT_CHANNEL") or None)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501")
        vacancy = page.get_by_role("textbox", name="Текст вакансии")
        expect(vacancy).to_be_visible()
        vacancy.fill("Черновик вакансии для проверки")
        page.get_by_role("button", name="Войти", exact=True).click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role("tab", name="Регистрация", exact=True)).to_be_visible()
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(vacancy).to_have_value("Черновик вакансии для проверки")
        page.get_by_role("button", name="Войти", exact=True).click()
        expect(dialog).to_be_visible()
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(vacancy).to_have_value("Черновик вакансии для проверки")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_role("button", name="Войти", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow"
        page.get_by_role("button", name="Войти", exact=True).click()
        expect(dialog).to_be_visible()
        google = dialog.get_by_role("button", name="Войти через Google")
        if google.count():
            icon = google.locator("p").evaluate("el => getComputedStyle(el, '::before').backgroundImage")
            assert "data:image/svg+xml" in icon
        screenshot = Path(".pytest_cache/guest-mobile.png")
        screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(vacancy).to_have_value("Черновик вакансии для проверки")
        browser.close()
        print("Guest page, modal dismissal, draft preservation and mobile layout: OK")


if __name__ == "__main__":
    main()
