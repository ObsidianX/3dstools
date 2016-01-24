#!/usr/bin/python
import json
import os.path
import struct
import sys

HEADER_LEN = 0x20
NLI1_HEADER_LEN = 0x14
TXT2_HEADER_LEN = 0x14
LBL1_HEADER_LEN = 0x14
ATR1_HEADER_LEN = 0x14

HEADER_MAGIC = 'MsgStdBn'
NLI1_MAGIC = 'NLI1'
TXT2_MAGIC = 'TXT2'
LBL1_MAGIC = 'LBL1'
ATR1_MAGIC = 'ATR1'
SECTION_END_MAGIC = '\xAB\xAB\xAB\xAB'
SECTION_END_MAGIC_SINGLE = '\xAB'


class Msbt:
    order = None
    sections = 0
    lbl1 = None
    nli1 = None
    txt2 = None
    atr1 = None

    def __init__(self, file_data, verbose=False):
        self.verbose = verbose
        self.file_size = len(file_data)
        self.file_data = file_data

        self.parse_header(file_data[:HEADER_LEN])

        file_index = HEADER_LEN

        while file_index < self.file_size:
            # advance 4 bytes to read the section header magic bytes
            section = file_data[file_index:file_index + 4]
            section_end = file_data.find(SECTION_END_MAGIC, file_index)
            section_data = file_data[file_index:section_end]

            if section == NLI1_MAGIC:
                header = self.parse_nli1_header(section_data[:NLI1_HEADER_LEN])
                if header is not None:
                    self.nli1 = {
                        'header': header
                    }
                    self.parse_nli1(section_data[NLI1_HEADER_LEN:])
            elif section == TXT2_MAGIC:
                header = self.parse_txt2_header(section_data[:TXT2_HEADER_LEN])
                if header is not None:
                    self.txt2 = {
                        'header': header
                    }
                    self.parse_txt2(section_data[TXT2_HEADER_LEN:])
            elif section == LBL1_MAGIC:
                header = self.parse_lbl1_header(section_data[:LBL1_HEADER_LEN])
                if header is not None:
                    self.lbl1 = {
                        'header': header
                    }
                    self.parse_lbl1(section_data[LBL1_HEADER_LEN:])
            elif section == ATR1_MAGIC:
                header = self.parse_atr1_header(section_data[:ATR1_HEADER_LEN])
                if header is not None:
                    self.atr1 = {
                        'header': header
                    }
                    # parse ATR1

            file_index = self.find_next_section(section_end)

    def find_next_section(self, start):
        if start >= 0:
            for i in range(start, self.file_size):
                if self.file_data[i] != SECTION_END_MAGIC_SINGLE:
                    return i

        return self.file_size

    def parse_header(self, data):
        magic, bom, unknown1, unknown2, sections, unknown3, file_size, unknown4 = struct.unpack('=8s5HI10s', data)

        if magic != HEADER_MAGIC:
            print('Invalid section magic bytes: %s (expected %s)' % (magic, HEADER_MAGIC))
            sys.exit(1)

        if file_size != self.file_size:
            print('File size mismatch. Header says: %d, OS says: %d' % (file_size, self.file_size))

        if bom == 0xFFFE:
            self.order = '>'
        elif bom == 0xFEFF:
            self.order = '<'
        else:
            print('Invalid byte order marker: 0x%x' % bom)
            sys.exit(1)

        self.sections = sections

        if self.verbose:
            print("""
Header Magic: %s
Byte order: %s
File Size: %d
Sections: %d

Unknown1: 0x%x
Unknown2: 0x%x
Unknown3: 0x%x
Unknown4: 0x%s
""" % (magic, self.order, file_size, sections, unknown1, unknown2, unknown3, unknown4.encode('hex')))

    def parse_lbl1_header(self, data):
        try:
            magic, size, unknown, entries = struct.unpack('%s4sI8sI' % self.order, data)
        except Exception:
            return None

        if self.verbose:
            print("""
LBL1 Header Magic: %s
LBL1 Size: %d
LBL1 Entries: %d

LBL1 Unknown1: %s
""" % (magic, size, entries, unknown.encode('hex')))

        return {
            'size': size,
            'entries': entries
        }

    def parse_lbl1(self, data):
        data_index = 0
        lists = []

        for i in range(self.lbl1['header']['entries']):
            count, offset = struct.unpack('%s2I' % self.order, data[data_index:data_index + 8])
            if count > 0:
                lists.append((count, offset))
            data_index += 8

        # all offsets are forward by 4 bytes for some reason...
        strings_start = -4

        strings = []
        for list_ in lists:
            count = list_[0]
            offset = list_[1]

            str_list = []

            idx = strings_start + offset
            for i in range(count):
                length = ord(data[idx])
                idx += 1
                string, index = struct.unpack('%s%dsI' % (self.order, length), data[idx:idx + length + 4])
                idx += length + 4
                str_list.append({
                    'index': index,
                    'string': string
                })

            strings.append(str_list)

        self.lbl1['data'] = strings

    def parse_atr1_header(self, data):
        try:
            magic, size, unknown1, unknown2, entries = struct.unpack('%s4s4I' % self.order, data)
        except Exception:
            return None

        if self.verbose:
            print("""
ATR1 Magic: %s
ATR1 Size: %d
ATR1 Entries: %d

ATR1 Unknown1: 0x%x
ATR2 Unknown2: 0x%x
""" % (magic, size, entries, unknown1, unknown2))

        return {
            'size': size,
            'entries': entries
        }

    def parse_txt2_header(self, data):
        try:
            magic, size, unknown1, unknown2, entries = struct.unpack('%s4s4I' % self.order, data)
        except Exception:
            return None

        if self.verbose:
            print("""
TXT2 Magic: %s
TXT2 Size: %d
TXT2 Entries: %d

TXT2 Unknown1: 0x%x
TXT2 Unknown2: 0x%x
""" % (magic, size, entries, unknown1, unknown2))

        return {
            'size': size,
            'entries': entries
        }

    def parse_txt2(self, data):
        entries = self.txt2['header']['entries']
        data_index = 0
        strings = []
        data_length = len(data)

        # all offsets are forward by 4 for some reason...
        strings_start = -4

        for i in range(entries):
            offset = struct.unpack('%sI' % self.order, data[data_index:data_index + 4])[0]
            data_index += 4

            start = strings_start + offset
            end = start
            while end < data_length:
                if data[end:end + 2] == '\x00\x00':
                    break
                end += 2

            strings.append(data[start:end])

        self.txt2['data'] = strings

    def parse_nli1_header(self, data):
        return None

    def parse_nli1(self, data):
        pass

    def to_json(self, filename):
        file = open(filename, 'w')

        data = {
            'msbt': {
                'strings': {},
                'structure': self.lbl1['data']
            }
        }

        strings = []
        for list in self.lbl1['data']:
            for string in list:
                strings.append({
                    'name': string['string'],
                    'value': self.txt2['data'][string['index']].decode('utf-16').encode('utf-8')
                })
        strings.sort(self.sort_json_strings)
        data['msbt']['strings'] = strings

        file.write(json.dumps(data, indent=2))
        file.close()

        print('Saved to file: %s' % filename)

    def sort_json_strings(self, x, y):
        xn = x['name'].lower()
        yn = y['name'].lower()

        if xn < yn:
            return -1
        if xn > yn:
            return 1

        return 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: %s filename.msbt output.json' % sys.argv[0])
        sys.exit(1)

    if not os.path.exists(sys.argv[1]):
        print('File not found: %s' % sys.argv[1])
        sys.exit(1)

    if os.path.exists(sys.argv[2]):
        print('Output file exists: %s' % sys.argv[2])
        answer = None
        while answer is None or answer.lower() not in ('y', 'n'):
            if answer is not None:
                print('Please answer y or n')

            answer = raw_input('Overwrite? (y/N) ')

            if len(answer) == 0:
                answer = 'n'

        if answer == 'n':
            print('Aborting')
            sys.exit(1)

    msbt = Msbt(open(sys.argv[1]).read(), True)
    msbt.to_json(sys.argv[2])
