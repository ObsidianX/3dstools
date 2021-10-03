#!/usr/bin/python
# -*- coding: utf-8 -*-
import argparse
import json
import math
import os.path
import struct
import sys

import png

# FINF = Font Info
# TGLP = Texture Glyph
# CWDH = Character Widths
# CMAP = Character Mapping

VERSIONS = (0x04000000, 0x03000000)

FFNT_HEADER_SIZE = 0x14
FINF_HEADER_SIZE = 0x20
TGLP_HEADER_SIZE = 0x20
CWDH_HEADER_SIZE = 0x10
CMAP_HEADER_SIZE = 0x14

FFNT_HEADER_MAGIC = (b'FFNT', b'FFNU')
FINF_HEADER_MAGIC = b'FINF'
TGLP_HEADER_MAGIC = b'TGLP'
CWDH_HEADER_MAGIC = b'CWDH'
CMAP_HEADER_MAGIC = b'CMAP'

FFNT_HEADER_STRUCT = '%s4s2H3I'
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
FORMAT_A4 = 0x0B
#TODO: Fix this, in fact, it should be BC4
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
    FORMAT_A4: 'A4',
    FORMAT_ETC1: 'ETC1',
    FORMAT_ETC1A4: 'ETC1A4'
}

PIXEL_FORMAT_SIZE = {
    FORMAT_RGBA8: 32,
    FORMAT_RGB8: 24,
    FORMAT_RGBA5551: 16,
    FORMAT_RGB565: 16,
    FORMAT_RGBA4: 16,
    FORMAT_LA8: 16,
    FORMAT_HILO8: 16,
    FORMAT_L8: 8,
    FORMAT_A8: 8,
    FORMAT_LA4: 8,
    FORMAT_L4: 4,
    FORMAT_A4: 4,
    FORMAT_ETC1: 64,
    FORMAT_ETC1A4: 128
}

ETC_INDIV_RED1_OFFSET = 60
ETC_INDIV_GREEN1_OFFSET = 52
ETC_INDIV_BLUE1_OFFSET = 44

ETC_DIFF_RED1_OFFSET = 59
ETC_DIFF_GREEN1_OFFSET = 51
ETC_DIFF_BLUE_OFFSET = 43

ETC_RED2_OFFSET = 56
ETC_GREEN2_OFFSET = 48
ETC_BLUE2_OFFSET = 40

ETC_TABLE1_OFFSET = 37
ETC_TABLE2_OFFSET = 34

ETC_DIFFERENTIAL_BIT = 33
ETC_ORIENTATION_BIT = 32

ETC_MODIFIERS = [
    [2, 8],
    [5, 17],
    [9, 29],
    [13, 42],
    [18, 60],
    [24, 80],
    [33, 106],
    [47, 183]
]

MAPPING_DIRECT = 0x00
MAPPING_TABLE = 0x01
MAPPING_SCAN = 0x02

MAPPING_METHODS = {
    MAPPING_DIRECT: 'Direct',
    MAPPING_TABLE: 'Table',
    MAPPING_SCAN: 'Scan'
}

TGLP_DATA_OFFSET = 0x2000


