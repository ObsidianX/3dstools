#!/usr/bin/python
import argparse
import os.path
import struct
import sys
import json

MSBT_HEADER_LEN = 0x20
NLI1_HEADER_LEN = 0x14
TXT2_HEADER_LEN = 0x14
LBL1_HEADER_LEN = 0x14
ATR1_HEADER_LEN = 0x14

MSBT_MAGIC = 'MsgStdBn'
NLI1_MAGIC = 'NLI1'
TXT2_MAGIC = 'TXT2'
LBL1_MAGIC = 'LBL1'
ATR1_MAGIC = 'ATR1'

SECTION_END_MAGIC = '\xAB\xAB\xAB\xAB'
SECTION_END_MAGIC_SINGLE = '\xAB'


class Msbt:
    order = None
    invalid = False
    sections = {}

    def __init__(self, filename, verbose=False, debug=False):
        self.verbose = verbose
        self.debug = debug
        self.filename = filename
        self.file_size = os.stat(filename).st_size

    def read(self):
        data = open(self.filename, 'r').read()

        self._parse_header(data[:MSBT_HEADER_LEN])
        if self.invalid:
            return
        position = MSBT_HEADER_LEN

        sections_left = self.section_count
        while sections_left > 0 and position < self.file_size:
            magic = data[position:position + 4]

            if magic == LBL1_MAGIC:
                self._parse_lbl1_header(data[position:position + LBL1_HEADER_LEN])
                position += LBL1_HEADER_LEN
                if self.invalid:
                    return
                self._parse_lbl1_data(data[position:position + self.sections['LBL1']['size']])
                position += self.sections['LBL1']['size']

            elif magic == ATR1_MAGIC:
                self._parse_atr1_header(data[position:position + ATR1_HEADER_LEN])
                position += ATR1_HEADER_LEN
                if self.invalid:
                    return

                # TODO: parse ATR1 data?
                position += self.sections['ATR1']['size']

            elif magic == TXT2_MAGIC:
                self._parse_txt2_header(data[position:position + TXT2_HEADER_LEN])
                position += TXT2_HEADER_LEN
                if self.invalid:
                    return
                self._parse_txt2_data(data[position:position + self.sections['TXT2']['size']])
                position += self.sections['TXT2']['size']

            # TODO:
            # elif magic == NLI1_MAGIC:

            sections_left -= 1

            while position < self.file_size:
                if data[position] != '\xAB':
                    break
                position += 1

    def save(self):
        pass

    def to_json(self, filename):
        output = {
            'strings': {},
            'structure': {}
        }

        label_lists = self.sections['LBL1']['data']
        for label_list in label_lists:
            for label in label_lists:
                id = label[0]
                name = label[1]
                value = self.sections['TXT2']['data'][id]
                output['strings'][name] = value

        file = open(filename, 'w')
        file.write(json.dumps(output, indent=2))

    def from_json(self, filename):
        pass

    def _parse_header(self, data):
        magic, bom, unknown1, unknown2, sections, unknown3, file_size, unknown4 = struct.unpack('=8s5HI10s', data)

        if magic != MSBT_MAGIC:
            print('Invalid header magic bytes: %s (expected %s)' % (magic, MSBT_MAGIC))
            self.invalid = True
            return

        if bom == 0xFFFE:
            self.order = '>'
        elif bom == 0xFEFF:
            self.order = '<'

        if self.order is None:
            print('Invalid byte-order marker: 0x%x (expected either 0xFFFE or 0xFEFF)' % bom)
            self.invalid = True
            return

        if file_size != self.file_size:
            print('Invalid file size reported: %d (OS reports %d)' % (file_size, self.file_size))

        self.section_count = sections
        # save for repacking
        self.header_unknowns = [
            unknown1,
            unknown2,
            unknown3,
            unknown4
        ]

        if self.debug:
            print('MSBT Magic bytes: %s' % magic)
            print('MSBT Byte-order: %s' % self.order)
            print('MSBT Sections: %d' % sections)
            print('MSBT File size: %s' % file_size)

            print('\nUnknown1: 0x%x' % unknown1)
            print('Unknown2: 0x%x' % unknown2)
            print('Unknown3: 0x%x' % unknown3)
            print('Unknown4: 0x%s\n' % unknown4.encode('hex'))

    def _parse_lbl1_header(self, data):
        magic, size, unknown, entries = struct.unpack('%s4sI8sI' % self.order, data)

        if magic != LBL1_MAGIC:
            print('Invalid LBL1 magic bytes: %s (expected %s)' % (magic, LBL1_MAGIC))
            self.invalid = True
            return

        # -4 from size since we're reading the entries as part of the header
        self.sections['LBL1'] = {
            'size': size - 4,
            'entries': entries,
            'unknown': unknown
        }

        if self.debug:
            print('LBL1 Magic bytes: %s' % magic)
            print('LBL1 Size: %d' % size)
            print('LBL1 Entries: %d' % entries)

            print('\nLBL1 Unknown: 0x%s\n' % unknown.encode('hex'))

    def _parse_lbl1_data(self, data):
        entries = self.sections['LBL1']['entries']
        position = 0

        lists = []

        if self.debug:
            print('\nLBL1 Entries:')

        entry = 1
        while entries > 0:
            count, offset = struct.unpack('%s2I' % self.order, data[position:position + 8])
            if self.debug:
                print('\n#%d' % entry)
                entry += 1
                print('List length: %d' % count)
                print('First offset: 0x%x' % offset)

            position += 8
            entries -= 1
            offset -= 4

            list_ = []

            for i in range(count):
                length = ord(data[offset])
                name_end = offset + length + 1
                name = data[offset + 1:name_end]
                id_offset = name_end
                id = struct.unpack('%sI' % self.order, data[id_offset:id_offset + 4])[0]
                list_.append((id, name))

                if self.debug:
                    print('  %d: %s' % (id, name))

            lists.append((list_, offset))

        if self.debug:
            print('')

        self.sections['LBL1']['data'] = lists

    def _parse_atr1_header(self, data):
        magic, size, unknown1, unknown2, entries = struct.unpack('%s4s4I' % self.order, data)

        if magic != ATR1_MAGIC:
            print('Invalid ATR1 magic bytes: %s (expected %s)' % (magic, ATR1_MAGIC))
            self.invalid = True
            return

        # -4 from size since we're reading the entries as part of the header
        self.sections['ATR1'] = {
            'size': size - 4,
            'entries': entries,
            'unknown1': unknown1,
            'unknown2': unknown2
        }

        if self.debug:
            print('ATR1 Magic bytes: %s' % magic)
            print('ATR1 Size: %d' % size)
            print('ATR1 Entries: %d' % entries)

            print('\nATR1 Unknown1: 0x%x' % unknown1)
            print('ATR1 Unknown2: 0x%x\n' % unknown2)

    def _parse_txt2_header(self, data):
        magic, size, unknown1, unknown2, entries = struct.unpack('%s4s4I' % self.order, data)

        if magic != TXT2_MAGIC:
            print('Invalid TXT2 magic bytes: %s (expected %s)' % (magic, TXT2_MAGIC))
            self.invalid = True
            return

        # -4 from size since we're reading the entries as part of the header
        self.sections['TXT2'] = {
            'size': size - 4,
            'entries': entries,
            'unknown1': unknown1,
            'unknown2': unknown2
        }

        if self.debug:
            print('TXT2 Magic bytes: %s' % magic)
            print('TXT2 Size: %d' % size)
            print('TXT2 Entries: %d' % entries)

            print('\nTXT2 Unknown1: 0x%x' % unknown1)
            print('TXT2 Unknown2: 0x%x\n' % unknown2)

    def _parse_txt2_data(self, data):
        entries = self.sections['TXT2']['entries']
        data_len = len(data)

        strings = []

        position = 0
        index = 0
        while entries > 0:
            print('index %d' % index)
            string_start = struct.unpack('I', data[position:position + 4])[0]
            position += 4
            entries -= 1

            # -4 since we included entries in the header
            string_start -= 4
            string_end = string_start

            while string_end < data_len:
                string_end += 2
                if data[string_end:string_end + 2] == '\x00\x00':
                    break

            string = data[string_start:string_end].decode('utf-16').encode('utf-8')
            strings.append(string)

            if self.debug:
                print('%d: %s' % (index, string))
                index += 1

        self.sections['TXT2']['data'] = strings


