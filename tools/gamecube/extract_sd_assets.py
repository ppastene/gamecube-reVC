#!/usr/bin/env python3
"""Extract the reVC ISO payload into a FAT/exFAT-ready SD card tree.

The game asks libfat for lowercase paths without the ISO ";1" version suffix
(dvdfs.c strips both when reading the real disc), so names are normalized here.
"""
import subprocess
import sys
from pathlib import Path

# Disc layout filler and El Torito metadata: needed by the ISO, not by the SD.
SKIP = {'disc_pad.bin', 'boot.catalog'}


def normalize(name):
	return name.split(';')[0].lower()


def main():
	iso = Path(sys.argv[1] if len(sys.argv) > 1 else 'out/reVC-GameCube.iso')
	out = Path(sys.argv[2] if len(sys.argv) > 2 else 'build/assets/gamecube/root')
	if not iso.is_file():
		sys.exit(f'no such ISO: {iso}')
	out.mkdir(parents=True, exist_ok=True)
	subprocess.run(['bsdtar', '-xf', str(iso), '-C', str(out)], check=True)

	renames = []
	for src in sorted(out.rglob('*'), key=lambda p: len(p.parts), reverse=True):
		if src.name in SKIP:
			src.unlink()
			continue
		want = normalize(src.name)
		if want != src.name:
			renames.append((src, src.with_name(want)))
	for src, dst in renames:
		if dst.exists():
			sys.exit(f'colision al normalizar: {dst}')
		src.rename(dst)

	files = [f for f in out.rglob('*') if f.is_file()]
	total = sum(f.stat().st_size for f in files)
	print(f'{out}: {len(files)} archivos, {total / 1048576:.1f} MB')


if __name__ == '__main__':
	main()
