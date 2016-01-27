#!/usr/bin/python
import argparse
import os.path
import struct

FFNT_HEADER_MAGIC = 'FFNT'
FINF_HEADER_MAGIC = 'FINF'
TGLP_HEADER_MAGIC = 'TGLP'
CWDH_HEADER_MAGIC = 'CWDH'
CMAP_HEADER_MAGIC = 'CMAP'

FFNT_HEADER_STRUCT = '=4sHIH3I'
FINF_HEADER_STRUCT = '%s4sIBBHbBBBIIIBBBB'


class Bffnt:
    def __init__(self):
        pass

    def _parse_header(self, data):
        magic, bom, header_size, version, file_size, sections = struct.unpack(FFNT_HEADER_MAGIC, data)

    def _parse_finf(self, data):
        magic, section_size, font_type, line_feed, alter_char_index, left_width, glyph_width, char_width, encoding, \
        tglp_offset, cwdh_offset, cmap_offset, height, width, ascent, padding = struct.unpack(FINF_HEADER_MAGIC, data)

    def _parse_tglp(self, data):
        pass

    def _parse_cwdh(self, data):
        pass

    def _parse_cmap(self, data):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BFFNT Converter Tool')
    parser.add_argument('-v', '--verbose', help='print more data when working', action='store_true', default=False)
    parser.add_argument('-d', '--debug', help='print debug information', action='store_true', default=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-c', '--create', help='create BFFNT file from plain files', default=False)
    group.add_argument('-x', '--extract', help='extract BFFNT into basic files', default=False)
    group.add_argument('-f', '--file', metavar='bffnt', help='BFFNT file', required=True)
    args = parser.parse_args()

    if args.extract and not os.path.exists(args.file):
        pass
