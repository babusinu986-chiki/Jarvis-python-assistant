from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jarvis_ai.reminders import ReminderStore


class ReminderStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ReminderStore(Path(self.temp_dir.name) / "reminders.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_list_and_remove(self) -> None:
        self.store.add("Practice the pitch")
        self.store.add("Check the demo")

        self.assertEqual(
            self.store.list(),
            ["Practice the pitch", "Check the demo"],
        )
        self.assertEqual(self.store.remove(0), "Practice the pitch")
        self.assertEqual(self.store.list(), ["Check the demo"])

    def test_duplicate_reminders_are_not_added_twice(self) -> None:
        self.store.add("Practice the pitch")
        self.store.add("practice the pitch")

        self.assertEqual(self.store.list(), ["Practice the pitch"])

    def test_empty_reminder_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add("   ")


if __name__ == "__main__":
    unittest.main()
