"""
Đảm bảo Playwright + Chromium sẵn sàng (Railway/Nixpacks thường chỉ pip install, thiếu browser).
Gọi một lần lúc khởi động bot; tra_diem_client cũng gọi lại nếu cần.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Tuple

_done = False
_last_msg = ""


def _run(cmd: list[str], timeout: int = 600) -> None:
    subprocess.check_call(
        cmd,
        timeout=timeout,
        env=os.environ.copy(),
    )


def _pip_install_playwright() -> None:
    _run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "playwright>=1.40.0"],
        timeout=300,
    )


def _install_chromium() -> None:
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    # Trên Linux container thiếu lib hệ thống; --with-deps cần quyền root (build phase tốt hơn).
    if platform.system() == "Linux" and hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd = [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"]
    _run(cmd, timeout=600)


def _smoke_launch() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        browser.close()


def ensure_playwright_ready(force: bool = False) -> Tuple[bool, str]:
    global _done, _last_msg
    if _done and not force:
        return True, _last_msg

    if os.environ.get("SKIP_PLAYWRIGHT_BOOTSTRAP", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        _done = True
        _last_msg = "skipped (SKIP_PLAYWRIGHT_BOOTSTRAP)"
        return True, _last_msg

    try:
        _smoke_launch()
        _done = True
        _last_msg = f"ok ({sys.executable})"
        return True, _last_msg
    except ImportError:
        try:
            _pip_install_playwright()
            _smoke_launch()
            _done = True
            _last_msg = f"ok after pip install ({sys.executable})"
            return True, _last_msg
        except Exception as e:
            _last_msg = f"pip/import failed: {e}"
            return False, _last_msg
    except Exception as e:
        err = str(e).lower()
        need_browser = any(
            x in err
            for x in (
                "executable doesn't exist",
                "failed to launch",
                "browser",
                "chromium",
                "ENOENT",
            )
        )
        if not need_browser:
            _last_msg = str(e)
            return False, _last_msg
        try:
            _install_chromium()
            _smoke_launch()
            _done = True
            _last_msg = f"ok after chromium install ({sys.executable})"
            return True, _last_msg
        except Exception as e2:
            _last_msg = f"chromium install/launch failed: {e2}"
            return False, _last_msg
