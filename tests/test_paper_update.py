import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

loader=importlib.machinery.SourceFileLoader('paper_update',str(Path(__file__).resolve().parents[1]/'images/paper/squab-paper-update'))
spec=importlib.util.spec_from_loader(loader.name,loader)
update=importlib.util.module_from_spec(spec);loader.exec_module(update)


def build(number, body=b'jar', channel='STABLE', version='26.2'):
    sha=hashlib.sha256(body).hexdigest()
    name=f'paper-{version}-{number}.jar'
    return {'id':number,'channel':channel,'downloads':{'server:default':{'name':name,'size':len(body),'checksums':{'sha256':sha},'url':f'https://fill-data.papermc.io/v1/objects/{sha}/{name}'}}}


class PaperUpdateTests(unittest.TestCase):
    def test_only_highest_stable_build_of_selected_minecraft_version(self):
        self.assertEqual(update.metadata([build(129),build(131,channel='EXPERIMENTAL'),build(130)])[0],130)
        with self.assertRaises(update.UpdateError):update.metadata([build(1,version='26.3')])
        with self.assertRaises(update.UpdateError):update.metadata([build(1,channel='EXPERIMENTAL')])
        for field,value in [('url','https://evil.example/game.jar'),('size',update.MAX_JAR+1)]:
            data=build(1);data['downloads']['server:default'][field]=value
            with self.assertRaises(update.UpdateError):update.metadata([data])

    def test_atomic_checksum_failure_preserves_old_game_and_world(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);world=root/'world.dat';world.write_bytes(b'world')
            cache=root/'runtime';cache.mkdir();old=cache/('a'*64+'.jar');old.write_bytes(b'old')
            with patch.object(update,'fetch',side_effect=[io.BytesIO(json.dumps([build(130)]).encode()),io.BytesIO(b'bad')]):
                with self.assertRaises(update.UpdateError):update.update(cache)
            self.assertEqual(old.read_bytes(),b'old');self.assertEqual(world.read_bytes(),b'world')
            self.assertFalse(list(cache.glob('.download-*')))
            with patch.object(update,'fetch',side_effect=[io.BytesIO(json.dumps([build(130)]).encode()),io.BytesIO(b'jar')]):
                installed=update.update(cache)
            self.assertEqual(installed.read_bytes(),b'jar');self.assertFalse(old.exists())
            with patch.object(update,'fetch',return_value=io.BytesIO(json.dumps([build(130)]).encode())) as fetch:
                self.assertEqual(update.update(cache),installed);self.assertEqual(fetch.call_count,1)
