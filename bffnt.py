#!/usr/bin/python
import argparse
import math
import os.path
import struct

# FINF = Font Info
# TGLP = Texture Glyph
# CWDH = Character Widths
# CMAP = Character Mapping

VERSION = 0x04000000

FFNT_HEADER_SIZE = 0x14
FINF_HEADER_SIZE = 0x20
TGLP_HEADER_SIZE = 0x20
CWDH_HEADER_SIZE = 0x10
CMAP_HEADER_SIZE = 0x14

FFNT_HEADER_MAGIC = 'FFNT'
FINF_HEADER_MAGIC = 'FINF'
TGLP_HEADER_MAGIC = 'TGLP'
CWDH_HEADER_MAGIC = 'CWDH'
CMAP_HEADER_MAGIC = 'CMAP'

FFNT_HEADER_STRUCT = '=4s2H3I'
FINF_HEADER_STRUCT = '%s4sI4B2H4B3I'
TGLP_HEADER_STRUCT = '%s4sI4BI6HI'
CWDH_HEADER_STRUCT = '%s4sI2HI'
CMAP_HEADER_STRUCT = '%s4sI4HI'

FORMAT_RGBA8 = 0x00
FORMAT_RGB8 = 0x01
FORMAT_RGBA5551 = 0x02
FORMAT_RGB565 = 0x03
FORMAT_RGBA4 = 0x04
FORMAT_LA8 = 0x05
FORMAT_HILO8 = 0x06
FORMAT_L8 = 0x07
FORMAT_A8 = 0x08
FORMAT_LA4 = 0x09
FORMAT_L4 = 0x0A
FORAMT_A4 = 0x0B
FORMAT_ETC1 = 0x0C
FORMAT_ETC1A4 = 0x0D

PIXEL_FORMATS = {
    FORMAT_RGBA8: 'RGBA8',
    FORMAT_RGB8: 'RGB8',
    FORMAT_RGBA5551: 'RGBA5551',
    FORMAT_RGB565: 'RGB565',
    FORMAT_RGBA4: 'RGBA4',
    FORMAT_LA8: 'LA8',
    FORMAT_HILO8: 'HILO8',
    FORMAT_L8: 'L8',
    FORMAT_A8: 'A8',
    FORMAT_LA4: 'LA4',
    FORMAT_L4: 'L4',
    FORAMT_A4: 'A4',
    FORMAT_ETC1: 'ETC1',
    FORMAT_ETC1A4: 'ETC1A4'
}

MAPPING_DIRECT = 0x00
MAPPING_TABLE = 0x01
MAPPING_SCAN = 0x02

MAPPING_METHODS = {
    MAPPING_DIRECT: 'Direct',
    MAPPING_TABLE: 'Table',
    MAPPING_SCAN: 'Scan'
}


