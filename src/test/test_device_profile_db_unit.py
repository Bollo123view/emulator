#!/usr/bin/env python3
"""
Unit tests for src/utils/device_profile_db.py.
"""

import os
import re
import shutil
import tempfile
import unittest
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.utils.device_profile_db import DeviceProfileDB


def is_valid_luhn_checksum(number: str) -> bool:
    digits = [int(d) for d in number]
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


class TestDeviceProfileDB(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="device-profile-db-")
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.db = DeviceProfileDB(db_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_profiles_are_created(self):
        manufacturers = set(self.db.get_manufacturers())
        self.assertTrue({"samsung", "google", "xiaomi", "oneplus"}.issubset(manufacturers))

        for manufacturer in ["samsung", "google", "xiaomi", "oneplus"]:
            self.assertTrue(os.path.exists(os.path.join(self.temp_dir, f"{manufacturer}.json")))

    def test_get_device_profile_uses_latest_android_version_by_default(self):
        profile = self.db.get_device_profile("samsung", "Galaxy S21")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["properties"]["ro.build.version.release"], "12")
        self.assertEqual(profile["properties"]["ro.build.version.sdk"], "31")

    def test_get_device_profile_invalid_version_falls_back_to_latest(self):
        profile = self.db.get_device_profile("google", "Pixel 6", android_version="99.0")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["properties"]["ro.build.version.release"], "13")
        self.assertEqual(profile["properties"]["ro.build.version.sdk"], "33")

    def test_get_devices_unknown_manufacturer_returns_empty(self):
        self.assertEqual(self.db.get_devices("unknown-brand"), [])

    def test_add_and_delete_device_profile_for_new_manufacturer(self):
        profile = {
            "android_versions": ["12.0"],
            "properties": {
                "ro.build.fingerprint": "acme/test/test:12/TEST/001:user/release-keys",
                "ro.build.tags": "release-keys",
                "ro.build.type": "user",
                "ro.product.device": "test",
            },
            "sensors": ["accelerometer", "gyroscope"],
        }

        added = self.db.add_device_profile("acme", "Acme Phone", profile)
        self.assertTrue(added)
        self.assertIn("acme", self.db.get_manufacturers())
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "acme.json")))

        deleted = self.db.delete_device_profile("acme", "Acme Phone")
        self.assertTrue(deleted)
        self.assertNotIn("acme", self.db.get_manufacturers())
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "acme.json")))

    def test_delete_one_device_keeps_manufacturer_when_others_remain(self):
        first_profile = {
            "android_versions": ["12.0"],
            "properties": {
                "ro.build.fingerprint": "acme/one/one:12/ONE/001:user/release-keys",
                "ro.build.tags": "release-keys",
                "ro.build.type": "user",
                "ro.product.device": "one",
            },
            "sensors": ["accelerometer"],
        }
        second_profile = {
            "android_versions": ["12.0"],
            "properties": {
                "ro.build.fingerprint": "acme/two/two:12/TWO/001:user/release-keys",
                "ro.build.tags": "release-keys",
                "ro.build.type": "user",
                "ro.product.device": "two",
            },
            "sensors": ["gyroscope"],
        }

        self.assertTrue(self.db.add_device_profile("acme", "Acme One", first_profile))
        self.assertTrue(self.db.add_device_profile("acme", "Acme Two", second_profile))
        self.assertTrue(self.db.delete_device_profile("acme", "Acme One"))

        self.assertIn("acme", self.db.get_manufacturers())
        self.assertEqual(self.db.get_devices("acme"), ["Acme Two"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "acme.json")))

    def test_generate_hardware_profile_populates_identifiers_and_defaults(self):
        hardware_profile = self.db.generate_hardware_profile("xiaomi", "Mi 11", android_version="12.0")

        self.assertIsNotNone(hardware_profile)
        self.assertEqual(hardware_profile["manufacturer"], "xiaomi")
        self.assertEqual(hardware_profile["model"], "Mi 11")
        self.assertIn("identifiers", hardware_profile)
        self.assertRegex(hardware_profile["identifiers"]["android_id"], r"^[0-9a-f]{16}$")
        self.assertRegex(hardware_profile["identifiers"]["mac_address"], r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")
        self.assertIn("ro.serialno", hardware_profile["build_prop"])
        self.assertIn("ro.boot.serialno", hardware_profile["build_prop"])
        self.assertIn("net.hostname", hardware_profile["build_prop"])
        expected_prefix = hardware_profile["build_prop"]["ro.product.device"]
        self.assertRegex(hardware_profile["build_prop"]["net.hostname"], rf"^{re.escape(expected_prefix)}-\d{{4}}$")

        for sensor in ["accelerometer", "gyroscope", "magnetometer"]:
            self.assertTrue(hardware_profile["sensors"][sensor])

    def test_generated_hardware_profile_contains_luhn_valid_imei(self):
        hardware_profile = self.db.generate_hardware_profile("samsung", "Galaxy S21", android_version="12.0")
        self.assertIsNotNone(hardware_profile)
        imei = hardware_profile["identifiers"]["imei"]
        self.assertRegex(imei, r"^\d{15}$")
        self.assertTrue(is_valid_luhn_checksum(imei))


if __name__ == "__main__":
    unittest.main(verbosity=2)
