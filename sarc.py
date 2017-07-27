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

SARC_MAGIC = b'SARC'
SFAT_MAGIC = b'SFAT'
SFNT_MAGIC = b'SFNT'

SARC_HEADER_STRUCT = '%s4s2H3I'
SFAT_HEADER_STRUCT = '%s4s2HI'
SFAT_NODE_STRUCT = '%s4I'
SFNT_HEADER_STRUCT = '%s4s2H'

READ_AMOUNT = 1024
DECOMP_AMOUNT = 512
FILE_READ_SIZE = 1024

SARC_HEADER_UNKNOWN = 0x100
SFAT_HASH_MULTIPLIER = 0x65

STATE_SARC_HEADER = 0
STATE_SFAT_HEADER = 1
STATE_SFAT_DATA = 2
STATE_SFNT_HEADER = 3
STATE_SFNT_DATA = 4
STATE_FILE_DATA = 5

DEFAULT_COMPRESSION_LEVEL = 6


class Sarc:
    invalid = False
    file_nodes = []
    fnt_data_length = 0
    extracting = False
    files = []
    file_position = 0

    def __init__(self, filename, compressed=False, verbose=False, extract=False, debug=False, little_endian=True,
                 list=False, compression_level=DEFAULT_COMPRESSION_LEVEL):
        self.file = open(filename, 'rb' if (extract or list) else 'wb')
        self.filename = filename
        self.outdir = os.path.splitext(filename)[0] + '_'  #if no names
        self.compressed = compressed
        self.verbose = verbose
        self.extract = extract
        self.debug = debug
        self.compression_level = compression_level

        if not extract and not list:
            if little_endian:
                self.order = '<'
            else:
                self.order = '>'
            self.file_name_hash_mult = SFAT_HASH_MULTIPLIER

        if os.path.exists(filename) and (extract or list):
            if compressed:
                self.file_size = struct.unpack('>I', self.file.read(4))[0]
            else:
                self.file_size = os.stat(filename).st_size

    def add(self, path):
        if os.path.isdir(path):
            for path, dirs, files in os.walk(path):
                self._add_path(path, dirs, files)
        else:
            self.files.append(path)

        self.files.sort(key=self._file_sort)
    
    def _file_sort(self, name):
        if name.endswith('.noname.bin'):
            hash_ = int(os.path.split(name)[-1].split('.')[0].lstrip('0x'), 16)
        else:
            hash_ = self._calc_filename_hash(name)
        return hash_

    def _add_path(self, path, dirs, files):
        for file_ in files:
            self.files.append(os.path.join(path, file_))

    def _write(self, data, count=True):
        self.file.write(data)
        if count:
            self.file_position += len(data)

    def save(self):
        bom = 0xFEFF  #because 0xfeff if packed in big endian and 0xfffe in little endian. better to keep the byteorder with the header struct

        header = struct.pack(SARC_HEADER_STRUCT % self.order, SARC_MAGIC, SARC_HEADER_LEN, bom, 0, 0, SARC_HEADER_UNKNOWN)

        self.file_position = 0
        self._write(header)

        fat_bytes = b''
        fnt_bytes = b''

        for filename in self.files:
            if filename.endswith('.noname.bin'):
                hash_ = int(os.path.split(filename)[-1].split('.')[0].lstrip('0x'), 16)
                offset = 0x00000000
                filename = '\x00'*16
            else:
                hash_ = self._calc_filename_hash(filename)
                offset = 0x01000000 | len(fnt_bytes) / 4

            fat_bytes += struct.pack(SFAT_NODE_STRUCT % self.order, hash_, offset, 0, 0)
            fnt_bytes += struct.pack('%s%dsB' % (self.order, len(filename)), filename.encode('ascii'), 0)

            padding = 4 - (len(fnt_bytes) % 4)
            if padding < 4:
                fnt_bytes += b'\x00' * padding

        fat_header = struct.pack(SFAT_HEADER_STRUCT % self.order, SFAT_MAGIC, SFAT_HEADER_LEN, len(self.files),
                                 SFAT_HASH_MULTIPLIER)
        fnt_header = struct.pack(SFNT_HEADER_STRUCT % self.order, SFNT_MAGIC, SFNT_HEADER_LEN, 0)

        self._write(fat_header)
        fat_header_start = self.file_position
        self._write(fat_bytes)

        self._write(fnt_header)
        self._write(fnt_bytes)

        data_start = self.file_position
        padding = 0x100 - (data_start % 0x100)
        if padding < 0x100:
            data_start += padding
            self._write(b'\x00' * padding)

        self.file.seek(0x0c)
        self._write(struct.pack('%sI' % self.order, data_start), False)
        self.file.seek(data_start)

        for i in range(len(self.files)):
            filename = self.files[i]

            position = self.file_position
            padding = 0x80 - (position % 0x80)
            if padding < 0x80:
                self._write(b'\x00' * padding)
                position += padding

            if self.verbose:
                print(filename)

            # adjust file start position
            file_start = position - data_start
            file_end = file_start + os.stat(filename).st_size
            self.file.seek(fat_header_start + (SFAT_NODE_LEN * i) + 0x08)
            self._write(struct.pack('%s2I' % self.order, file_start, file_end), False)
            self.file.seek(position)

            file = open(filename, 'rb')
            data = file.read(FILE_READ_SIZE)
            while len(data) > 0:
                self._write(data)
                data = file.read(FILE_READ_SIZE)

        size = self.file_position
        self.file.seek(0x08)
        self._write(struct.pack('%sI' % self.order, size), False)

        self.file.close()

        if self.compressed:
            self.compress_file()

    def compress_file(self):
        # stream-compress to another file then overwrite original
        self.file = open(self.filename, 'rb')
        compressed_filename = '%s.zlib' % self.filename
        compressed_file = open(compressed_filename, 'wb')
        compressor = zlib.compressobj(self.compression_level)

        compressed_file.write(struct.pack('>I', os.stat(self.filename).st_size))

        data = self.file.read(READ_AMOUNT)
        while len(data) > 0:
            compressed_file.write(compressor.compress(data))
            data = self.file.read(READ_AMOUNT)

        compressed_file.write(compressor.flush(zlib.Z_FINISH))

        self.file.close()
        compressed_file.close()

        os.rename(compressed_filename, self.filename)

    def read(self):
        if self.compressed:
            z = zlib.decompressobj()
        state = STATE_SARC_HEADER

        partial_data = b''
        eof = False
        get_more = True
        node_section_length = 0
        position = 0
        partial_start = 0
        file_idx = 0
        remaining = 0
        output = None
        try:
            os.mkdir(self.outdir)
        except:
            pass

        while not eof or len(partial_data) > 0 or self.extracting:
            if get_more:
                read_data = self.file.read(READ_AMOUNT)
                eof = len(read_data) == 0

                if self.compressed:
                    read_data = z.decompress(z.unconsumed_tail + read_data, DECOMP_AMOUNT)

                position += len(read_data)
                partial_data += read_data
                get_more = False

            if state == STATE_SARC_HEADER:
                if len(partial_data) >= SARC_HEADER_LEN:
                    self._parse_header(partial_data[:SARC_HEADER_LEN])
                    if self.invalid:
                        return
                    partial_data = partial_data[SARC_HEADER_LEN:]
                    partial_start += SARC_HEADER_LEN
                    state = STATE_SFAT_HEADER
                else:
                    get_more = True
            elif state == STATE_SFAT_HEADER:
                if len(partial_data) >= SFAT_HEADER_LEN:
                    self._parse_fat_header(partial_data[:SFAT_HEADER_LEN])
                    if self.invalid:
                        return
                    partial_data = partial_data[SFAT_HEADER_LEN:]
                    partial_start += SFAT_HEADER_LEN
                    state = STATE_SFAT_DATA
                    node_section_length = SFAT_NODE_LEN * self.file_count
                    self.fnt_data_length = self.file_data_offset - SARC_HEADER_LEN - SFAT_HEADER_LEN - SFNT_HEADER_LEN - node_section_length
                else:
                    get_more = True
            elif state == STATE_SFAT_DATA:
                if len(partial_data) >= node_section_length:
                    self._parse_fat_nodes(partial_data[:node_section_length])
                    if self.invalid:
                        return
                    partial_data = partial_data[node_section_length:]
                    partial_start += node_section_length
                    state = STATE_SFNT_HEADER
                else:
                    get_more = True
            elif state == STATE_SFNT_HEADER:
                if len(partial_data) >= SFNT_HEADER_LEN:
                    self._parse_fnt_header(partial_data[:SFNT_HEADER_LEN])
                    if self.invalid:
                        return
                    partial_data = partial_data[SFNT_HEADER_LEN:]
                    partial_start += SFNT_HEADER_LEN
                    state = STATE_SFNT_DATA
                else:
                    get_more = True
            elif state == STATE_SFNT_DATA:
                if len(partial_data) >= self.fnt_data_length:
                    self._parse_fnt_data(partial_data[:self.fnt_data_length])
                    if self.invalid:
                        return
                    partial_data = partial_data[self.fnt_data_length:]
                    partial_start += self.fnt_data_length
                    state = STATE_FILE_DATA
                else:
                    get_more = True
            elif state == STATE_FILE_DATA:
                if not self.extract:
                    break

                self.extracting = True

                if remaining == 0:
                    remaining = self.file_nodes[file_idx]['length']
                    filename = self.file_nodes[file_idx]['filename']

                    if self.verbose:
                        print(filename)
                    if not self.file_nodes[file_idx]['has_name']:
                        filename = os.path.join(self.outdir, filename)
                    dirname = os.path.dirname(filename)
                    if len(dirname) > 0 and not os.path.exists(dirname):
                        try:
                            os.makedirs(dirname)
                        except OSError:
                            print("Couldn't create directory: %s" % dirname)
                            return
                    output = open(filename, 'wb')

                if remaining == self.file_nodes[file_idx]['length']:
                    start = self.file_nodes[file_idx]['start'] + self.file_data_offset
                    if position > start and partial_start <= start:
                        data_start = start - partial_start
                        partial_data = partial_data[data_start:]
                        partial_start += data_start
                    elif partial_start > start:
                        print("Couldn't extract file data.")
                        return
                    else:
                        get_more = True
                        continue

                partial_len = len(partial_data)
                if partial_len < remaining:
                    output.write(partial_data)
                    remaining -= partial_len
                    partial_data = b''
                    partial_start = position
                    get_more = True
                else:
                    output.write(partial_data[:remaining])
                    output.close()
                    partial_data = partial_data[remaining:]
                    partial_start += remaining
                    remaining = 0
                    file_idx += 1
                    if file_idx >= self.file_count:
                        break

        if not self.extract:
            self._list_files()

    def _parse_header(self, data):
        bom = data[6:8]
        try:  #python3
            int_bom = int.from_bytes(bom, 'big')  #for error messages
        except:
            int_bom = (ord(bom[0]) << 8) + ord(bom[1])
        
        if bom not in [b'\xff\xfe', b'\xfe\xff']:
            print('Invalid byte-order marker: 0x%x (expected either 0xFFFE or 0xFEFF)' % int_bom)
            self.invalid = True
            return
        
        self.order = '<' if (bom == b'\xff\xfe') else '>'
        magic, header_len, bom, file_len, data_offset, unknown = struct.unpack(SARC_HEADER_STRUCT % self.order, data)

        if magic != SARC_MAGIC:
            print('Invalid SARC magic bytes: %s (expected "%s")' % (magic, SARC_MAGIC))
            self.invalid = True
            return

        if header_len != SARC_HEADER_LEN:
            print('Invalid SARC header length: %d (expected %d)' % (header_len, SARC_HEADER_LEN))
            self.invalid = True
            return

        if self.order is None:
            print('Invalid byte-order marker: 0x%x (expected either 0xFFFE or 0xFEFF)' % int_bom)
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

        self.file_data_offset = data_offset

        if self.debug:
            print('SARC Magic: %s' % magic)
            print('SARC Header length: %d' % header_len)
            print('SARC Byte order: %s' % self.order)
            print('SARC File size: %d' % file_len)
            print('SARC Data offset: %d' % data_offset)

            print('\nSARC Unknown: 0x%x\n' % unknown)

    def _parse_fat_header(self, data):
        magic, header_len, node_count, hash_multiplier = struct.unpack(SFAT_HEADER_STRUCT % self.order, data)

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

        if self.debug:
            print('SFAT Magic: %s' % magic)
            print('SFAT Header length: %d' % header_len)
            print('SFAT File count: %d' % node_count)
            print('SFAT Hash multiplier: 0x%x\n' % hash_multiplier)

    def _parse_fat_nodes(self, data):
        idx = 0
        for i in range(self.file_count):
            node_data = data[idx:idx + SFAT_NODE_LEN]
            idx += SFAT_NODE_LEN

            hash, name_offset, data_start, data_end = struct.unpack(SFAT_NODE_STRUCT % self.order, node_data)
            # first byte is to determine if the file name is stored in SFNT
            has_name = name_offset >> 24
            # trim off first byte
            name_offset &= 0xFFFFFF
            name_offset *= 4

            self.file_nodes.append({
                'hash': hash,
                'has_name': has_name,
                'name_offset': name_offset,
                'start': data_start,
                'end': data_end,
                'length': (data_end - data_start)
            })

    def _parse_fnt_header(self, data):
        magic, header_length, unknown = struct.unpack(SFNT_HEADER_STRUCT % self.order, data)

        if magic != SFNT_MAGIC:
            print('Invalid SFNT magic bytes: %s (expected "%s")' % (magic, SFNT_MAGIC))
            self.invalid = True
            return

        if header_length != SFNT_HEADER_LEN:
            print('Invalid SFNT header length: %d (expected %d)' % (header_length, SFNT_HEADER_LEN))
            self.invalid = True
            return

        if self.debug:
            print('SFNT Magic: %s' % magic)
            print('SFNT Header length: %d' % header_length)

            print('\nSFNT Unknown: 0x%x\n' % unknown)

    def _parse_fnt_data(self, data):
        for node in self.file_nodes:
            if node['has_name']:
                start = node['name_offset']
                end = data.find(b'\0', start)
                node['filename'] = data[start:end]

                if self.debug:
                    print('File name: %s' % node['filename'])
                    print('File name hash: 0x%x' % node['hash'])
                    print('File data start: %d' % node['start'])
                    print('File length: %d\n' % node['length'])

                hash = self._calc_filename_hash(node['filename'])
                if node['hash'] != hash:
                    print('Invalid filename: %s' % node['filename'])
                    print('Hash: 0x%x (expected 0x%x)' % (hash, node['hash']))
                    self.invalid = True
                    return
            else:
                node['filename'] = '0x%08x.noname.bin' % node['hash']

    def _calc_filename_hash(self, name):
        result = 0
        for c in name:
            result = ord(c) + (result * self.file_name_hash_mult)
            result &= 0xFFFFFFFF
        return result

    def _list_files(self):
        for node in self.file_nodes:
            print(node['filename'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SARC Archive Tool')
    parser.add_argument('-v', '--verbose', help='print more data when working', action='store_true', default=False)
    parser.add_argument('-d', '--debug', help='print debug information', action='store_true', default=False)
    parser.add_argument('-y', '--yes', help='answer "yes" to questions (overwriting files)', action='store_true',
                        default=False)
    parser.add_argument('-z', '--zlib', help='use ZLIB to compress or decompress the archive', action='store_true',
                        default=False)
    parser.add_argument('--compression-level', metavar='LEVEL', help='ZLIB compression level (default: 6)', type=int,
                        default=DEFAULT_COMPRESSION_LEVEL)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-x', '--extract', help='extract the SARC', action='store_true', default=False)
    group.add_argument('-c', '--create', help='create a SARC', action='store_true', default=False)
    group.add_argument('-t', '--list', help='list contents', action='store_true', default=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-l', '--little-endian', help='use little endian encoding when creating an archive (default)',
                       action='store_true', default=True)
    group.add_argument('-b', '--big-endian', help='use big endian encoding when creating an archive',
                       action='store_true', default=False)
    parser.add_argument('-f', '--archive', metavar='archive', help='the SARC filename', default=None, required=True)
    parser.add_argument('file', help='files to add to an archive', nargs='*')
    args = parser.parse_args()
    
    if args.big_endian:  #issue with argparse...
        args.little_endian = False

    archive_exists = os.path.exists(args.archive)

    if archive_exists and args.create and not args.yes:
        print('File exists: %s' % args.archive)
        answer = None
        while answer not in ('y', 'n'):
            if answer is not None:
                print('Please answer "y" or "n"')
            try:  #python2
                answer = raw_input('Overwrite existing file? (y/N) ').lower()
            except:
                answer = input('Overwrite existing file? (y/N) ').lower()

            if len(answer) == 0:
                answer = 'n'

        if answer == 'n':
            print('Aborted.')
            sys.exit(1)

    if not archive_exists and (args.extract or args.list):
        print('File not found!')
        print(args.archive)
        sys.exit(1)

    sarc = Sarc(args.archive, compressed=args.zlib, verbose=args.verbose, debug=args.debug, extract=args.extract,
                list=args.list, little_endian=args.little_endian, compression_level=args.compression_level)

    if args.extract or args.list:
        sarc.read()
        if sarc.invalid:
            print('SARC archive is invalid')

    elif args.create:
        for path in args.file:
            sarc.add(path)
        sarc.save()