def prompt_yes_no(prompt):
    answer = None
    while answer not in ('y', 'n'):
        if answer is not None:
            print('Please answer "y" or "n"')

        answer = raw_input(prompt).lower()

        if len(answer) == 0:
            answer = 'n'

    return answer


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MsgStdBn Parser')
    parser.add_argument('-v', '--verbose', help='print more data when working', action='store_true', default=False)
    parser.add_argument('-d', '--debug', help='print debug information', action='store_true', default=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-x', '--extract', help='extract MSBT to plain text', action='store_true', default=False)
    group.add_argument('-p', '--pack', help='pack plain text into an MSBT file', action='store_true', default=False)
    parser.add_argument('-j', '--json', help='JSON document to read from or write to', required=True)
    parser.add_argument('msbt_file', help='MSBT file to parse')

    args = parser.parse_args()

    if args.extract and not os.path.exists(args.msbt_file):
        print('MSBT file not found!')
        print(args.msbt_file)
        sys.exit(1)

    if args.extract and os.path.exists(args.json):
        print('JSON output file exists.')
        answer = prompt_yes_no('Overwrite? (y/N) ')

        if answer == 'n':
            print('Aborted.')
            sys.exit(1)

    if args.pack and not os.path.exists(args.json):
        print('JSON file not found!')
        print(args.json)
        sys.exit(1)

    if args.pack and os.path.exists(args.msbt_file):
        print('MSBT output file exists.')
        answer = prompt_yes_no('Overwrite? (y/N) ')

        if answer == 'n':
            print('Aborted.')
            sys.exit(1)

    msbt = Msbt(args.msbt_file, verbose=args.verbose, debug=args.debug)

    if args.pack:
        msbt.from_json(args.json)
        msbt.save()
    elif args.extract:
        msbt.read()
        if msbt.invalid:
            print('Invalid MSBT file!')
            sys.exit(1)
        msbt.to_json(args.json)
