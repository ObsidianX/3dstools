#!/usr/bin/python

import argparse
import math
import os.path
import struct
import sys

import png

FLIM_HEADER_SIZE = 0x14
IMAG_HEADER_SIZE = 0x14

FLIM_HEADER_MAGIC = "FLIM"
IMAG_HEADER_MAGIC = "imag"

FLIM_HEADER_STRUCT = "=4s2H2IH2B"
IMAG_HEADER_STRUCT = "%s4sI3H2BI"

FORMAT_L8 = 0x00
FORMAT_A8 = 0x01
FORMAT_LA4 = 0x02
FORMAT_LA8 = 0x03
FORMAT_HILO8 = 0x04
FORMAT_RGB565 = 0x05
FORMAT_RGB8 = 0x06
FORMAT_RGBA5551 = 0x07
FORMAT_RGBA4 = 0x08
FORMAT_RGBA8 = 0x09
FORMAT_ETC1 = 0x0A
FORMAT_ETC1A4 = 0x0B
FORMAT_L4 = 0x0C
FORMAT_A4 = 0x0D
FORMAT_ETC1_2 = 0x13

PIXEL_FORMATS = {
    FORMAT_L8: 'L8',
    FORMAT_A8: 'A8',
    FORMAT_LA4: 'LA4',
    FORMAT_LA8: 'LA8',
    FORMAT_HILO8: 'HILO8',
    FORMAT_RGB565: 'RGB565',
    FORMAT_RGB8: 'RGB8',
    FORMAT_RGBA5551: 'RGBA5551',
    FORMAT_RGBA4: 'RGBA4',
    FORMAT_RGBA8: 'RGBA8',
    FORMAT_ETC1: 'ETC1',
    FORMAT_ETC1A4: 'ETC1A4',
    FORMAT_L4: 'L4',
    FORMAT_A4: 'A4',
    FORMAT_ETC1_2: 'ETC1'
}

