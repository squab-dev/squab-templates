import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('palworld', str(ROOT / 'images/palworld/squab-palworld-launcher'))
spec = importlib.util.spec_from_loader(loader.name, loader)
palworld = importlib.util.module_from_spec(spec)
loader.exec_module(palworld)


class PalworldTests(unittest.TestCase):
    def test_managed_credentials_rotate_without_losing_gameplay_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'Config/LinuxServer/PalWorldSettings.ini'
            config.parent.mkdir(parents=True)
            config.write_text('[/Script/Pal.PalGameWorldSettings]\n'
                'OptionSettings=(ExpRate=2.5,ServerDescription="Friends, (only)",'
                'AdminPassword="old",RESTAPIEnabled=False,RCONEnabled=True,bUseAuth=False)\n')
            palworld.configure(root, 'f' * 64, 'My "world"', 8)
            written = config.read_text()
            self.assertIn('ExpRate=2.5', written)
            self.assertIn('ServerDescription="Friends, (only)"', written)
            self.assertIn('ServerName="My \\"world\\""', written)
            self.assertNotIn('"old"', written)
            self.assertIn('RESTAPIEnabled=True', written)
            self.assertIn('RCONEnabled=False', written)
            self.assertIn('bUseAuth=True', written)
            palworld.configure(root, 'a' * 64, 'My world', 12)
            self.assertNotIn('f' * 64, config.read_text())
            self.assertIn('ExpRate=2.5', config.read_text())

    def test_malformed_or_symlinked_settings_are_not_overwritten(self):
        for text in ['ServerName="unterminated', 'bad-field=1', 'Something=(a=1', 'Something=1)']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                palworld.settings_fields(text)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'Config/LinuxServer/PalWorldSettings.ini'
            config.parent.mkdir(parents=True)
            target = root / 'original'
            target.write_text('do not overwrite')
            config.symlink_to(target)
            with self.assertRaises(ValueError):
                palworld.configure(root, 'a' * 64, 'Name', 4)
            self.assertEqual(target.read_text(), 'do not overwrite')

    def test_readiness_requires_game_identity_and_a_loaded_world(self):
        for response, expected in [({'version':'v1','worldguid':'abcd'}, True),
                                   ({'version':'v1','worldguid':''}, False),
                                   ({'version':'v1'}, False), ([], False)]:
            with self.subTest(response=response), patch.object(palworld, 'api', return_value=json.dumps(response)):
                self.assertEqual(bool(palworld.healthy()), expected)

    def test_bounded_launch_settings(self):
        for value in ['0', '33', '-1', '1; touch file', '9' * 5000, '\u0661']:
            with self.subTest(value=value), patch.dict(os.environ, PALWORLD_PLAYERS=value), self.assertRaises(ValueError):
                palworld.integer('PALWORLD_PLAYERS', 32, 1, 32)

