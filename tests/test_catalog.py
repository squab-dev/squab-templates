"""The public catalog only references valid committed immutable releases."""
import json
import re
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


class PublicCatalogTests(unittest.TestCase):
    def test_index_references_valid_immutable_releases(self):
        index = json.loads((ROOT / "catalog.json").read_text())
        self.assertEqual(set(index), {"schema_version", "manifests"})
        self.assertEqual(index["schema_version"], 1)
        paths = index["manifests"]
        self.assertTrue(1 <= len(paths) <= 100)
        self.assertEqual(len(paths), len(set(paths)))
        revision_ids = set()
        schemas = list((ROOT / "api/vendor").rglob("*template*.json"))
        self.assertEqual(len(schemas), 1)
        schema = json.loads(schemas[0].read_text())
        for path in paths:
            self.assertRegex(path, r"^releases/[a-zA-Z0-9._/-]+\.json$")
            self.assertFalse(any(part in {"", ".", ".."} for part in path.split("/")))
            raw = (ROOT / path).read_bytes()
            self.assertLessEqual(len(raw), 1024 * 1024)
            manifest = json.loads(raw)
            jsonschema.validate(manifest, schema)
            self.assertRegex(manifest["image"], r"^ghcr\.io/.+@sha256:[a-f0-9]{64}$")
            self.assertNotIn(manifest["revision_id"], revision_ids)
            revision_ids.add(manifest["revision_id"])
            self.assertFalse(manifest["test_only"])
