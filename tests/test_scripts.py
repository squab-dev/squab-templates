"""Every image entry point and tool script parses, without a hand-maintained list."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scripts():
    # Same discovery as the release planner: one directory per image, plus the
    # shared build and per-game smoke tools.
    paths = sorted(ROOT.glob('images/*/squab-*')) + sorted(ROOT.glob('tools/*.sh'))
    return [path for path in paths if path.is_file()]


def interpreter(path):
    first = path.read_bytes().split(b'\n', 1)[0].decode(errors='replace')
    if not first.startswith('#!'):
        return None
    words = first[2:].split()
    name = Path(words[0]).name
    if name == 'env' and len(words) > 1:
        name = words[1]
    return 'sh' if name in ('sh', 'bash', 'ash') else 'python' if name.startswith('python') else None


class ScriptSyntaxTests(unittest.TestCase):
    def test_discovers_every_launcher_and_tool(self):
        found = {str(path.relative_to(ROOT)) for path in scripts()}
        for game in (path.parent.name for path in ROOT.glob('images/*/apko.yaml')):
            self.assertTrue(any(name.startswith(f'images/{game}/squab-{game}-launcher') for name in found), game)
        self.assertIn('tools/build.sh', found)

    def test_scripts_parse(self):
        for path in scripts():
            kind = interpreter(path)
            with self.subTest(script=str(path.relative_to(ROOT)), kind=kind):
                self.assertIsNotNone(kind, 'unknown interpreter')
                if kind == 'sh':
                    result = subprocess.run(['sh', '-n', str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    compile(path.read_text(), str(path), 'exec')


if __name__ == '__main__':
    unittest.main()
