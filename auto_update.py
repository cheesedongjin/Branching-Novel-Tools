"""Simple auto-update helper for Windows builds."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
import urllib.request
from tkinter import messagebox

from i18n import tr

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
    # defensive cleanup for stray braces like '}}' from typos
    s = s.strip("{} \t")
    return s or None


def _norm_name(s: str | None) -> str:
    """Casefold + collapse whitespaces for tolerant comparisons."""
    if not isinstance(s, str):
        return ""
    # remove all spaces and casefold
    return "".join(s.split()).casefold()


def _ver_tuple(ver: str) -> tuple[int, ...]:
    """
    Parse version like '1.2.3', '1.2.3-rc1', '1.2.3+meta' to a tuple of ints.
    Non-digit suffixes per segment are ignored. Trailing zeros removed.
    """
    # Cut off build metadata or pre-release labels at first non [0-9.].
    cleaned = []
    seg = ""
    for ch in ver.strip():
        if ch.isdigit() or ch == ".":
            seg += ch
        else:
            break
    if not seg:
        seg = "0"

    parts = []
    for p in seg.split("."):
        num = ""
        for ch in p:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)

    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts) if parts else (0,)


def _open_key(root, path: str, access: int):
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
    """
    Scan Inno Setup uninstall locations for DisplayVersion.

    Priority
      1) {AppId}_is1 (including brace-typo variants like {GUID}}_is1)
      2) DisplayName equals app_name (tolerant compare)
      3) Subkey name equals <AppName>_is1 (tolerant compare)
      4) Any subkey whose name contains normalized AppId with braces stripped
    """
    if winreg is None:
        return "0"

    UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    hives = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]

    WOW64_32 = getattr(winreg, "KEY_WOW64_32KEY", 0)
    WOW64_64 = getattr(winreg, "KEY_WOW64_64KEY", 0)
    views = [winreg.KEY_READ, winreg.KEY_READ | WOW64_32, winreg.KEY_READ | WOW64_64]

    norm_app_id = _normalize_app_id(app_id)
    tolerant_app_name = _norm_name(app_name)

    def read_display_version(hive, access, subkey_name: str) -> str | None:
        k = _open_key(hive, UNINSTALL + "\\" + subkey_name, access)
        if not k:
            return None
        try:
            v = _get_val(k, "DisplayVersion")
            return str(v) if v else None
        finally:
            winreg.CloseKey(k)

    # 1) Try AppId-oriented candidates, including brace-typo variants
    if norm_app_id:
        id_variants = [
            "{" + norm_app_id + "}_is1",     # normal
            norm_app_id + "_is1",            # plain
            "{" + norm_app_id + "}}_is1",    # extra closing brace variant
        ]
        for hive in hives:
            for access in views:
                for target in id_variants:
                    v = read_display_version(hive, access, target)
                    if v:
                        return v

    # 2) Enumerate and match by tolerant DisplayName
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
                        if _norm_name(disp) == tolerant_app_name:
                            v = _get_val(sub, "DisplayVersion")
                            if v:
                                return str(v)
                    finally:
                        winreg.CloseKey(sub)
            finally:
                winreg.CloseKey(base)

    # 3) Subkey name equals <AppName>_is1 (tolerant compare)
    candidate_by_name = f"{app_name}_is1"
    for hive in hives:
        for access in views:
            v = read_display_version(hive, access, candidate_by_name)
            if v:
                return v

    # 4) If AppId known, find any subkey whose name contains it (braces stripped)
    if norm_app_id:
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
                        # strip all braces for comparison
                        plain = subname.replace("{", "").replace("}", "")
                        if norm_app_id in plain and subname.endswith("_is1"):
                            v = read_display_version(hive, access, subname)
                            if v:
                                return v
                finally:
                    winreg.CloseKey(base)

    return "0"


def _get_installed_version(app_name: str, app_id: str | None = None) -> str:
    """
    Priority:
      1) HKCU\\Software\\BranchingNovelTools\\<AppName>\\Version
      2) Inno Setup uninstall (robust scan)
      3) "0"
    """
    if winreg is None:
        return "0"

    # 1) Fixed custom key we write at install time
    custom_key = rf"Software\BranchingNovelTools\{app_name}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, custom_key) as k:
            v = winreg.QueryValueEx(k, "Version")[0]
            if v:
                return str(v)
    except OSError:
        pass

    # 2) Fallback to Inno uninstall scanning
    return _scan_inno_uninstall_for_version(app_name, app_id)


def _github_api_json(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "BranchingNovelTools-Updater/1.0 (+Windows)")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {}


def _pick_asset_download_url(release: dict, installer_name: str) -> str | None:
    assets = release.get("assets") or []
    for a in assets:
        if a.get("name") == installer_name:
            return a.get("browser_download_url")
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
    """Check GitHub for a newer release and optionally run the installer."""
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