class Bffnt:
    order = None
    invalid = False
    file_size = 0
    filename = ''
    font_info = {}
    tglp = {}
    cwdh_sections = []
    cmap_sections = []

    def __init__(self, verbose=False, debug=False, load_order='<'):
        self.verbose = verbose
        self.debug = debug
        self.load_order = load_order

    def read(self, filename):
        data = open(filename, 'rb').read()
        self.file_size = len(data)
        self.filename = filename

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

        # convert pixels to RGBA8
        self._parse_tglp_data(data)

    def load(self, json_filename):
        json_data = json.load(open(json_filename, 'r', encoding="utf-8"))

        self.order = self.load_order
        self.version = json_data['version']
        self.filetype = json_data['fileType']

        self.font_info = json_data['fontInfo']
        tex_info = json_data['textureInfo']

        sheet_pixel_format = None
        for value in PIXEL_FORMATS.keys():
            if PIXEL_FORMATS[value] == tex_info['sheetInfo']['colorFormat']:
                sheet_pixel_format = value
                break

        if sheet_pixel_format is None:
            print('Invalid pixel format: %s' % tex_info['sheetInfo']['colorFormat'])
            self.invalid = True
            return

        self.tglp = {
            'glyph': {
                'width': tex_info['glyph']['width'],
                'height': tex_info['glyph']['height'],
                'baseline': tex_info['glyph']['baseline']
            },
            'sheetCount': tex_info['sheetCount'],
            'sheet': {
                'cols': tex_info['sheetInfo']['cols'],
                'rows': tex_info['sheetInfo']['rows'],
                'width': tex_info['sheetInfo']['width'],
                'height': tex_info['sheetInfo']['height'],
                'format': sheet_pixel_format
            }
        }

        widths = json_data['glyphWidths']
        cwdh = {
            'start': 0,
            'end': 0,
            'data': []
        }

        widest = 0
        glyph_indicies = list(widths.keys())
        glyph_indicies.sort(key=self._int_sort)

        cwdh['end'] = int(glyph_indicies[-1], 10)

        for idx in glyph_indicies:
            cwdh['data'].append(widths[idx])
            if widths[idx]['char'] > widest:
                widest = widths[idx]['char']

        self.tglp['maxCharWidth'] = widest

        self.cwdh_sections = [cwdh]

        glyph_map = json_data['glyphMap']
        glyph_ords = list(glyph_map.keys())
        glyph_ords.sort()
        cmap = {
            'start': ord(glyph_ords[0]),
            'end': ord(glyph_ords[-1]),
            'type': MAPPING_SCAN,
            'entries': {}
        }

        for entry in range(cmap['start'], cmap['end'] + 1):
            try:  #Python2
                utf16 = unichr(entry)
            except:  #Python3
                utf16 = chr(entry)
            if utf16 in glyph_map:
                cmap['entries'][utf16] = glyph_map[utf16]

        self.cmap_sections = [cmap]

    def _int_sort(self, n):
        return int(n, 10)

    def extract(self, ensure_ascii=True):
        if self.verbose:
            print('Extracting...')
        basename_ = os.path.splitext(os.path.basename(self.filename))[0]

        glyph_widths = {}
        for cwdh in self.cwdh_sections:
            for index in range(cwdh['start'], cwdh['end'] + 1):
                glyph_widths[index] = cwdh['data'][index - cwdh['start']]

        glyph_mapping = {}
        for cmap in self.cmap_sections:
            if cmap['type'] == MAPPING_DIRECT:
                for code in range(cmap['start'], cmap['end']):
                    try:  #Python2
                        glyph_mapping[unichr(code)] = code - cmap['start'] + cmap['indexOffset']
                    except:
                        glyph_mapping[chr(code)] = code - cmap['start'] + cmap['indexOffset']
            elif cmap['type'] == MAPPING_TABLE:
                for code in range(cmap['start'], cmap['end']):
                    index = cmap['indexTable'][code - cmap['start']]
                    if index != 0xFFFF:
                        try:  #Python2
                            glyph_mapping[unichr(code)] = index
                        except:
                            glyph_mapping[chr(code)] = index
            elif cmap['type'] == MAPPING_SCAN:
                for code in cmap['entries'].keys():
                    glyph_mapping[code] = cmap['entries'][code]

        # save JSON manifest
        json_file_ = open('%s_manifest.json' % basename_, 'w', encoding="utf-8")
        json_file_.write(json.dumps({
            'version': self.version,
            'fileType': self.filetype,
            'fontInfo': self.font_info,
            'textureInfo': {
                'glyph': self.tglp['glyph'],
                'sheetCount': self.tglp['sheetCount'],
                'sheetInfo': {
                    'cols': self.tglp['sheet']['cols'],
                    'rows': self.tglp['sheet']['rows'],
                    'width': self.tglp['sheet']['width'],
                    'height': self.tglp['sheet']['height'],
                    'colorFormat': PIXEL_FORMATS[self.tglp['sheet']['format']]
                }
            },
            'glyphWidths': glyph_widths,
            'glyphMap': glyph_mapping
        }, indent=2, sort_keys=True, ensure_ascii=ensure_ascii))
        json_file_.close()

        # save sheet bitmaps
        for i in range(self.tglp['sheetCount']):
            sheet = self.tglp['sheets'][i]
            width = sheet['width']
            height = sheet['height']
            png_data = []
            for y in range(height):
                row = []
                for x in range(width):
                    for color in sheet['data'][x + (y * width)]:
                        row.append(color)

                png_data.append(row)

            file_ = open('%s_sheet%d.png' % (basename_, i), 'wb')
            writer = png.Writer(width, height, alpha=True)
            writer.write(file_, png_data)
            file_.close()
        print('Done')

    def save(self, filename):
        if self.verbose:
            print('Packing...')
        file_ = open(filename, 'wb')
        basename_ = os.path.splitext(os.path.basename(filename))[0]
        section_count = 0

        bom = 0
        if self.order == '>':
            bom = 0xFFFE
        elif self.order == '<':
            bom = 0xFEFF

        # write header
        file_size_pos = 0x0C
        section_count_pos = 0x10
        magic = self.filetype.upper().encode('ascii')

        data = struct.pack(FFNT_HEADER_STRUCT % self.order, magic, bom, FFNT_HEADER_SIZE, self.version, 0, 0)
        file_.write(data)

        position = FFNT_HEADER_SIZE

        # write finf
        if self.verbose:
            print('Writing FINF...')
        font_info = self.font_info
        default_width = font_info['defaultWidth']
        finf_tglp_offset_pos = position + 0x14
        finf_cwdh_offset_pos = position + 0x18
        finf_cmap_offset_pos = position + 0x1C
        data = struct.pack(FINF_HEADER_STRUCT % self.order, FINF_HEADER_MAGIC, FINF_HEADER_SIZE, font_info['fontType'],
                           font_info['height'], font_info['width'], font_info['ascent'], font_info['lineFeed'],
                           font_info['alterCharIdx'], default_width['left'], default_width['glyphWidth'],
                           default_width['charWidth'], font_info['encoding'], 0, 0, 0)
        file_.write(data)
        position += FINF_HEADER_SIZE

        section_count += 1

        # write tglp
        if self.verbose:
            print('Writing TGLP...')
        tglp = self.tglp
        sheet = tglp['sheet']
        tglp_size_pos = position + 0x04
        tglp_data_size = int(sheet['width'] * sheet['height'] * (PIXEL_FORMAT_SIZE[sheet['format']] / 8.0))

        file_.seek(finf_tglp_offset_pos)
        file_.write(struct.pack('%sI' % self.order, position + 8))
        file_.seek(position)

        tglp_start_pos = position
        data = struct.pack(TGLP_HEADER_STRUCT % self.order, TGLP_HEADER_MAGIC, 0, tglp['glyph']['width'],
                       tglp['glyph']['height'], tglp['sheetCount'], tglp['maxCharWidth'], tglp_data_size,
                       tglp['glyph']['baseline'], sheet['format'], sheet['cols'], sheet['rows'], sheet['width'],
                       sheet['height'], TGLP_DATA_OFFSET)
        file_.write(data)

        file_.seek(TGLP_DATA_OFFSET)
        position = TGLP_DATA_OFFSET

        section_count += 1

        for idx in range(tglp['sheetCount']):
            sheet_filename = '%s_sheet%d.png' % (basename_, idx)
            sheet_file_ = open(sheet_filename, 'rb')

            reader = png.Reader(file=sheet_file_)
            width, height, pixels, metadata = reader.read()

            if width != sheet['width'] or height != sheet['height']:
                print('Invalid sheet PNG:\nexpected an image size of %dx%d but %s is %dx%d' %
                      (sheet['width'], sheet['height'], sheet_filename, width, height))
                self.invalid = True
                return

            if metadata['bitdepth'] != 8 or metadata['alpha'] != True:
                print('Invalid sheet PNG:\nexpected a PNG8 with alpha')

            self.tglp['sheet']['size'] = tglp_data_size

            bmp = []
            for row in list(pixels):
                for pixel in range(len(row) // 4):
                    bmp.append(row[pixel * 4:pixel * 4 + 4])
            data = self._sheet_to_bitmap(bmp, to_tglp=True)
            file_.write(data)
            position += len(data)

            sheet_file_.close()

        file_.seek(tglp_size_pos)
        file_.write(struct.pack('%sI' % self.order, position - tglp_start_pos))

        file_.seek(finf_cwdh_offset_pos)
        file_.write(struct.pack('%sI' % self.order, position + 8))
        file_.seek(position)

        # write cwdh
        if self.verbose:
            print('Writing CWDH...')
        prev_cwdh_offset_pos = 0
        for cwdh in self.cwdh_sections:
            section_count += 1
            if prev_cwdh_offset_pos > 0:
                file_.seek(prev_cwdh_offset_pos)
                file_.write(struct.pack('%sI' % self.order, position + 8))
                file_.seek(position)

            size_pos = position + 0x04
            prev_cwdh_offset_pos = position + 0x0C

            start_pos = position
            data = struct.pack(CWDH_HEADER_STRUCT % self.order, CWDH_HEADER_MAGIC, 0, cwdh['start'], cwdh['end'] - 1, 0)
            file_.write(data)
            position += CWDH_HEADER_SIZE

            for code in range(cwdh['start'], cwdh['end'] + 1):
                widths = cwdh['data'][code]
                for key in ('left', 'glyph', 'char'):
                    file_.write(struct.pack('=b', widths[key]))
                    position += 1

            file_.seek(size_pos)
            file_.write(struct.pack('%sI' % self.order, position - start_pos))
            file_.seek(position)

        file_.seek(finf_cmap_offset_pos)
        file_.write(struct.pack('%sI' % self.order, position + 8))
        file_.seek(position)

        # write cmap
        if self.verbose:
            print('Writing CMAP...')
        prev_cmap_offset_pos = 0
        for cmap in self.cmap_sections:
            section_count += 1
            if prev_cmap_offset_pos > 0:
                file_.seek(prev_cmap_offset_pos)
                file_.write(struct.pack('%sI' % self.order, position + 8))
                file_.seek(position)

            size_pos = position + 0x04
            prev_cmap_offset_pos = position + 0x10

            start_pos = position
            data = struct.pack(CMAP_HEADER_STRUCT % self.order, CMAP_HEADER_MAGIC, 0, cmap['start'], cmap['end'],
                               cmap['type'], 0, 0)
            file_.write(data)
            position += CMAP_HEADER_SIZE

            file_.write(struct.pack('%sH' % self.order, len(cmap['entries'])))
            position += 2

            if cmap['type'] == MAPPING_DIRECT:
                file_.write(struct.pack('%sH' % self.order, cmap['indexOffset']))
                position += 2
            elif cmap['type'] == MAPPING_TABLE:
                for index in cmap['indexTable']:
                    file_.write(struct.pack('%sH' % self.order, index))
                    position += 2
            elif cmap['type'] == MAPPING_SCAN:
                keys = list(cmap['entries'].keys())
                keys.sort()
                for code in keys:
                    index = cmap['entries'][code]
                    file_.write(struct.pack('%s2H' % self.order, ord(code), index))
                    position += 4

            file_.seek(size_pos)
            file_.write(struct.pack('%sI' % self.order, position - start_pos))
            file_.seek(position)

        # fill in size/offset placeholders
        file_.seek(file_size_pos)
        file_.write(struct.pack('%sI' % self.order, position))

        file_.seek(section_count_pos)
        file_.write(struct.pack('%sI' % self.order, section_count))
        if self.verbose:
            print('Done!')

    def _parse_header(self, data):
        bom = struct.unpack_from('>H', data, 4)[0]
        if bom == 0xFFFE:
            self.order = '<'
        elif bom == 0xFEFF:
            self.order = '>'

        if self.order is None:
            print('Invalid byte-order marker: 0x%x (expected 0xFFFE or 0xFEFF)' % bom)
            self.invalid = True
            return
            
        magic, bom, header_size, self.version, file_size, sections = struct.unpack(FFNT_HEADER_STRUCT % self.order, data)

        if magic not in FFNT_HEADER_MAGIC:
            print('Invalid FFNT magic bytes: %s (expected %s)' % (magic, FFNT_HEADER_MAGIC))
            self.invalid = True
            return
        self.filetype = magic.decode('ascii').lower()


        if self.version not in VERSIONS:
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

        if self.debug:
            print('FFNT Magic: %s' % magic)
            print('FFNT BOM: %s (0x%x)' % (self.order, bom))
            print('FFNT Header Size: %d' % header_size)
            print('FFNT Version: 0x%08x' % self.version)
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
            'fontType': font_type,
            'encoding': encoding
        }

        self.tglp_offset = tglp_offset
        self.cwdh_offset = cwdh_offset
        self.cmap_offset = cmap_offset

        if self.debug:
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
                sheet_pixel_format, num_sheet_cols, num_sheet_rows, sheet_width, sheet_height, sheet_data_offset \
                = struct.unpack(TGLP_HEADER_STRUCT % self.order, data)

        if magic != TGLP_HEADER_MAGIC:
            print('Invalid TGLP magic bytes: %s (expected %s)' % (magic, TGLP_HEADER_MAGIC))
            self.invalid = True
            return

        self.tglp = {
            'size': section_size,
            'glyph': {
                'width': cell_width,
                'height': cell_height,
                'baseline': baseline_position
            },
            'sheetCount': num_sheets,
            'sheet': {
                'size': sheet_size,
                'cols': num_sheet_cols,
                'rows': num_sheet_rows,
                'width': sheet_width,
                'height': sheet_height,
                'format': sheet_pixel_format
            },
            'sheetOffset': sheet_data_offset
        }

        if self.debug:
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
        self.tglp['sheets'] = []
        format_ = self.tglp['sheet']['format']
        for i in range(self.tglp['sheetCount']):
            sheet = data[position:position + self.tglp['sheet']['size']]
            if format_ == FORMAT_ETC1 or format_ == FORMAT_ETC1A4:
                bmp_data = self._decompress_etc1(sheet)
            else:
                bmp_data = self._sheet_to_bitmap(sheet)
            self.tglp['sheets'].append({
                'width': self.tglp['sheet']['width'],
                'height': self.tglp['sheet']['height'],
                'data': bmp_data
            })
            position = position + self.tglp['sheet']['size']

    def _decompress_etc1(self, data):
        width = self.tglp['sheet']['width']
        height = self.tglp['sheet']['height']

        with_alpha = self.tglp['sheet']['format'] == FORMAT_ETC1A4

        block_size = 16 if with_alpha else 8

        bmp = [[0, 0, 0, 0]] * width * height

        tile_width = int(math.ceil(width / 8.0))
        tile_height = int(math.ceil(height / 8.0))

        # here's the kicker: there will always be a power-of-two amount of tiles
        tile_width = 1 << int(math.ceil(math.log(tile_width, 2)))
        tile_height = 1 << int(math.ceil(math.log(tile_height, 2)))

        pos = 0

        # texture is composed of 8x8 tiles
        for tile_y in range(tile_height):
            for tile_x in range(tile_width):

                # in ETC1 mode each tile is composed of 2x2, compressed sub-tiles, 4x4 pixels each
                for block_y in range(2):
                    for block_x in range(2):
                        data_pos = pos
                        pos += block_size

                        block = data[data_pos:data_pos + block_size]

                        alphas = 0xFFffFFffFFffFFff
                        if with_alpha:
                            alphas = struct.unpack('%sQ' % self.order, block[:8])[0]
                            block = block[8:]

                        pixels = struct.unpack('%sQ' % self.order, block)[0]

                        # how colors are stored in the high-order 32 bits
                        differential = (pixels >> ETC_DIFFERENTIAL_BIT) & 0x01 == 1
                        # how the sub blocks are divided, 0 = 2x4, 1 = 4x2
                        horizontal = (pixels >> ETC_ORIENTATION_BIT) & 0x01 == 1
                        # once the colors are decoded for the sub block this determines how to shift the colors
                        # which modifier row to use for sub block 1
                        table1 = ETC_MODIFIERS[(pixels >> ETC_TABLE1_OFFSET) & 0x07]
                        # which modifier row to use for sub block 2
                        table2 = ETC_MODIFIERS[(pixels >> ETC_TABLE2_OFFSET) & 0x07]

                        color1 = [0, 0, 0]
                        color2 = [0, 0, 0]

                        if differential:
                            # grab the 5-bit code words
                            r = ((pixels >> ETC_DIFF_RED1_OFFSET) & 0x1F)
                            g = ((pixels >> ETC_DIFF_GREEN1_OFFSET) & 0x1F)
                            b = ((pixels >> ETC_DIFF_BLUE_OFFSET) & 0x1F)

                            # extends from 5 to 8 bits by duplicating the 3 most significant bits
                            color1[0] = (r << 3) | ((r >> 2) & 0x07)
                            color1[1] = (g << 3) | ((g >> 2) & 0x07)
                            color1[2] = (b << 3) | ((b >> 2) & 0x07)

                            # add the 2nd block, 3-bit code words to the original words (2's complement!)
                            r += self._complement((pixels >> ETC_RED2_OFFSET) & 0x07, 3)
                            g += self._complement((pixels >> ETC_GREEN2_OFFSET) & 0x07, 3)
                            b += self._complement((pixels >> ETC_BLUE2_OFFSET) & 0x07, 3)

                            # extend from 5 to 8 bits like before
                            color2[0] = (r << 3) | ((r >> 2) & 0x07)
                            color2[1] = (g << 3) | ((g >> 2) & 0x07)
                            color2[2] = (b << 3) | ((b >> 2) & 0x07)
                        else:
                            # 4 bits per channel, 16 possible values

                            # 1st block
                            color1[0] = ((pixels >> ETC_INDIV_RED1_OFFSET) & 0x0F) * 0x11
                            color1[1] = ((pixels >> ETC_INDIV_GREEN1_OFFSET) & 0x0F) * 0x11
                            color1[2] = ((pixels >> ETC_INDIV_BLUE1_OFFSET) & 0x0F) * 0x11

                            # 2nd block
                            color2[0] = ((pixels >> ETC_RED2_OFFSET) & 0x0F) * 0x11
                            color2[1] = ((pixels >> ETC_GREEN2_OFFSET) & 0x0F) * 0x11
                            color2[2] = ((pixels >> ETC_BLUE2_OFFSET) & 0x0F) * 0x11

                        # now that we have two sub block pixel colors to start from,
                        # each pixel is read as a modifier value

                        # 16 pixels are described with 2 bits each,
                        # one selecting the sign, the second the value

                        amounts = pixels & 0xFFFF
                        signs = (pixels >> 16) & 0xFFFF

                        for pixel_y in range(4):
                            for pixel_x in range(4):
                                x = pixel_x + (block_x * 4) + (tile_x * 8)
                                y = pixel_y + (block_y * 4) + (tile_y * 8)

                                if x >= width:
                                    continue
                                if y >= height:
                                    continue

                                offset = pixel_x * 4 + pixel_y

                                if horizontal:
                                    table = table1 if pixel_y < 2 else table2
                                    color = color1 if pixel_y < 2 else color2
                                else:
                                    table = table1 if pixel_x < 2 else table2
                                    color = color1 if pixel_x < 2 else color2

                                # determine the amount to shift the color
                                amount = table[(amounts >> offset) & 0x01]
                                # and in which direction. 1 = -, 0 = +
                                sign = (signs >> offset) & 0x01

                                if sign == 1:
                                    amount *= -1

                                red = max(min(color[0] + amount, 0xFF), 0)
                                green = max(min(color[1] + amount, 0xFF), 0)
                                blue = max(min(color[2] + amount, 0xFF), 0)
                                alpha = ((alphas >> (offset * 4)) & 0x0F) * 0x11

                                pixel_pos = y * width + x

                                bmp[pixel_pos] = [red, green, blue, alpha]
        return bmp

    def _complement(self, input_, bits):
        if input_ >> (bits - 1) == 0:
            return input_
        return input_ - (1 << bits)

    def _sheet_to_bitmap(self, data, to_tglp=False):
        width = self.tglp['sheet']['width']
        height = self.tglp['sheet']['height']
        format_ = self.tglp['sheet']['format']

        data_width = width
        data_height = height

        # increase the size of the image to a power-of-two boundary, if necessary
        width = 1 << int(math.ceil(math.log(width, 2)))
        height = 1 << int(math.ceil(math.log(height, 2)))

        if to_tglp:
            bmp = data
            data = [0] * self.tglp['sheet']['size']
        else:
            # initialize empty bitmap memory (RGBA8)
            bmp = [[0, 0, 0, 0]] * (width * height)

        tile_width = width // 8
        tile_height = height // 8

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

                                        if to_tglp:
                                            # OR the data since there are pixel formats which use the same byte for
                                            # multiple pixels (A4/L4)
                                            bytes_ = self._get_tglp_pixel_data(bmp, format_, bmp_pos)
                                            if len(bytes_) > 1:
                                                data[data_pos:data_pos + len(bytes_)] = bytes_
                                            else:
                                                if PIXEL_FORMAT_SIZE[format_] == 4:
                                                    data_pos //= 2
                                                data[data_pos] |= bytes_[0]
                                        else:
                                            bmp[bmp_pos] = self._get_pixel_data(data, format_, data_pos)

        if to_tglp:
            return struct.pack('%dB' % len(data), *data)
        else:
            return bmp

    def _get_pixel_data(self, data, format_, index):
        red = green = blue = alpha = 0

        # rrrrrrrr gggggggg bbbbbbbb aaaaaaaa
        if format_ == FORMAT_RGBA8:
            red, green, blue, alpha = struct.unpack('4B', data[index * 4:index * 4 + 4])

        # rrrrrrrr gggggggg bbbbbbbb
        elif format_ == FORMAT_RGB8:
            red, green, blue = struct.unpack('3B', data[index * 3:index * 3 + 3])
            alpha = 255

        # rrrrrgg gggbbbbba
        elif format_ == FORMAT_RGBA5551:
            b1, b2 = struct.unpack('2B', data[index * 2:index * 2 + 2])

            red = ((b1 >> 3) & 0x1F)
            green = (b1 & 0x07) | ((b2 >> 6) & 0x03)
            blue = (b2 >> 1) & 0x1F
            alpha = (b2 & 0x01) * 255

        # rrrrrggg gggbbbbb
        elif format_ == FORMAT_RGB565:
            b1, b2 = struct.unpack('2B', data[index * 2:index * 2 + 2])

            red = (b1 >> 3) & 0x1F
            green = (b1 & 0x7) | ((b2 >> 5) & 0x7)
            blue = (b2 & 0x1F)
            alpha = 255

        # rrrrgggg bbbbaaaa
        elif format_ == FORMAT_RGBA4:
            b1, b2 = struct.unpack('2B', data[index * 2:index * 2 + 2])

            red = ((b1 >> 4) & 0x0F) * 0x11
            alpha = (b1 & 0x0F) * 0x11
            blue = ((b2 >> 4) & 0x0F) * 0x11
            green = (b2 & 0x0F) * 0x11

        # llllllll aaaaaaaa
        elif format_ == FORMAT_LA8:
            l, alpha = struct.unpack('2B', data[index * 2:index * 2 + 2])
            red = green = blue = l

        # ??
        elif format_ == FORMAT_HILO8:
            # TODO
            pass

        # llllllll
        elif format_ == FORMAT_L8:
            red = green = blue = struct.unpack('B', data[index:index + 1])[0]
            alpha = 255

        # aaaaaaaa
        elif format_ == FORMAT_A8:
            alpha = struct.unpack('B', data[index:index + 1])[0]
            red = green = blue = 255

        # llllaaaa
        elif format_ == FORMAT_LA4:
            la = struct.unpack('B', data[index:index + 1])[0]
            red = green = blue = ((la >> 4) & 0x0F) * 0x11
            alpha = (la & 0x0F) * 0x11

        # llll
        elif format_ == FORMAT_L4:
            l = struct.unpack('B', data[index // 2])[0]
            shift = (index & 1) * 4
            red = green = blue = ((l >> shift) & 0x0F) * 0x11
            alpha = 255

        # aaaa
        elif format_ == FORMAT_A4:
            try:  #Python2:
                byte = ord(data[index // 2])
            except:
                byte = data[index // 2]
            shift = (index & 1) * 4
            alpha = ((byte >> shift) & 0x0F) * 0x11
            green = red = blue = 0xFF

        return red, green, blue, alpha

    def _get_tglp_pixel_data(self, bmp, format_, index):
        # bmp data: tuple (r, g, b, a)
        # output: list of bytes: [255, 255]
        red, green, blue, alpha = bmp[index]

        if format_ == FORMAT_RGBA8:
            return [red, green, blue, alpha]

        elif format_ == FORMAT_RGB8:
            return [red, green, blue]

        # rrrrrggg ggbbbbba
        elif format_ == FORMAT_RGBA5551:
            r5 = (red // 8) & 0x1F
            g5 = (green // 8) & 0x1F
            b5 = (blue // 8) & 0x1F
            a = 1 if alpha > 0 else 0

            b1 = (r5 << 3) | (g5 >> 2)
            b2 = ((g5 << 6) | (b5 << 1) | a) & 0xFF
            return [b1, b2]

        # rrrrrggg gggbbbbb
        elif format_ == FORMAT_RGB565:
            r5 = (red // 8) & 0x1F
            g6 = (green // 4) & 0x3F
            b5 = (blue // 8) & 0x1F

            b1 = (r5 << 3) | (g6 >> 3)
            b2 = ((g6 << 5) | b5) & 0xFF
            return [b1, b2]

        # rrrrgggg bbbbaaaa
        elif format_ == FORMAT_RGBA4:
            r4 = (red // 0x11) & 0x0F
            g4 = (green // 0x11) & 0x0F
            b4 = (blue // 0x11) & 0x0F
            a4 = (alpha // 0x11) & 0x0F

            b1 = (r4 << 4) | g4
            b2 = (b4 << 4) | a4
            return [b1, b2]

        # llllllll aaaaaaaa
        elif format_ == FORMAT_LA8:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))

            return [l, alpha]

        elif format_ == FORMAT_HILO8:
            # TODO
            pass

        # llllllll
        elif format_ == FORMAT_L8:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))

            return [l]

        # aaaaaaaa
        elif format_ == FORMAT_A8:
            return [alpha]

        # llllaaaa
        elif format_ == FORMAT_LA4:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722)) // 0x11
            a = (alpha // 0x11) & 0x0F

            b = (l << 4) | a
            return [b]

        # llll
        elif format_ == FORMAT_L4:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))
            shift = (index & 1) * 4
            return [l << shift]

        # aaaa
        elif format_ == FORMAT_A4:
            alpha = (bmp[index][3] // 0x11) & 0xF
            shift = (index & 1) * 4
            return [alpha << shift]

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

        if self.debug:
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
        info['data'] = output

    def _parse_cmap_header(self, data):
        magic, section_size, code_begin, code_end, map_method, unknown, next_cmap_offset \
            = struct.unpack(CMAP_HEADER_STRUCT % self.order, data)

        if magic != CMAP_HEADER_MAGIC:
            print('Invalid CMAP magic bytes: %s (expected %s)' % (magic, CMAP_HEADER_MAGIC))

        self.cmap_sections.append({
            'size': section_size,
            'start': code_begin,
            'end': code_end,
            'type': map_method
        })

        if self.debug:
            print('CMAP Magic: %s' % magic)
            print('CMAP Section Size: %d' % section_size)
            print('CMAP Code Begin: 0x%x' % code_begin)
            print('CMAP Code End: 0x%x' % code_end)
            print('CMAP Mapping Method: 0x%x (%s)' % (map_method, MAPPING_METHODS[map_method]))
            print('CMAP Next CMAP Offset: 0x%x' % next_cmap_offset)

            print('\nCMAP Unknown: 0x%x\n' % unknown)

        return next_cmap_offset

    def _parse_cmap_data(self, info, data):
        if self.verbose:
            print('\nParsing CMAP...')
        type_ = info['type']
        if type_ == MAPPING_DIRECT:
            info['indexOffset'] = struct.unpack('%sH' % self.order, data[:2])[0]

        elif type_ == MAPPING_TABLE:
            count = info['end'] - info['start'] + 1
            position = 0
            output = []
            for i in range(count):
                offset = struct.unpack('%sH' % self.order, data[position:position + 2])[0]
                position += 2
                output.append(offset)
            info['indexTable'] = output

        elif type_ == MAPPING_SCAN:
            position = 0
            count = struct.unpack('%sH' % self.order, data[position:position + 2])[0]
            position += 2
            output = {}
            for i in range(count):
                code, offset = struct.unpack('%s2H' % self.order, data[position:position + 4])
                position += 4
                try:  #Python2
                    output[unichr(code)] = offset
                except:  #Python3
                    output[chr(code)] = offset
            info['entries'] = output


def prompt_yes_no(prompt):
    answer_ = None
    while answer_ not in ('y', 'n'):
        if answer_ is not None:
            print('Please answer "y" or "n"')
        try:  #Python2
            answer_ = raw_input(prompt).lower()
        except NameError:  #Python3
            answer_ = input(prompt).lower()

        if len(answer_) == 0:
            answer_ = 'n'

    return answer_


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BFFNT Converter Tool')
    parser.add_argument('-v', '--verbose', help='print more data when working', action='store_true', default=False)
    parser.add_argument('-d', '--debug', help='print debug information', action='store_true', default=False)
    parser.add_argument('-y', '--yes', help='answer yes to any questions (overwriting files)', action='store_true',
                        default=False)
    parser.add_argument('-a', '--ensure-ascii', help='turn off ensure_ascii option when dump json file', action='store_false',
                        default=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-l', '--little-endian', help='Use little endian encoding in the created BFFNT file (default)',
                       action='store_true', default=False)
    group.add_argument('-b', '--big-endian', help='Use big endian encoding in the created BFFNT file',
                       action='store_true', default=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-c', '--create', help='create BFFNT file from extracted files', action='store_true',
                       default=False)
    group.add_argument('-x', '--extract', help='extract BFFNT into PNG/JSON files', action='store_true', default=False)
    parser.add_argument('-f', '--file', metavar='bffnt', help='BFFNT file', required=True)
    args = parser.parse_args()
    if args.extract and not os.path.exists(args.file):
        print('Could not find BFFNT file:')
        print(args.file)
        sys.exit(1)

    basename = os.path.splitext(os.path.basename(args.file))[0]
    json_file = '%s_manifest.json' % basename

    if args.extract and os.path.exists(json_file) and not args.yes:
        print('JSON output file exists.')
        answer = prompt_yes_no('Overwrite? (y/N) ')

        if answer == 'n':
            print('Aborted')
            sys.exit(1)

    sheet_file = '%s_sheet0.png' % basename

    if args.extract and os.path.exists(sheet_file) and not args.yes:
        print('At least one sheet PNG file exists.')
        answer = prompt_yes_no('Overwrite? (y/N) ')

        if answer == 'n':
            print('Aborted')
            sys.exit(1)

    if args.create and os.path.exists(args.file) and not args.yes:
        print('BFFNT output file exists.')
        answer = prompt_yes_no('Overwrite? (y/N) ')

        if answer == 'n':
            print('Aborted')
            sys.exit(1)

    if args.big_endian:
        order = '>'
    else:
        order = '<'
    bffnt = Bffnt(load_order=order, verbose=args.verbose, debug=args.debug)

    if args.extract:
        bffnt.read(args.file)
        if not bffnt.invalid:
            bffnt.extract(args.ensure_ascii)
    elif args.create:
        bffnt.load(json_file)
        if not bffnt.invalid:
            bffnt.save(args.file)
