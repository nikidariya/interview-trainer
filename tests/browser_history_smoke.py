"""Standalone browser check with in-memory interviews; no accounts, database or LLM.

Run: python tests/browser_history_smoke.py
Requires Playwright Chromium (or PLAYWRIGHT_CHANNEL).
"""
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def serve():
    from copy import deepcopy
    from datetime import datetime, timezone
    import streamlit as st
    from app import auth, interviews
    from app.orchestrator import InterviewSession
    from app.schemas import InterviewPlan

    st.session_state._auth_account = {"id": "preview-owner", "name": "Preview"}
    auth.current_account = lambda: st.session_state._auth_account
    session = InterviewSession()
    session.plan = InterviewPlan("Python", "Junior", ["Python"])
    session._current_question = "Расскажите о вашем проекте?"
    snapshot = dict(schema_version=1, session=session.to_dict(),
                    messages=[("assistant", session._current_question)], report=None,
                    pending=None, error=None, vacancy_error=None)
    if "_auth_preview_records" not in st.session_state:
        st.session_state._auth_preview_records = {
            str(i): dict(id=str(i), user_id="preview-owner", title=f"Подготовка к интервью {i}",
                         status="in_progress", updated_at=datetime.now(timezone.utc), version=1,
                         vacancy="Python", snapshot=deepcopy(snapshot)) for i in range(1, 4)}
    records = st.session_state._auth_preview_records
    interviews.list_interviews = lambda _: [deepcopy(r) for r in records.values()]
    interviews.load_interview = lambda _, key: deepcopy(records[key])

    def rename(_, key, title, version):
        if not title.strip():
            raise ValueError("Введите название.")
        records[key].update(title=title.strip(), version=version + 1)
        return deepcopy(records[key])

    interviews.rename_interview = rename
    interviews.delete_interview = lambda _, key, version: records.pop(key, None)
    runpy.run_path(str(ROOT / "app/ui.py"), run_name="__main__")


def main():
    from playwright.sync_api import expect, sync_playwright

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve()),
         "--server.headless=true", "--server.address=127.0.0.1", f"--server.port={port}",
         "--browser.gatherUsageStats=false", "--", "--serve"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                with urlopen(url + "/_stcore/health", timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel=os.getenv("PLAYWRIGHT_CHANNEL") or None)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url)
            menu = page.locator(".st-key-history_menu_1")
            dots = page.locator(".st-key-history_more_1 button:visible")
            expect(dots).to_be_visible(timeout=20000)
            expect(menu).to_be_hidden()
            dots.hover()
            expect(menu).to_be_visible()
            expect(menu.get_by_role("button")).to_have_count(2)
            page.screenshot(path=str(ROOT / ".pytest_cache/history-menu.png"))
            menu.get_by_role("button", name="Переименовать").click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            page.screenshot(path=str(ROOT / ".pytest_cache/history-rename.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(ROOT / ".pytest_cache/history-rename-mobile.png"))
            page.set_viewport_size({"width": 1280, "height": 900})
            dialog.get_by_role("textbox", name="Название").fill("Моя подготовка")
            expect(dialog.get_by_text("Press Enter to submit form", exact=True)).to_be_hidden()
            page.screenshot(path=str(ROOT / ".pytest_cache/history-rename-editing.png"))
            dialog.get_by_role("button", name="Сохранить название").click()
            expect(dialog).not_to_be_visible()
            expect(page.get_by_role("button", name="Моя подготовка", exact=True)).to_be_visible()
            dots.focus()
            expect(menu).to_be_visible()
            menu.get_by_role("button", name="Удалить", exact=True).click()
            expect(dialog).to_be_visible()
            for width in (1280, 390):
                page.set_viewport_size({"width": width, "height": 900})
                cancel_bounds = dialog.get_by_role("button", name="Отмена", exact=True).bounding_box()
                delete_bounds = dialog.get_by_role("button", name="Удалить интервью", exact=True).bounding_box()
                assert cancel_bounds and delete_bounds
                assert abs(cancel_bounds["width"] - delete_bounds["width"]) < 1
                assert cancel_bounds["height"] == delete_bounds["height"] == 64
                page.screenshot(path=str(ROOT / f".pytest_cache/history-delete-{width}.png"))
            page.set_viewport_size({"width": 1280, "height": 900})
            dialog.get_by_role("button", name="Отмена").click()
            expect(page.get_by_role("button", name="Моя подготовка", exact=True)).to_be_visible()
            page.get_by_role("button", name="Моя подготовка", exact=True).click()
            page.set_viewport_size({"width": 390, "height": 844})
            expand = page.get_by_test_id("stExpandSidebarButton")
            if expand.is_visible():
                expand.click()
            dots.click()
            expect(menu).to_be_visible()
            bounds = menu.bounding_box()
            assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
            page.screenshot(path=str(ROOT / ".pytest_cache/history-menu-mobile.png"))
            menu.get_by_role("button", name="Удалить", exact=True).click()
            dialog.get_by_role("button", name="Удалить интервью", exact=True).click()
            expect(page.get_by_role("button", name="Моя подготовка", exact=True)).to_have_count(0)
            expect(page.get_by_role("textbox", name="Текст вакансии")).to_be_visible()
            browser.close()
        print("History hover, keyboard, rename, cancel, mobile menu and active deletion: OK")
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        main()