PIXEL_FORMAT_SIZE = {
    FORMAT_L8: 8,
    FORMAT_A8: 8,
    FORMAT_LA4: 8,
    FORMAT_LA8: 16,
    FORMAT_HILO8: 16,
    FORMAT_RGB565: 16,
    FORMAT_RGB8: 24,
    FORMAT_RGBA5551: 16,
    FORMAT_RGBA4: 16,
    FORMAT_RGBA8: 32,
    FORMAT_ETC1: 4,
    FORMAT_ETC1A4: 8,
    FORMAT_L4: 4,
    FORMAT_A4: 4,
    FORMAT_ETC1_2: 4
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


class Bflim:
    data_size = 0
    invalid = False
    order = None

    def __init__(self, verbose=False, debug=False):
        self.verbose = verbose
        self.debug = debug

    def read(self, filename):
        self.filename = filename

        data = open(filename, 'rb').read()
        self.file_size = len(data)

        position = self.file_size - IMAG_HEADER_SIZE
        position -= FLIM_HEADER_SIZE

        self._parse_flim_header(data[position:position + FLIM_HEADER_SIZE])
        position += FLIM_HEADER_SIZE
        if self.invalid:
            return

        self._parse_imag_header(data[position:position + IMAG_HEADER_SIZE])
        if self.invalid:
            return

        bmp_data = data[:self.data_size]
        if format == FORMAT_ETC1 or format == FORMAT_ETC1_2 or format == FORMAT_ETC1A4:
            self._decompress_etc1(bmp_data)

        self.bmp = self._data_to_bitmap(bmp_data)

    def extract(self):
        width = self.imag['width']
        height = self.imag['height']

        png_data = []
        for y in range(height):
            row = []
            for x in range(width):
                for color in self.bmp[x + (y * width)]:
                    row.append(color)

            png_data.append(row)

        basename = os.path.splitext(os.path.basename(self.filename))[0]
        file = open('%s.png' % basename, 'wb')
        writer = png.Writer(width, height, alpha=True)
        writer.write(file, png_data)
        file.close()

    def _parse_flim_header(self, data):
        magic, bom, header_size, unknown1, file_size, unknown2, multiplier, unknown3 = struct.unpack(FLIM_HEADER_STRUCT,
                                                                                                     data)

        if magic != FLIM_HEADER_MAGIC:
            print('Invalid FLIM magic bytes: %s (expected %s)' % (magic, FLIM_HEADER_MAGIC))
            self.invalid = True
            return

        if bom == 0xFFFE:
            self.order = '>'
        elif bom == 0xFEFF:
            self.order = '<'

        if self.order is None:
            print('Invalid Byte-order marker: 0x%x (expected either 0xFFFE or 0xFEFF)' % bom)
            self.invalid = True
            return

        if header_size != FLIM_HEADER_SIZE:
            print('Invalid/unknown header size: %d (expected %d)' % (header_size, FLIM_HEADER_SIZE))
            self.invalid = True
            return

        if self.file_size != file_size:
            print('Warning: header disagrees with OS file size: OS: %d; Header: %d' % (self.file_size, file_size))

        self.flim = {
            'multiplier': multiplier,
            'unknown1': unknown1,
            'unknown2': unknown2
        }

        if self.debug:
            print('FLIM Magic bytes: %s' % magic)
            print('FLIM Byte-order marker: 0x%x' % bom)
            print('FLIM Header size: %d' % header_size)
            print('FLIM File size: %d' % file_size)
            print('FLIM Multiplier: %d' % multiplier)
            print('\nFLIM Unknown1: 0x%x' % unknown1)
            print('FLIM Unknown2: 0x%x' % unknown2)
            print('FLIM Unknown3: 0x%x\n' % unknown3)

    def _parse_imag_header(self, data):
        magic, parse_size, height, width, alignment, format, swizzle, data_size \
            = struct.unpack(IMAG_HEADER_STRUCT % self.order, data)

        if magic != IMAG_HEADER_MAGIC:
            print('Invalid imag magic bytes: %s (expected %s)' % (magic, IMAG_HEADER_MAGIC))
            self.invalid = True
            return

        self.data_size = data_size

        self.imag = {
            'parse_size': parse_size,
            'width': width,
            'height': height,
            'alignment': alignment,
            'format': format,
            'swizzle': swizzle
        }

        if self.debug:
            print('imag Magic bytes: %s' % magic)
            print('imag Parse info size: %d' % parse_size)
            print('imag Width: %d' % width)
            print('imag Height: %d' % height)
            print('imag Alignment: 0x%x' % alignment)
            print('imag Format: %s' % PIXEL_FORMATS[self.imag['format']])
            print('imag Swizzle: %d' % swizzle)
            print('imag Data size: %d' % data_size)

    def _decompress_etc1(self, data):
        with_alpha = self.imag['format'] == FORMAT_ETC1A4

        chunk_size = 16 if with_alpha else 8
        chunks = len(data) / chunk_size

        for i in range(chunks):
            chunk = data[i * chunk_size:i * chunk_size + chunk_size]

            alpha = 0xFFffFFffFFffFFff
            if with_alpha:
                alpha = struct.unpack('%sQ' % self.order, chunk[:8])[0]

            pixels = chunk[8:]

            differential = (pixels >> ETC_DIFFERENTIAL_BIT) & 0x01 == 1
            orientation = (pixels >> ETC_ORIENTATION_BIT) & 0x01 == 1
            table1 = (pixels >> ETC_TABLE1_OFFSET) & 0x7
            table2 = (pixels >> ETC_TABLE2_OFFSET) & 0x7

            if differential:
                pass
            else:
                # 4 bits per channel, 16 possible values
                red1 = ((data >> ETC_INDIV_RED1_OFFSET) & 0xF) * 0x11
                green1 = ((data >> ETC_INDIV_GREEN1_OFFSET) & 0xF) * 0x11
                blue1 = ((data >> ETC_INDIV_BLUE1_OFFSET) & 0xF) * 0x11
                red2 = ((data >> ETC_RED2_OFFSET) & 0xF) * 0x11
                green2 = ((data >> ETC_GREEN2_OFFSET) & 0xF) * 0x11
                blue2 = ((data >> ETC_BLUE2_OFFSET) & 0xF) * 0x11

    def _data_to_bitmap(self, data, to_bin=False):
        width = self.imag['width']
        height = self.imag['height']
        format = self.imag['format']

        data_width = width
        data_height = height

        # increase the size of the image to a power-of-two boundary, if necessary
        width = 1 << int(math.ceil(math.log(width, 2)))
        height = 1 << int(math.ceil(math.log(height, 2)))

        if to_bin:
            bmp = data
            data = [0] * self.imag[self.data_size]
        else:
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

                                        if to_bin:
                                            # OR the data since there are pixel formats which use the same byte for
                                            # multiple pixels (A4/L4)
                                            bytes = self._get_pixel_data(bmp, format, bmp_pos)
                                            if len(bytes) > 1:
                                                data[data_pos:data_pos + len(bytes)] = bytes
                                            else:
                                                if PIXEL_FORMAT_SIZE[format] == 4:
                                                    data_pos /= 2
                                                data[data_pos] |= bytes[0]
                                        else:
                                            bmp[bmp_pos] = self._get_bmp_pixel_data(data, format, data_pos)

        if to_bin:
            return struct.pack('%dB' % len(data), *data)
        else:
            return bmp

    def _get_bmp_pixel_data(self, data, format, index):
        red = green = blue = alpha = 0

        # rrrrrrrr gggggggg bbbbbbbb aaaaaaaa
        if format == FORMAT_RGBA8:
            color = struct.unpack('%sI' % self.order, data[index * 4:index * 4 + 4])[0]
            red = (color >> 24) & 0xFF
            green = (color >> 16) & 0xFF
            blue = (color >> 8) & 0xFF
            alpha = color & 0xFF

        # rrrrrrrr gggggggg bbbbbbbb
        elif format == FORMAT_RGB8:
            red, green, blue = struct.unpack('3B', data[index * 3:index * 3 + 3])
            alpha = 255

        # rrrrrgg gggbbbbba
        elif format == FORMAT_RGBA5551:
            b1, b2 = struct.unpack('2B', data[index * 2:index * 2 + 2])

            red = ((b1 >> 3) & 0x1F)
            green = (b1 & 0x07) | ((b2 >> 6) & 0x03)
            blue = (b2 >> 1) & 0x1F
            alpha = (b2 & 0x01) * 255

        # rrrrrggg gggbbbbb
        elif format == FORMAT_RGB565:
            b1, b2 = struct.unpack('2B', data[index * 2:index * 2 + 2])

            red = (b1 >> 3) & 0x1F
            green = (b1 & 0x7) | ((b2 >> 5) & 0x7)
            blue = (b2 & 0x1F)
            alpha = 255

        # rrrrgggg bbbbaaaa
        elif format == FORMAT_RGBA4:
            b1, b2 = struct.unpack('2B', data[index * 2:index * 2 + 2])

            red = ((b1 >> 4) & 0x0F) * 0x11
            green = (b1 & 0x0F) * 0x11
            blue = ((b2 >> 4) & 0x0F) * 0x11
            alpha = (b2 & 0x0F) * 0x11

        # llllllll aaaaaaaa
        elif format == FORMAT_LA8:
            l, alpha = struct.unpack('2B', data[index * 2:index * 2 + 2])
            red = green = blue = l

        # ??
        elif format == FORMAT_HILO8:
            # TODO
            pass

        # llllllll
        elif format == FORMAT_L8:
            red = green = blue = struct.unpack('B', data[index:index + 1])[0]
            alpha = 255

        # aaaaaaaa
        elif format == FORMAT_A8:
            alpha = struct.unpack('B', data[index:index + 1])[0]
            red = green = blue = 255

        # llllaaaa
        elif format == FORMAT_LA4:
            la = struct.unpack('B', data[index:index + 1])[0]
            red = green = blue = ((la >> 4) & 0x0F) * 0x11
            alpha = (la & 0x0F) * 0x11

        # llll
        elif format == FORMAT_L4:
            l = struct.unpack('B', data[index / 2])[0]
            shift = (index & 1) * 4
            red = green = blue = ((l >> shift) & 0x0F) * 0x11
            alpha = 255

        # aaaa
        elif format == FORMAT_A4:
            byte = ord(data[index / 2])
            shift = (index & 1) * 4
            alpha = ((byte >> shift) & 0x0F) * 0x11
            green = red = blue = 0xFF

        # compressed
        elif format == FORMAT_ETC1:
            # TODO
            pass

        # compress w/alpha
        elif format == FORMAT_ETC1A4:
            # TODO
            pass

        return (red, green, blue, alpha)

    def _get_pixel_data(self, bmp, format, index):
        # bmp data: tuple (r, g, b, a)
        # output: list of bytes: [255, 255]
        red, green, blue, alpha = bmp[index]

        if format == FORMAT_RGBA8:
            color = alpha
            color |= red << 24
            green |= green << 16
            blue |= blue << 8
            return struct.pack('%sI' % self.order, color)

        elif format == FORMAT_RGB8:
            return [red, green, blue]

        # rrrrrggg ggbbbbba
        elif format == FORMAT_RGBA5551:
            r5 = (red / 8) & 0x1F
            g5 = (green / 8) & 0x1F
            b5 = (blue / 8) & 0x1F
            a = 1 if alpha > 0 else 0

            b1 = (r5 << 3) | (g5 >> 2)
            b2 = ((g5 << 6) | (b5 << 1) | a) & 0xFF
            return [b1, b2]

        # rrrrrggg gggbbbbb
        elif format == FORMAT_RGB565:
            r5 = (red / 8) & 0x1F
            g6 = (green / 4) & 0x3F
            b5 = (blue / 8) & 0x1F

            b1 = (r5 << 3) | (g6 >> 3)
            b2 = ((g6 << 5) | b5) & 0xFF
            return [b1, b2]

        # rrrrgggg bbbbaaaa
        elif format == FORMAT_RGBA4:
            r4 = (red / 0x11) & 0x0F
            g4 = (green / 0x11) & 0x0F
            b4 = (blue / 0x11) & 0x0F
            a4 = (alpha / 0x11) & 0x0F

            b1 = (r4 << 4) | g4
            b2 = (b4 << 4) | a4
            return [b1, b2]

        # llllllll aaaaaaaa
        elif format == FORMAT_LA8:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))

            return [l, alpha]

        elif format == FORMAT_HILO8:
            # TODO
            pass

        # llllllll
        elif format == FORMAT_L8:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))

            return [l]

        # aaaaaaaa
        elif format == FORMAT_A8:
            return [alpha]

        # llllaaaa
        elif format == FORMAT_LA4:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722)) / 0x11
            a = (alpha / 0x11) & 0x0F

            b = (l << 4) | a
            return [b]

        # llll
        elif format == FORMAT_L4:
            l = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))
            shift = (index & 1) * 4
            return [l << shift]

        # aaaa
        elif format == FORMAT_A4:
            alpha = (bmp[index][3] / 0x11) & 0xF
            shift = (index & 1) * 4
            return [alpha << shift]

        elif format == FORMAT_ETC1:
            # TODO
            pass

        elif format == FORMAT_ETC1A4:
            # TODO
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BFLIM Converter')
    parser.add_argument('-v', '--verbose', help='print more data when working', action='store_true', default=False)
    parser.add_argument('-d', '--debug', help='print debug information', action='store_true', default=False)
    parser.add_argument('-y', '--yes', help='answer yes to any questions (overwriting files)', action='store_true',
                        default=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-c', '--create', help='create BFFNT file from extracted files', action='store_true',
                       default=False)
    group.add_argument('-x', '--extract', help='extract BFFNT into PNG/JSON files', action='store_true', default=False)
    parser.add_argument('bflim_file', help='FLIM file')
    args = parser.parse_args()

    bflim = Bflim(verbose=args.verbose, debug=args.debug)

    if args.extract:
        bflim.read(args.bflim_file)
        if bflim.invalid:
            sys.exit(1)
        bflim.extract()
