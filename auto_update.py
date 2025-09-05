"""Simple auto-update helper for Windows builds.

This module checks the latest release on GitHub and, when a newer version is
available, offers to download and run the installer. The repository is fixed
in GITHUB_REPO but can be overridden by the environment variable GITHUB_REPO.
The currently installed version is obtained primarily from a fixed registry
key we write during install, and secondarily by scanning Inno Setup uninstall
keys across HKCU/HKLM and 32/64-bit views.

Pure-stdlib only to work inside PyInstaller executables.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
import urllib.request
from tkinter import messagebox

from i18n import tr


# Default repository; can be overridden by env var at runtime
GITHUB_REPO = os.environ.get("GITHUB_REPO", "cheesedongjin/Branching-Novel-Tools")

if platform.system() == "Windows":
    import winreg  # type: ignore[import-not-found]
else:  # pragma: no cover - non-Windows
    winreg = None  # type: ignore[misc]


def _normalize_app_id(app_id: str | None) -> str | None:
    """Return AppId without braces (e.g., {GUID} -> GUID)."""
    if not app_id:
        return None
    s = app_id.strip()
    # strip one pair of leading/trailing braces if present
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    # 방어적으로 여분의 '}' 같은 오타도 정리
    s = s.strip("{} \t")
    return s or None


def _ver_tuple(ver: str) -> tuple[int, ...]:
    parts = []
    for p in ver.strip().split("."):
        # keep only leading integer portion of each segment
        num = ""
        for ch in p:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            parts.append(int(num))
        else:
            # if a segment has no leading digits, treat as 0
            parts.append(0)
    # remove trailing zeros to normalize
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts) if parts else (0,)


def _open_key(root, path: str, access: int) -> object | None:
    try:
        return winreg.OpenKey(root, path, 0, access)
    except OSError:
        return None


def _get_val(key, name: str, default=None):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def _scan_inno_uninstall_for_version(app_name: str, app_id: str | None) -> str:
    """Scan Inno Setup uninstall locations for DisplayVersion.

    탐색 우선순위
      1) {AppId}_is1 (정확히 일치)
      2) <AppName> (DisplayName 정확히 일치)
      3) (마지막 안전장치) 키 이름이 <AppName>_is1 인 경우
    """
    if winreg is None:
        return "0"

    UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    hives = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]

    WOW64_32 = getattr(winreg, "KEY_WOW64_32KEY", 0)
    WOW64_64 = getattr(winreg, "KEY_WOW64_64KEY", 0)
    views = [winreg.KEY_READ, winreg.KEY_READ | WOW64_32, winreg.KEY_READ | WOW64_64]

    norm_app_id = _normalize_app_id(app_id)
    # Inno는 일반적으로 {GUID}_is1 형태를 사용
    candidates_by_id = []
    if norm_app_id:
        candidates_by_id.append("{" + norm_app_id + "}_is1")
        # 혹시 모를 변종/오타 대응: GUID_is1 도 한 번 시도
        candidates_by_id.append(norm_app_id + "_is1")

    # 1) AppId 기반 정확 키 조회
    for hive in hives:
        for access in views:
            for target in candidates_by_id:
                k = _open_key(hive, UNINSTALL + "\\" + target, access)
                if not k:
                    continue
                try:
                    v = _get_val(k, "DisplayVersion")
                    if v:
                        return str(v)
                finally:
                    winreg.CloseKey(k)

    # 2) DisplayName == app_name (정확 일치) 로 열거 조회
    for hive in hives:
        for access in views:
            base = _open_key(hive, UNINSTALL, access)
            if not base:
                continue
            try:
                i = 0
                while True:
                    try:
                        subname = winreg.EnumKey(base, i)
                        i += 1
                    except OSError:
                        break
                    sub = _open_key(hive, UNINSTALL + "\\" + subname, access)
                    if not sub:
                        continue
                    try:
                        disp = _get_val(sub, "DisplayName", "")
                        if isinstance(disp, str) and disp.strip() == app_name.strip():
                            v = _get_val(sub, "DisplayVersion")
                            if v:
                                return str(v)
                    finally:
                        winreg.CloseKey(sub)
            finally:
                winreg.CloseKey(base)

    # 3) (예외적) 키 이름이 <AppName>_is1 인 경우 직접 조회
    target_by_name = f"{app_name}_is1"
    for hive in hives:
        for access in views:
            k = _open_key(hive, UNINSTALL + "\\" + target_by_name, access)
            if k:
                try:
                    v = _get_val(k, "DisplayVersion")
                    if v:
                        return str(v)
                finally:
                    winreg.CloseKey(k)

    return "0"


def _get_installed_version(app_name: str, app_id: str | None = None) -> str:
    """Return installed version.

    Priority:
      1) HKCU\Software\BranchingNovelTools\<AppName>\Version (고정 키)
      2) Inno Setup uninstall (AppId 엄격 + DisplayName 정확 일치)
      3) "0"
    """
    if winreg is None:
        return "0"

    # 1) 우리가 [Registry]로 쓰는 고정 키가 최우선
    custom_key = rf"Software\BranchingNovelTools\{app_name}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, custom_key) as k:
            v = winreg.QueryValueEx(k, "Version")[0]
            if v:
                return str(v)
    except OSError:
        pass

    # 2) Inno Uninstall 쪽 스캔
    return _scan_inno_uninstall_for_version(app_name, app_id)


def _github_api_json(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url)
    # Add a UA to reduce likelihood of 403/blocked
    req.add_header("User-Agent", "BranchingNovelTools-Updater/1.0 (+Windows)")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # GitHub returns UTF-8 JSON
        data = resp.read()
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {}


def _pick_asset_download_url(release: dict, installer_name: str) -> str | None:
    assets = release.get("assets") or []
    # 1) Exact match
    for a in assets:
        if a.get("name") == installer_name:
            return a.get("browser_download_url")
    # 2) Fallback: first .exe
    for a in assets:
        name = a.get("name") or ""
        if name.lower().endswith(".exe"):
            return a.get("browser_download_url")
    return None


def check_for_update(
    app_name: str,
    installer_name: str,
    *,
    parent=None,
    app_id: str | None = None,
) -> None:
    """Check GitHub for a newer release and optionally run the installer.

    Parameters
    ----------
    app_name: str
        Display name of the application (used for registry lookup and UI).
    installer_name: str
        Expected asset name of the installer in the GitHub release.
    parent: tkinter widget, optional
        Parent widget for message boxes.
    app_id: str | None
        Inno Setup AppId (without curly braces). If provided, improves accuracy
        when scanning uninstall keys.
    """
    if platform.system() != "Windows":
        return

    current_version = _get_installed_version(app_name, app_id=app_id)

    try:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        data = _github_api_json(api_url, timeout=8.0)
        tag = str(data.get("tag_name") or "")
        latest = tag[1:] if tag.startswith("v") else tag
        if not latest:
            return

        if _ver_tuple(latest) <= _ver_tuple(current_version):
            return

        msg = tr("update_available", app=app_name, ver=latest)
        if not messagebox.askyesno(tr("update_title"), msg, parent=parent):
            return

        asset_url = _pick_asset_download_url(data, installer_name)
        if not asset_url:
            return

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".exe")
        tmp.close()
        urllib.request.urlretrieve(asset_url, tmp.name)
        subprocess.Popen([tmp.name, "/VERYSILENT", "/NORESTART"])
        messagebox.showinfo(tr("update_title"), tr("update_started"), parent=parent)
    except Exception:
        # Fail silently by design
        pass


__all__ = ["check_for_update"]
