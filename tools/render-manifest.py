"""Render an immutable catalog revision from a published image version tag."""
import argparse
from pathlib import Path

from release import render_manifest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', default='paper')
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release', help='release tag (vX.Y.Z) that repository artwork is pinned to')
    args = parser.parse_args()
    try:
        manifest = render_manifest(Path('.'), args.game, args.image, args.release)
    except ValueError as error:
        parser.error(str(error))
    write_json(args.output, manifest)


if __name__ == '__main__':
    main()
