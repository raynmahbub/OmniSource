import unittest

from omnisource.permissions import compare_permissions


class PermissionDiffTests(unittest.TestCase):
    def test_diff_and_unknown(self):
        old = {"entitlements": ["old"], "privacy": {"NSCameraUsageDescription": "old"}}
        new = {
            "entitlements": ["new"],
            "privacy": {"NSCameraUsageDescription": "new", "NSPhotoLibraryUsageDescription": "photos"},
        }
        d = compare_permissions(new, old)
        self.assertEqual(d["entitlementsAdded"], ["new"])
        self.assertEqual(d["entitlementsRemoved"], ["old"])
        self.assertEqual(d["privacyAdded"], ["NSPhotoLibraryUsageDescription"])
        self.assertEqual(d["privacyChanged"], ["NSCameraUsageDescription"])
        self.assertIsNone(compare_permissions(new, None))
        self.assertIsNone(compare_permissions({}, old))


if __name__ == "__main__":
    unittest.main()
