import os
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
Browser = playwright_api.Browser
Playwright = playwright_api.Playwright
sync_playwright = playwright_api.sync_playwright


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as instance:
        yield instance


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright):
    executable = os.getenv("PLAYWRIGHT_CHROME_PATH")
    launch_args = {"headless": True}
    if executable:
        if not Path(executable).is_file():
            raise RuntimeError(f"PLAYWRIGHT_CHROME_PATH does not exist: {executable}")
        launch_args["executable_path"] = executable
    browser = playwright_instance.chromium.launch(**launch_args)
    yield browser
    browser.close()


@pytest.fixture()
def page(browser: Browser):
    base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5173")
    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    yield page
    context.close()
