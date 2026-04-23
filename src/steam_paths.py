"""
Steam and Empires path detection utilities.

Provides cross-platform auto-detection of Steam library locations
and Empires game directory paths.
"""

import os
import sys
import platform
from typing import List, Optional


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32" or platform.system() == "Windows"


def expand_steam_path(path: str) -> str:
    """Expand ~ and resolve the path."""
    return os.path.realpath(os.path.expanduser(path))


import re

def _get_windows_steam_paths() -> List[str]:
    """Get Windows Steam library paths from registry and libraryfolders.vdf."""
    paths = []
    steam_install_paths = []

    # Try to get Steam path from registry
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"
        )
        try:
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            if steam_path and os.path.exists(steam_path):
                steam_install_paths.append(steam_path)
                common_path = os.path.join(steam_path, "steamapps", "common")
                if os.path.exists(common_path):
                    paths.append(common_path)
        except OSError:
            pass
        winreg.CloseKey(key)
    except OSError:
        pass

    # Also check registry for SteamLibrary locations
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam")
        try:
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            if steam_path and os.path.exists(steam_path):
                if steam_path not in steam_install_paths:
                    steam_install_paths.append(steam_path)
                common_path = os.path.join(steam_path, "steamapps", "common")
                if os.path.exists(common_path) and common_path not in paths:
                    paths.append(common_path)
        except OSError:
            pass
        winreg.CloseKey(key)
    except OSError:
        pass

    # Read libraryfolders.vdf to find all Steam libraries
    for steam_path in steam_install_paths:
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf_path):
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Match "path" "C:\\SteamLibrary" or similar
                # VDF uses double backslashes which might be escaped, so match carefully
                matches = re.finditer(r'"path"\s+"([^"]+)"', content)
                for match in matches:
                    # Replace double backslashes with single backslash
                    lib_path = match.group(1).replace("\\\\", "\\")
                    common_path = os.path.join(lib_path, "steamapps", "common")
                    if os.path.exists(common_path) and common_path not in paths:
                        paths.append(common_path)
            except OSError:
                pass

    return paths


def get_steam_base_paths() -> List[str]:
    """Get platform-appropriate Steam library base paths.

    Returns a list of Steam library base directories that exist on the system.
    """
    paths = []

    if is_windows():
        # Get paths from Windows registry
        registry_paths = _get_windows_steam_paths()
        paths.extend(registry_paths)

        # Common Windows Steam locations
        windows_paths = [
            os.path.expanduser("~/Steam/steamapps/common"),
            "C:\\Program Files (x86)\\Steam\\steamapps\\common",
            "C:\\Program Files\\Steam\\steamapps\\common",
        ]
        for p in windows_paths:
            if os.path.exists(p):
                expanded = expand_steam_path(p)
                if expanded not in paths:
                    paths.append(expanded)

        # Check for SteamLibrary folders on all drives (D:, E:, etc.)
        # SteamLibrary can be on secondary drives
        for drive in ["D:", "E:", "F:", "G:"]:
            drive_path = f"{drive}\\SteamLibrary\\steamapps\\common"
            if os.path.exists(drive_path) and drive_path not in paths:
                paths.append(drive_path)

            # Also check without "SteamLibrary" prefix
            steam_lib = f"{drive}\\SteamApps\\common"  # Some older setups
            if os.path.exists(steam_lib) and steam_lib not in paths:
                paths.append(steam_lib)
    else:
        # Linux Steam library locations
        # Primary: ~/.local/share/Steam (modern Steam on Linux)
        steam_root = os.path.expanduser("~/.local/share/Steam")
        if os.path.exists(steam_root):
            linux_base = os.path.join(steam_root, "steamapps", "common")
            if os.path.exists(linux_base):
                paths.append(linux_base)

        # Secondary: ~/.steam/steam/steamapps/common (legacy/proton)
        legacy_steam = os.path.expanduser("~/.steam/steam/steamapps/common")
        if os.path.exists(legacy_steam) and legacy_steam not in paths:
            paths.append(legacy_steam)

        # Check for Steam Library folders (can be on separate drives)
        # Look in common mount points for external Steam Libraries
        common_mount_bases = [
            "/run/media",
            "/media",
            "/mnt",
        ]
        for mount_base in common_mount_bases:
            if os.path.exists(mount_base):
                try:
                    for user_dir in os.listdir(mount_base):
                        user_path = os.path.join(mount_base, user_dir)
                        if os.path.isdir(user_path):
                            for root, dirs, files in os.walk(user_path):
                                # Look for SteamLibrary folders
                                if "SteamLibrary" in dirs:
                                    steam_lib = os.path.join(
                                        root, "SteamLibrary", "steamapps", "common"
                                    )
                                    if (
                                        os.path.exists(steam_lib)
                                        and steam_lib not in paths
                                    ):
                                        paths.append(steam_lib)
                                # Stop after finding one level deep
                                if root.count(os.sep) - user_path.count(os.sep) > 2:
                                    break
                except (PermissionError, OSError):
                    pass

    return paths


def find_empires_path() -> Optional[str]:
    """Find Empires game directory.

    Searches through Steam library locations for the Empires empires folder.
    Returns the path to the empires directory (containing maps/, materials/, etc.)
    or None if not found.
    """
    for base in get_steam_base_paths():
        empires = os.path.join(base, "Empires", "empires")
        if os.path.exists(empires):
            return empires
    return None


def find_empires_bin() -> Optional[str]:
    """Find Empires bin directory.

    Searches through Steam library locations for the Empires bin folder
    containing vbsp.exe and other SDK tools.
    Returns the path to the bin directory or None if not found.
    """
    for base in get_steam_base_paths():
        empires_bin = os.path.join(base, "Empires", "bin")
        if os.path.exists(empires_bin):
            # Verify vbsp.exe exists
            vbsp = os.path.join(empires_bin, "vbsp.exe")
            if os.path.exists(vbsp):
                return empires_bin
    return None


def validate_empires_path(path: str) -> tuple[bool, str]:
    """Validate that a path is a valid Empires installation.

    Args:
        path: Path to the Empires "empires" directory (containing maps/, materials/, etc.)

    Returns:
        Tuple of (is_valid, message)
    """
    if not path:
        return False, "No path provided"

    # The path should be the "empires" directory directly
    if not os.path.exists(path):
        return False, "Path does not exist"

    maps_dir = os.path.join(path, "maps")
    if not os.path.exists(maps_dir):
        return False, "Not a valid Empires folder (maps folder missing)"

    return True, "Valid"


def validate_empires_bin(path: str) -> tuple[bool, str]:
    """Validate that a path contains VBSP compiler tools.

    Args:
        path: Path to the Empires bin directory

    Returns:
        Tuple of (is_valid, message)
    """
    if not path:
        return False, "No path provided"

    if not os.path.exists(path):
        return False, "Bin directory does not exist"

    vbsp = os.path.join(path, "vbsp.exe")
    if not os.path.exists(vbsp):
        return False, "VBSP.exe not found in bin directory"

    return True, "Valid"