class Bffnt:
    order = None
    invalid = False
    tglp = {}
    cwdh_sections = []
    cmap_sections = []

    def __init__(self, verbose=False, debug=False):
        self.verbose = verbose
        self.debug = debug

    def read(self, filename):
        data = open(filename, 'r').read()
        self.file_size = len(data)

        self._parse_header(data[:FFNT_HEADER_SIZE])
        position = FFNT_HEADER_SIZE
        if self.invalid:
            return

        self._parse_finf(data[position:position + FINF_HEADER_SIZE])
        if self.invalid:
            return

        # navigate to TGLP (offset skips the MAGIC+size)
        position = self.tglp_offset - 8
        self._parse_tglp_header(data[position:position + TGLP_HEADER_SIZE])
        if self.invalid:
            return

        position = self.tglp['sheetOffset']
        self._parse_tglp_data(data[position:position + self.tglp['size']])

        # navigate to CWDH (offset skips the MAGIC+size)
        cwdh = self.cwdh_offset
        while cwdh > 0:
            position = cwdh - 8
            cwdh = self._parse_cwdh_header(data[position:position + CWDH_HEADER_SIZE])
            if self.invalid:
                return

            position += CWDH_HEADER_SIZE
            info = self.cwdh_sections[-1]
            self._parse_cwdh_data(info, data[position:position + info['size'] - CWDH_HEADER_SIZE])

        # navigate to CMAP (offset skips the MAGIC+size)
        cmap = self.cmap_offset
        while cmap > 0:
            position = cmap - 8
            cmap = self._parse_cmap_header(data[position:position + CMAP_HEADER_SIZE])
            if self.invalid:
                return

            position += CMAP_HEADER_SIZE
            info = self.cmap_sections[-1]
            self._parse_cmap_data(info, data[position:position + info['size'] - CMAP_HEADER_SIZE])

    def _parse_header(self, data):
        magic, bom, header_size, version, file_size, sections = struct.unpack(FFNT_HEADER_STRUCT, data)

        if magic != FFNT_HEADER_MAGIC:
            print('Invalid FFNT magic bytes: %s (expected %s)' % (magic, FFNT_HEADER_MAGIC))
            self.invalid = True
            return

        if bom == 0xFFFE:
            self.order = '>'
        elif bom == 0xFEFF:
            self.order = '<'

        if self.order is None:
            print('Invalid byte-order marker: 0x%x (expected 0xFFFE or 0xFEFF)' % bom)
            self.invalid = True
            return

        if version != VERSION:
            print('Unknown version: 0x%08x (expected 0x%08x)' % (version, VERSION))
            self.invalid = True
            return

        if header_size != FFNT_HEADER_SIZE:
            print('Invalid header size: %d (expected %d)' % (header_size, FFNT_HEADER_SIZE))
            self.invalid = True
            return

        if file_size != self.file_size:
            print('Invalid file size: %d (expected %d)' % (file_size, self.file_size))
            self.invalid = True
            return

        self.sections = sections

        print('FFNT Magic: %s' % magic)
        print('FFNT BOM: %s (0x%x)' % (self.order, bom))
        print('FFNT Header Size: %d' % header_size)
        print('FFNT Version: 0x%08x' % version)
        print('FFNT File Size: %d' % file_size)
        print('FFNT Sections: %d\n' % sections)

    def _parse_finf(self, data):
        magic, section_size, font_type, height, width, ascent, line_feed, alter_char_idx, def_left, def_glyph_width, \
        def_char_width, encoding, tglp_offset, cwdh_offset, cmap_offset \
            = struct.unpack(FINF_HEADER_STRUCT % self.order, data)

        if magic != FINF_HEADER_MAGIC:
            print('Invalid FINF magic bytes: %s (expected %s)' % (magic, FINF_HEADER_MAGIC))
            self.invalid = True
            return

        if section_size != FINF_HEADER_SIZE:
            print('Invalid FINF size: %d (expected %d)' % (section_size, FINF_HEADER_SIZE))
            self.invalid = True
            return

        self.font_info = {
            'height': height,
            'width': width,
            'ascent': ascent,
            'lineFeed': line_feed,
            'alterCharIdx': alter_char_idx,
            'defaultWidth': {
                'left': def_left,
                'glyphWidth': def_glyph_width,
                'charWidth': def_char_width
            },
            'encoding': encoding
        }

        self.tglp_offset = tglp_offset
        self.cwdh_offset = cwdh_offset
        self.cmap_offset = cmap_offset

        print('FINF Magic: %s' % magic)
        print('FINF Section Size: %d' % section_size)
        print('FINF Font Type: 0x%x' % font_type)
        print('FINF Height: %d' % height)
        print('FINF Width: %d' % width)
        print('FINF Ascent: %d' % ascent)
        print('FINF Line feed: %d' % line_feed)
        print('FINF Alter Character Index: %d' % alter_char_idx)
        print('FINF Default Width, Left: %d' % def_left)
        print('FINF Default Glyph Width: %d' % def_glyph_width)
        print('FINF Default Character Width: %d' % def_char_width)
        print('FINF Encoding: %d' % encoding)
        print('FINF TGLP Offset: 0x%08x' % tglp_offset)
        print('FINF CWDH Offset: 0x%08x' % cwdh_offset)
        print('FINF CMAP Offset: 0x%08x\n' % cmap_offset)

    def _parse_tglp_header(self, data):
        magic, section_size, cell_width, cell_height, num_sheets, max_char_width, sheet_size, baseline_position, \
        sheet_pixel_format, num_sheet_rows, num_sheet_cols, sheet_width, sheet_height, sheet_data_offset \
            = struct.unpack(TGLP_HEADER_STRUCT % self.order, data)

        if magic != TGLP_HEADER_MAGIC:
            print('Invalid TGLP magic bytes: %s (expected %s)' % (magic, TGLP_HEADER_MAGIC))
            self.invalid = True
            return

        self.tglp = {
            'size': section_size,
            'cell': {
                'width': cell_width,
                'height': cell_height
            },
            'sheetCount': num_sheets,
            'sheet': {
                'size': sheet_size,
                'rows': num_sheet_rows,
                'cols': num_sheet_cols,
                'width': sheet_width,
                'height': sheet_height,
                'format': sheet_pixel_format
            },
            'sheetOffset': sheet_data_offset
        }

        print('TGLP Magic: %s' % magic)
        print('TGLP Section Size: %d' % section_size)
        print('TGLP Cell Width: %d' % cell_width)
        print('TGLP Cell Height: %d' % cell_height)
        print('TGLP Sheet Count: %d' % num_sheets)
        print('TGLP Max Character Width: %d' % max_char_width)
        print('TGLP Sheet Size: %d' % sheet_size)
        print('TGLP Baseline Position: %d' % baseline_position)
        print('TGLP Sheet Image Format: 0x%x (%s)' % (sheet_pixel_format, PIXEL_FORMATS[sheet_pixel_format]))
        print('TGLP Sheet Rows: %d' % num_sheet_rows)
        print('TGLP Sheet Columns: %d' % num_sheet_cols)
        print('TGLP Sheet Width: %d' % sheet_width)
        print('TGLP Sheet Height: %d' % sheet_height)
        print('TGLP Sheet Data Offset: 0x%08x\n' % sheet_data_offset)

    def _parse_tglp_data(self, data):
        position = self.tglp['sheetOffset']
        self.tglp['sheets'] = {}
        for i in range(self.tglp['sheetCount']):
            sheet = data[position:position + self.tglp['sheet']['size']]
            self.tglp['sheets'][i] = self._sheet_to_bitmap(sheet)

    def _sheet_to_bitmap(self, data):
        width = self.tglp['sheet']['width']
        height = self.tglp['sheet']['height']
        format = self.tglp['sheet']['format']

        data_width = width
        data_height = height

        # increase the size of the image to a power-of-two boundary, if necessary
        width = 1 << int(math.ceil(math.log(width, 2)))
        height = 1 << int(math.ceil(math.log(height, 2)))

        # initialize empty bitmap memory (RGBA8)
        bmp = [[0, 0, 0, 0]] * (width * height)

        tile_width = width / 8
        tile_height = height / 8

        # sheet is composed of 8x8 pixel tiles
        for tile_y in range(tile_height):
            for tile_x in range(tile_width):

                # tile is composed of 2x2 sub-tiles
                for y in range(2):
                    for x in range(2):

                        # sub-tile is composed of 2x2 pixel groups
                        for y2 in range(2):
                            for x2 in range(2):

                                # pixel group is composed of 2x2 pixels (finally)
                                for y3 in range(2):
                                    for x3 in range(2):
                                        # if the final y value is beyond the input data's height then don't read it
                                        if tile_y + y + y2 + y3 >= data_height:
                                            continue
                                        # same for the x and the input data width
                                        if tile_x + x + x2 + x3 >= data_width:
                                            continue

                                        pixel_x = (x3 + (x2 * 2) + (x * 4) + (tile_x * 8))
                                        pixel_y = (y3 + (y2 * 2) + (y * 4) + (tile_y * 8))

                                        data_x = (x3 + (x2 * 4) + (x * 16) + (tile_x * 64))
                                        data_y = ((y3 * 2) + (y2 * 8) + (y * 32) + (tile_y * width * 8))

                                        data_pos = data_x + data_y
                                        bmp_pos = pixel_x + (pixel_y * width)

                                        # TODO: get this based on the pixel format...
                                        # A4 = 4 bits of alpha, 15 possible values, each unit is worth 17/255 alpha
                                        # since we've got 2 pixels per 8-bit byte we need to trim off the other bits
                                        # so we can just have a single pixel
                                        shift = (data_pos & 1) * 4
                                        byte = ord(data[data_pos / 2])
                                        alpha = ((byte >> shift) & 0xF) * 0x11
                                        bmp[bmp_pos] = (0xFF, 0xFF, 0xFF, alpha)

        return bmp

    def _get_pixel_data(self, data, format, index):
        if format == FORMAT_RGBA8:
            pass

        elif format == FORMAT_RGB8:
            pass

        elif format == FORMAT_RGBA5551:
            pass

        elif format == FORMAT_RGB565:
            pass

        elif format == FORMAT_RGBA4:
            pass

        elif format == FORMAT_LA8:
            pass

        elif format == FORMAT_HILO8:
            pass

    def _parse_cwdh_header(self, data):
        magic, section_size, start_index, end_index, next_cwdh_offset \
            = struct.unpack(CWDH_HEADER_STRUCT % self.order, data)

        if magic != CWDH_HEADER_MAGIC:
            print('Invalid CWDH magic bytes: %s (expected %s)' % (magic, CWDH_HEADER_MAGIC))
            self.invalid = True
            return

        self.cwdh_sections.append({
            'size': section_size,
            'start': start_index,
            'end': end_index
        })

        print('CWDH Magic: %s' % magic)
        print('CWDH Section Size: %d' % section_size)
        print('CWDH Start Index: %d' % start_index)
        print('CWDH End Index: %d' % end_index)
        print('CWDH Next CWDH Offset: 0x%x\n' % next_cwdh_offset)

        return next_cwdh_offset

    def _parse_cwdh_data(self, info, data):
        count = info['end'] - info['start'] + 1
        output = []
        position = 0
        for i in range(count):
            left, glyph, char = struct.unpack('%sb2B' % self.order, data[position:position + 3])
            position += 3
            output.append({
                'left': left,
                'glyph': glyph,
                'char': char
            })

    def _parse_cmap_header(self, data):
        magic, section_size, code_begin, code_end, map_method, unknown, next_cmap_offset \
            = struct.unpack(CMAP_HEADER_STRUCT % self.order, data)

        if magic != CMAP_HEADER_MAGIC:
            print('Invalid CMAP magic bytes: %s (expected %s)' % (magic, CMAP_HEADER_MAGIC))

        self.cmap_sections.append({
            'size': section_size,
            'begin': code_begin,
            'end': code_end,
            'type': map_method
        })

        print('CMAP Magic: %s' % magic)
        print('CMAP Section Size: %d' % section_size)
        print('CMAP Code Begin: 0x%x' % code_begin)
        print('CMAP Code End: 0x%x' % code_end)
        print('CMAP Mapping Method: 0x%x (%s)' % (map_method, MAPPING_METHODS[map_method]))
        print('CMAP Next CMAP Offset: 0x%x' % next_cmap_offset)

        print('\nCMAP Unknown: 0x%x\n' % unknown)

        return next_cmap_offset

    def _parse_cmap_data(self, info, data):
        type = info['type']
        if type == MAPPING_DIRECT:
            info['indexOffset'] = struct.unpack('%sH' % self.order, data[2])

        elif type == MAPPING_TABLE:
            count = info['end'] - info['begin'] + 1
            position = 0
            output = []
            for i in range(count):
                offset = struct.unpack('%sH' % self.order, data[position:position + 2])
                position += 2
                output.append(offset)
            info['indexTable'] = output

        elif type == MAPPING_SCAN:
            position = 0
            count = struct.unpack('%sH' % self.order, data[position:position + 2])[0]
            position += 2
            output = {}
            for i in range(count):
                code, offset = struct.unpack('%s2H' % self.order, data[position:position + 4])
                position += 4
                output[code] = offset
            info['entries'] = output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BFFNT Converter Tool')
    parser.add_argument('-v', '--verbose', help='print more data when working', action='store_true', default=False)
    parser.add_argument('-d', '--debug', help='print debug information', action='store_true', default=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-c', '--create', help='create BFFNT file from plain files', action='store_true', default=False)
    group.add_argument('-x', '--extract', help='extract BFFNT into basic files', action='store_true', default=False)
    parser.add_argument('-f', '--file', metavar='bffnt', help='BFFNT file', required=True)
    args = parser.parse_args()

    if args.extract and not os.path.exists(args.file):
        pass

    bffnt = Bffnt()
    bffnt.read(args.file)
