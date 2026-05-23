"""
Tra cứu điểm ĐGNL qua thinangluc.vnuhcm.edu.vn (trang « Tra kết quả thi »).

Luồng: GET danh sách đợt thi (JSON), rồi Playwright mở trang thật, gửi form (reCAPTCHA v3).
Có thể ghi đè: đặt file test.py ở gốc project với hàm tra_diem_sync (legacy).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

_ROOT = Path(__file__).resolve().parent
API_BASE = "https://thinangluc.vnuhcm.edu.vn/dgnl/api/"
SEARCH_PAGE = "https://thinangluc.vnuhcm.edu.vn/dgnl/search-result-exam"

# Playwright: không tải ảnh/CSS/font/media — chỉ cần DOM + JS cho form/reCAPTCHA.
_PLAYWRIGHT_SKIP_RESOURCE_TYPES = frozenset(
    ("image", "stylesheet", "font", "media", "manifest")
)


def _playwright_abort_heavy_resources(route) -> None:
    if route.request.resource_type in _PLAYWRIGHT_SKIP_RESOURCE_TYPES:
        route.abort()
    else:
        route.continue_()


_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "Accept": "application/json",
        "Accept-Language": "vi",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }
)

_impl: Optional[Callable[..., Dict[str, Any]]] = None


def _get_legacy_impl() -> Optional[Callable[..., Dict[str, Any]]]:
    legacy = _ROOT / "test.py"
    if not legacy.is_file():
        return None
    spec = importlib.util.spec_from_file_location("user_tra_diem_plugin", legacy)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "tra_diem_sync", None)
    return fn if callable(fn) else None


def _normalize_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(raw)
    c = out.get("code")
    if c in (0, "0", "200", 200):
        out["code"] = 0
    elif isinstance(c, str) and c.isdigit():
        out["code"] = int(c)
    if "msg" not in out and "message" in out:
        out["msg"] = out.get("message", "")
    if out.get("data") is None:
        out["data"] = {}
    return out


def _validate_inputs(so_bao_danh: str, email: str) -> Optional[Dict[str, Any]]:
    cccd = so_bao_danh.strip()
    em = email.strip().lower()
    if not cccd:
        return {"code": 400, "msg": "Chưa nhập Số Thẻ căn cước/CCCD", "data": {}}
    if not re.match(r"^\d{9}$|^\d{12}$", cccd):
        return {"code": 400, "msg": "Số Thẻ căn cước/CCCD không hợp lệ (9 hoặc 12 chữ số)", "data": {}}
    if not em:
        return {"code": 400, "msg": "Chưa nhập địa chỉ email", "data": {}}
    if not re.match(r"^[\w\-.]+@([\w\-]+\.)+[\w\-]{2,4}$", em):
        return {"code": 400, "msg": "Địa chỉ email không hợp lệ", "data": {}}
    return None


def _list_registrations() -> List[Dict[str, Any]]:
    r = _SESSION.get(f"{API_BASE}public/v1/list-registrations", timeout=25)
    r.raise_for_status()
    body = r.json()
    if body.get("code") not in (0, "0"):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []


def _pick_dot_id(regs: List[Dict[str, Any]]) -> Optional[int]:
    if not regs:
        return None
    return max(int(x["id"]) for x in regs if x.get("id") is not None)


def _tra_diem_impl(so_bao_danh: str, email: str) -> Dict[str, Any]:
    err = _validate_inputs(so_bao_danh, email)
    if err:
        return err

    cccd = so_bao_danh.strip()
    em = email.strip().lower()

    try:
        regs = _list_registrations()
    except requests.RequestException as e:
        return {"code": 503, "msg": f"Không kết nối được máy chủ tra cứu: {e}", "data": {}}

    dot_id = _pick_dot_id(regs)
    if dot_id is None:
        return {"code": 404, "msg": "Không tìm thấy đợt thi", "data": {}}

    from utils.playwright_bootstrap import ensure_playwright_ready

    ok, boot_msg = ensure_playwright_ready()
    if not ok:
        return {
            "code": 503,
            "msg": (
                f"Playwright/Chromium chưa sẵn sàng trên máy chủ: {boot_msg}. "
                "Railway: bật Builder = Dockerfile hoặc Start Command = bash scripts/railway_start.sh"
            ),
            "data": {},
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "code": 503,
            "msg": (
                "Không import được playwright sau khi cài. "
                f"Chi tiết: {boot_msg}. Thử redeploy với Dockerfile."
            ),
            "data": {},
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--blink-settings=imagesEnabled=false",
                ],
            )
            try:
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                    locale="vi-VN",
                    timezone_id="Asia/Ho_Chi_Minh",
                    # Viewport nhỏ: ít compositing/paint; headless vẫn chạy JS/form bình thường.
                    viewport={"width": 640, "height": 480},
                )

                ctx.route("**/*", _playwright_abort_heavy_resources)
                page = ctx.new_page()
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                with page.expect_response(
                    lambda r: "list-registrations" in r.url and r.ok,
                    timeout=90000,
                ):
                    page.goto(SEARCH_PAGE, wait_until="domcontentloaded", timeout=90000)

                page.wait_for_timeout(800)
                page.wait_for_selector("#cboDotDuThi option", state="attached", timeout=30000)
                page.evaluate(
                    """(id) => {
                        const el = document.querySelector('#cboDotDuThi');
                        if (!el) return;
                        el.value = String(id);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    dot_id,
                )
                page.fill("#txtSoBaoDanh", cccd)
                page.fill("#txtEmail", em)

                with page.expect_response(
                    lambda r: r.request.method == "POST"
                    and "/public/v1/search-result-exam/" in r.url,
                    timeout=45000,
                ) as resp_info:
                    page.click("#bntSearch")
                body = resp_info.value.json()
            finally:
                browser.close()
    except Exception as e:
        err_name = type(e).__name__
        if "Timeout" in err_name:
            return {
                "code": 504,
                "msg": "Hết thời gian chờ trang tra cứu. Thử lại sau hoặc kiểm tra mạng.",
                "data": {},
            }
        return {
            "code": 503,
            "msg": f"Lỗi khi mở trình duyệt tra cứu: {e}",
            "data": {},
        }

    return _normalize_payload(body)


def _get_impl() -> Callable[..., Dict[str, Any]]:
    global _impl
    if _impl is not None:
        return _impl
    legacy = _get_legacy_impl()
    if legacy is not None:
        _impl = legacy
        return _impl
    _impl = _tra_diem_impl
    return _impl


def tra_diem_sync(so_bao_danh: str, email: str) -> Dict[str, Any]:
    return _get_impl()(so_bao_danh, email)
