"""Small, dependency-free Windows media and navigation controls."""

from __future__ import annotations

import ctypes
import os


class WindowsMediaController:
    """Send only the allow-listed keys needed by Jarvis.

    The media play/pause key controls the current Windows media session. Alt+Left
    asks the foreground application to navigate back when that app supports it.
    """

    VK_MENU = 0x12
    VK_CONTROL = 0x11
    VK_F4 = 0x73
    VK_LEFT = 0x25
    VK_W = 0x57
    VK_MEDIA_PLAY_PAUSE = 0xB3
    KEYEVENTF_KEYUP = 0x0002

    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def _key(self, virtual_key: int, *, key_up: bool = False) -> None:
        flags = self.KEYEVENTF_KEYUP if key_up else 0
        ctypes.windll.user32.keybd_event(virtual_key, 0, flags, 0)

    def toggle_playback(self) -> bool:
        if self.dry_run:
            return True
        if os.name != "nt":
            return False
        try:
            self._key(self.VK_MEDIA_PLAY_PAUSE)
            self._key(self.VK_MEDIA_PLAY_PAUSE, key_up=True)
        except (AttributeError, OSError):
            return False
        return True

    def go_back(self) -> bool:
        if self.dry_run:
            return True
        if os.name != "nt":
            return False
        try:
            self._key(self.VK_MENU)
            self._key(self.VK_LEFT)
            self._key(self.VK_LEFT, key_up=True)
            self._key(self.VK_MENU, key_up=True)
        except (AttributeError, OSError):
            return False
        return True

    def close_tab(self) -> bool:
        """Close only the foreground browser tab using Ctrl+W."""
        if self.dry_run:
            return True
        if os.name != "nt":
            return False
        try:
            self._key(self.VK_CONTROL)
            self._key(self.VK_W)
            self._key(self.VK_W, key_up=True)
            self._key(self.VK_CONTROL, key_up=True)
        except (AttributeError, OSError):
            return False
        return True

    def close_window(self) -> bool:
        """Close the foreground window, matching the window's cross button."""
        if self.dry_run:
            return True
        if os.name != "nt":
            return False
        try:
            self._key(self.VK_MENU)
            self._key(self.VK_F4)
            self._key(self.VK_F4, key_up=True)
            self._key(self.VK_MENU, key_up=True)
        except (AttributeError, OSError):
            return False
        return True
