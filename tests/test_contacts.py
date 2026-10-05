from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_ai.assistant import JarvisAssistant
from jarvis_ai.contacts import ContactStore


class ContactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        (self.data_dir / "contacts.json").write_text(
            json.dumps(
                {
                    "bablu": {
                        "phone": "+919861271063",
                        "aliases": ["babu", "brother"],
                    },
                    "mom": {
                        "phone": "+917873574987",
                        "aliases": ["mother", "mama", "mum", ""],
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolves_names_and_aliases_and_ignores_empty_alias(self) -> None:
        contacts = ContactStore(self.data_dir / "contacts.json")

        self.assertEqual(contacts.resolve("Bablu").phone, "919861271063")
        self.assertEqual(contacts.resolve("brother").name, "bablu")
        self.assertEqual(contacts.resolve("mother").name, "mom")
        self.assertEqual(contacts.resolve("mum").name, "mom")
        self.assertNotIn("", contacts.aliases())

    def test_message_requires_confirmation_before_opening_whatsapp(self) -> None:
        assistant = JarvisAssistant(self.data_dir, dry_run=False)

        with patch.object(assistant.executor, "_open") as mock_open:
            prepared = assistant.handle(
                "send a WhatsApp message to Bablu saying Hello, I am coming"
            )
            mock_open.assert_not_called()
            confirmed = assistant.handle("yes")

        self.assertEqual(prepared.action, "prepare_whatsapp_message")
        self.assertIn("Should I open it", prepared.message)
        self.assertEqual(confirmed.action, "open_whatsapp_message")
        mock_open.assert_called_once_with(
            "https://wa.me/919861271063?text=Hello%2C+I+am+coming"
        )

    def test_alias_works_and_no_cancels_without_opening(self) -> None:
        assistant = JarvisAssistant(self.data_dir, dry_run=False)

        with patch.object(assistant.executor, "_open") as mock_open:
            prepared = assistant.handle("message mother I will call you later")
            cancelled = assistant.handle("no")

        self.assertIn("Mom", prepared.message)
        self.assertEqual(cancelled.action, "cancel_whatsapp_message")
        mock_open.assert_not_called()

    def test_recognition_variation_mum_says_is_supported(self) -> None:
        assistant = JarvisAssistant(self.data_dir, dry_run=True)

        result = assistant.handle(
            "send a WhatsApp message to mum says I will go later"
        )

        self.assertEqual(result.action, "prepare_whatsapp_message")
        self.assertIn("Mom", result.message)
        self.assertIn("I will go later", result.message)

    def test_unknown_contact_does_not_create_pending_message(self) -> None:
        assistant = JarvisAssistant(self.data_dir, dry_run=True)

        result = assistant.handle("send message to Rahul saying Hello")
        follow_up = assistant.handle("yes")

        self.assertIn("don't know Rahul", result.message)
        self.assertNotEqual(follow_up.action, "open_whatsapp_message")

    def test_understands_message_first_spoken_variation(self) -> None:
        assistant = JarvisAssistant(self.data_dir, dry_run=True)

        result = assistant.handle(
            "send message to Hello, I am coming to Bablu"
        )

        self.assertEqual(result.action, "prepare_whatsapp_message")
        self.assertIn("Hello, I am coming", result.message)
        self.assertIn("Bablu", result.message)


if __name__ == "__main__":
    unittest.main()
