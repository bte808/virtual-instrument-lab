"""Opt-in checks that need a real Tk graphical session."""

import os
import unittest

import pytest


pytestmark = pytest.mark.gui


@unittest.skipUnless(os.environ.get("VIL_RUN_GUI_TESTS") == "1", "Set VIL_RUN_GUI_TESTS=1 for Tk smoke tests")
class GuiSmokeTests(unittest.TestCase):
    def test_presets_validation_exports_and_import(self):
        from virtual_instrument_lab.app import run_smoke_test

        report = run_smoke_test()
        self.assertEqual(report["presets"], 3)
        for check in (
            "input_error_recovery", "undefined_phase", "csv_export", "png_export",
            "settings_roundtrip", "cancelled_dialogs",
        ):
            self.assertTrue(report[check], check)


if __name__ == "__main__":
    unittest.main()
