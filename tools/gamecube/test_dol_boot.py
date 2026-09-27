#!/usr/bin/env python3
"""Check that the DOL the builder makes the El Torito boot image is loadable.

The GBI apploader (cubeboot-tools ppc/apploader) reads struct dol_header: 7 text
and 11 data file offsets, the matching addresses and sizes, then the bss
address, the bss size and the entry point, all inside 0x100 bytes.  al_check_dol
then rejects the image unless every section is 32 byte aligned, starts past the
header, stays inside the file, loads between 0x80000000 and 0x81200000, and the
entry point falls inside a text section.  build_iso.verify_boot_dol applies
those rules, and this test pins the layout they are read from.

Run directly: python3 tools/gamecube/test_dol_boot.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_iso

ROOT = Path(__file__).resolve().parents[2]
GBI = ROOT/'tools/gamecube/iso/gbi.hdr'
BUILT_DOLS = (ROOT/'build/cube/src/reVC.dol', ROOT/'build/wii/src/reVC.dol')
CLASSIC = build_iso.DOL_LAYOUT_CLASSIC


def buildable_dol(text=(0x80003100, 0x1000), data=(0x80403100, 0x800),
                  bss=(0x8040B100, 0x2000), entry=None, text_off=0x100):
    """Return a DOL the apploader would accept, as elf2dol would write it."""
    text_addr, text_size = text
    data_addr, data_size = data
    data_off = text_off + text_size
    header = bytearray(build_iso.DOL_HEADER_BYTES)
    for key, value in (('text_off', text_off), ('data_off', data_off),
                       ('text_addr', text_addr), ('data_addr', data_addr),
                       ('text_size', text_size), ('data_size', data_size),
                       ('bss_addr', bss[0]), ('bss_size', bss[1]),
                       ('entry', text_addr if entry is None else entry)):
        struct.pack_into('>I', header, CLASSIC[key], value)
    return bytes(header) + bytes(data_off + data_size - build_iso.DOL_HEADER_BYTES)


def word(dol, key):
    return struct.unpack_from('>I', dol, CLASSIC[key])[0]


def slot0(dol, key, value):
    """Return dol with the first slot of a header table replaced."""
    patched = bytearray(dol)
    struct.pack_into('>I', patched, CLASSIC[key], value)
    return bytes(patched)


def check_layout_constants():
    # struct dol_header, field by field.
    assert CLASSIC == {'text_off': 0x00, 'data_off': 0x1C, 'text_addr': 0x48,
                       'data_addr': 0x64, 'text_size': 0x90, 'data_size': 0xAC,
                       'bss_addr': 0xD8, 'bss_size': 0xDC, 'entry': 0xE0}, CLASSIC
    spans = [(CLASSIC[f'{name}_{kind}'], slots*4, f'{name}_{kind}')
             for name, slots in build_iso.DOL_SECTION_SLOTS
             for kind in ('off', 'addr', 'size')]
    spans += [(CLASSIC[key], 4, key) for key in ('bss_addr', 'bss_size', 'entry')]
    for offset, width, key in spans:
        assert offset + width <= build_iso.DOL_HEADER_BYTES, key
    for (_, end, _), (start, _, _) in zip(sorted(spans), sorted(spans)[1:]):
        assert end <= start, ('classic DOL fields overlap', spans)
    print('ok: header layout matches struct dol_header and is collision free')


def check_section_reader():
    dol = buildable_dol()
    sections = list(build_iso.dol_sections(dol))
    assert sections == [(0x100, 0x80003100, 0x1000), (0x1100, 0x80403100, 0x800)], sections
    assert [s[1] for s in build_iso.dol_sections(dol, 'data')] == [0x80403100]
    print('ok: sections are read as the apploader reads them')


def check_verifier():
    limit = build_iso.gbi_memory_limit(GBI.read_bytes())
    assert limit == 0x81800000, hex(limit)
    good = buildable_dol()
    build_iso.verify_boot_dol(good, limit)

    def rejected(dol, why):
        try:
            build_iso.verify_boot_dol(dol, limit)
        except ValueError as error:
            print(f'ok: rejected {why}: {error}')
            return
        raise AssertionError(f'verifier accepted {why}')

    rejected(slot0(good, 'text_off', 0x80), 'a section inside the header')
    rejected(slot0(good, 'text_off', 0x102), 'an unaligned section offset')
    rejected(slot0(good, 'data_addr', 0x80403101), 'an unaligned section address')
    rejected(slot0(good, 'text_size', 0x80000000), 'a section past the end of file')
    rejected(slot0(good, 'data_addr', 0x00403100), 'a section below 2GB')
    rejected(slot0(good, 'data_addr', 0x81803100), 'a section above 0x81200000')
    rejected(slot0(good, 'entry', 0x80004200), 'an entry point outside the text section')
    rejected(slot0(good, 'entry', 0x80004201), 'an unaligned entry point')
    rejected(slot0(good, 'bss_addr', 0x8200B100), 'bss above the GBI memory limit')
    print('ok: verifier accepts a loadable DOL and rejects the failure modes')


def check_built_dols():
    memory_limit = build_iso.gbi_memory_limit(GBI.read_bytes())
    for path in BUILT_DOLS:
        if not path.exists():
            print(f'skip: {path} not built')
            continue
        # The build ships the DOL elf2dol wrote, so that is what has to load.
        dol = path.read_bytes()
        build_iso.verify_boot_dol(dol, memory_limit)
        sections = list(build_iso.dol_sections(dol))
        assert [s[:2] for s in sections] == sorted(s[:2] for s in sections), path
        bss_end = word(dol, 'bss_addr') + word(dol, 'bss_size')
        assert bss_end <= memory_limit, (path, hex(bss_end))
        print(f'ok: {path.relative_to(ROOT)} '
              + ' '.join(f'{o:#x}->{a:#x}+{s:#x}' for o, a, s in sections) +
              f' entry {word(dol, "entry"):#x} bss end {bss_end:#x} '
              f'({bss_end - build_iso.MEM1_BASE:#x} of '
              f'{memory_limit - build_iso.MEM1_BASE:#x})')


if __name__ == '__main__':
    check_layout_constants()
    check_section_reader()
    check_verifier()
    check_built_dols()
    print('PASS')
