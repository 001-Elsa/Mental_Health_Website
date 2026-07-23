import os
import time

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
Page = playwright_api.Page
expect = playwright_api.expect


pytestmark = pytest.mark.e2e


def create_user(page: Page) -> tuple[str, str]:
    suffix = str(int(time.time() * 1000))[-8:]
    phone = f"139{suffix}"
    nickname = f"端到端用户{suffix[-5:]}"
    password = "E2e-secure-123"
    code_response = page.request.post("/api/auth/send-code", data={"phone": phone})
    assert code_response.ok
    code = code_response.json()["dev_code"]
    register = page.request.post(
        "/api/auth/register",
        data={"nickname": nickname, "phone": phone, "code": code, "password": password},
    )
    assert register.ok
    return nickname, password


def test_login_cookie_restore_route_boundary_and_logout(page: Page):
    page.goto("/")
    nickname, password = create_user(page)

    page.get_by_role("button", name="登录").first.click()
    page.get_by_placeholder("昵称").fill(nickname)
    page.get_by_placeholder("密码").fill(password)
    page.locator("form").get_by_role("button", name="登录").click()
    expect(page.locator(".user-name")).to_contain_text(nickname)

    # Access tokens are memory-only. A reload must restore the session through
    # the HttpOnly refresh cookie without exposing the refresh token to JS.
    page.reload()
    expect(page.locator(".user-name")).to_contain_text(nickname)
    storage = page.evaluate("Object.keys(localStorage)")
    assert "mh-auth" not in storage

    page.goto("/admin")
    expect(page).to_have_url(os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5173") + "/dashboard")

    page.goto("/profile")
    page.get_by_role("button", name="退出登录").click()
    expect(page.get_by_role("button", name="登录").first).to_be_visible()


def test_public_pages_render_without_authentication(page: Page):
    page.goto("/articles")
    expect(page.locator("main")).to_be_visible()
    page.goto("/community")
    expect(page.locator("main")).to_be_visible()
