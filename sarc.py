#!/usr/bin/python
import argparse
import os
import os.path
import struct
import sys

import zlib

SARC_HEADER_LEN = 0x14
SFAT_HEADER_LEN = 0x0c
SFNT_HEADER_LEN = 0x08
SFAT_NODE_LEN = 0x10

SARC_MAGIC = 'SARC'
SFAT_MAGIC = 'SFAT'
SFNT_MAGIC = 'SFNT'

READ_AMOUNT = 1024
DECOMP_AMOUNT = 512

STATE_SARC_HEADER = 0
STATE_SFAT_HEADER = 1
STATE_SFAT_DATA = 2
STATE_SFNT_HEADER = 3
STATE_SFNT_DATA = 4
STATE_FILE_DATA = 5


class Sarc:
    invalid = False
    file_nodes = []
    fnt_data_length = 0

    def __init__(self, filename, compressed=False, verbose=False, extract=False):
        self.file = open(filename, 'rw')
        self.compressed = compressed
        self.verbose = verbose
        self.extract = extract

        if os.path.exists(filename):
            if compressed:
                self.file_size = struct.unpack('>I', self.file.read(4))[0]
            else:
                self.file_size = os.stat(filename).st_size

    def save(self):
        pass

    def read(self):
        if self.compressed:
            z = zlib.decompressobj()
        state = STATE_SARC_HEADER

        partial_data = ''
        eof = False
        get_more = True

        while not eof or len(partial_data) > 0:
            if get_more:
                read_data = self.file.read(READ_AMOUNT)
                eof = len(read_data) == 0

                if self.compressed:
                    partial_data += z.decompress(z.unconsumed_tail + read_data, DECOMP_AMOUNT)
                else:
                    partial_data += read_data
                get_more = False

            if state == STATE_SARC_HEADER:
                if len(partial_data) >= SARC_HEADER_LEN:
                    self._parse_header(partial_data[:SARC_HEADER_LEN])
                    if self.invalid:
                        return
                    partial_data = partial_data[SARC_HEADER_LEN:]
                    state = STATE_SFAT_HEADER
                else:
                    get_more = True
            elif state == STATE_SFAT_HEADER:
                if len(partial_data) >= SFAT_HEADER_LEN:
                    self._parse_fat_header(partial_data[:SFAT_HEADER_LEN])
                    if self.invalid:
                        return
                    partial_data = partial_data[SFAT_HEADER_LEN:]
                    state = STATE_SFAT_DATA
                else:
                    get_more = True
            elif state == STATE_SFAT_DATA:
                node_section_length = SFAT_NODE_LEN * self.file_count
                if len(partial_data) >= node_section_length:
                    self._parse_fat_nodes(partial_data[:node_section_length])
                    if self.invalid:
                        return
                    partial_data = partial_data[node_section_length:]
                    state = STATE_SFNT_HEADER
                else:
                    get_more = True
            elif state == STATE_SFNT_HEADER:
                if len(partial_data) >= SFNT_HEADER_LEN:
                    self._parse_fnt_header(partial_data[:SFNT_HEADER_LEN])
                    if self.invalid:
                        return
                    partial_data = partial_data[SFNT_HEADER_LEN:]
                    state = STATE_SFNT_DATA
                else:
                    get_more = True
            elif state == STATE_SFNT_DATA:
                if len(partial_data) >= self.fnt_data_length:
                    self._parse_fnt_data(partial_data[:self.fnt_data_length])
                    if self.invalid:
                        return
                    partial_data = partial_data[self.fnt_data_length:]
                    state = STATE_FILE_DATA
            elif state == STATE_FILE_DATA:
                if not self.extract:
                    return

        if not self.extract:
            for node in self.file_nodes:
                print(node['filename'])

    def _parse_header(self, data):
        magic, header_len, bom, file_len, data_offset, unknown = struct.unpack('=4s2H3I', data)

        self.order = None

        if bom == 0xFFFE:
            self.order = '>'
        elif bom == 0xFEFF:
            self.order = '<'

        if magic != SARC_MAGIC:
            print('Invalid SARC magic bytes: %s (expected "%s")' % (magic, SARC_MAGIC))
            self.invalid = True
            return

        if header_len != SARC_HEADER_LEN:
            print('Invalid SARC header length: %d (expected %d)' % (header_len, SARC_HEADER_LEN))
            self.invalid = True
            return

        if self.order is None:
            print('Invalid byte-order marker: 0x%x (expected either 0xFFFE or 0xFEFF)' % bom)
            self.invalid = True
            return

        if file_len != self.file_size:
            print('Invalid file size: %d (expected %d)' % (file_len, self.file_size))
            self.invalid = True
            return

        if data_offset > file_len or data_offset < SARC_HEADER_LEN + SFAT_HEADER_LEN + SFNT_HEADER_LEN:
            print('Invalid data offset: %d (outside of file)' % data_offset)
            self.invalid = True
            return

        if self.verbose:
            print('SARC Magic: %s' % magic)
            print('SARC Header length: %d' % header_len)
            print('SARC Byte order: %s' % self.order)
            print('SARC File size: %d' % file_len)
            print('SARC Data offset: %d' % data_offset)

            print('\nSARC Unknown: 0x%x\n' % unknown)

    def _parse_fat_header(self, data):
        magic, header_len, node_count, hash_multiplier = struct.unpack('%s4s2HI' % self.order, data)

        if magic != SFAT_MAGIC:
            print('Invalid SFAT magic bytes: %s (expected "%s")' % (magic, SFAT_MAGIC))
            self.invalid = True
            return

        if header_len != SFAT_HEADER_LEN:
            print('Invalid SFAT header length: %d (expected %d)' % (header_len, SFAT_HEADER_LEN))
            self.invalid = True
            return

        self.file_count = node_count
        self.file_name_hash_mult = hash_multiplier

        if self.verbose:
            print('SFAT Magic: %s' % magic)
            print('SFAT Header length: %d' % header_len)
            print('SFAT Node count: %d' % node_count)
            print('SFAT Hash multiplier: 0x%x\n' % hash_multiplier)

    def _parse_fat_nodes(self, data):
        idx = 0
        for i in range(self.file_count):
            node_data = data[idx:idx + SFAT_NODE_LEN]
            idx += SFAT_NODE_LEN

            hash, name_offset, data_start, data_end = struct.unpack('%s4I' % self.order, node_data)
            # trim off first byte
            name_offset &= 0xFFFFFF
            name_offset *= 4

            self.file_nodes.append({
                'hash': hash,
                'name_offset': name_offset,
                'start': data_start,
                'end': data_end
            })

            self.fnt_data_length += name_offset + 1

    def _parse_fnt_header(self, data):
        magic, header_length, unknown = struct.unpack('%s4s2H' % self.order, data)

        if magic != SFNT_MAGIC:
            print('Invalid SFNT magic bytes: %s (expected "%s")' % (magic, SFNT_MAGIC))
            self.invalid = True
            return

        if header_length != SFNT_HEADER_LEN:
            print('Invalid SFNT header length: %d (expected %d)' % (header_length, SFNT_HEADER_LEN))
            self.invalid = True
            return

        if self.verbose:
            print('SFNT Magic: %s' % magic)
            print('SFNT Header length: %d' % header_length)

            print('\nSFNT Unknown: 0x%x\n' % unknown)

    def _parse_fnt_data(self, data):
        print data.encode('hex')
        for node in self.file_nodes:
            start = node['name_offset']
            end = data.find('\0', start)
            node['filename'] = data[start:end]
            print('Name offset: %d' % node['name_offset'])
            print('End: %d' % end)

            hash = self._calc_filename_hash(node['filename'])
            if node['hash'] != hash:
                print('Invalid filename: %s' % node['filename'])
                print('Hash: 0x%x (expected 0x%x)' % (hash, node['hash']))
                self.invalid = True
                return

            if self.verbose:
                print('Node filename: %s' % node['filename'])
                print('Node filename hash: 0x%x' % node['hash'])
                print('Node data start: %d' % node['start'])
                print('Node length: %d\n' % (node['end'] - node['start']))

    def _calc_filename_hash(self, name):
        result = 0
        for c in name:
            result = ord(c) + (result * self.file_name_hash_mult)
            result &= 0xFFFFFFFF
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SARC Archive Tool')
    parser.add_argument('-v', '--verbose', help='print more data when working', action='store_true', default=False)
    parser.add_argument('-z', '--zlib', help='use ZLIB to compress or decompress the archive', action='store_true',
                        default=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-x', '--extract', help='extract the SARC', action='store_true', default=False)
    group.add_argument('-c', '--create', help='create a SARC', action='store_true', default=False)
    group.add_argument('-t', '--list', help='list contents', action='store_true', default=False)
    parser.add_argument('-f', '--archive', metavar='archive', help='the SARC filename', default=None, required=True)
    parser.add_argument('file', help='files to add to an archive', nargs='*')
    args = parser.parse_args()

    archive_exists = os.path.exists(args.archive)

    if archive_exists and args.create:
        print('File exists: %s' % args.archive)
        answer = None
        while answer not in ('y', 'n'):
            if answer is not None:
                print('Please answer "y" or "n"')
            answer = raw_input('Overwrite existing file? (y/N) ').lower()

            if len(answer) == 0:
                answer = 'n'

        if answer == 'n':
            print('Aborted.')
            sys.exit(1)

    if not archive_exists and (args.extract or args.list):
        print('File not found!')
        print(args.archive)
        sys.exit(1)

    sarc = Sarc(args.archive, compressed=args.zlib, verbose=args.verbose)

    if args.extract or args.list:
        sarc.read()

    if sarc.invalid:
        print('SARC archive is invalid')
