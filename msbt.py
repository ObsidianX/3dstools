#!/usr/bin/python
import argparse
import json
import os.path
import re
import struct
import sys

MSBT_HEADER_LEN = 0x20
LBL1_HEADER_LEN = 0x14
ATR1_HEADER_LEN = 0x14
TXT2_HEADER_LEN = 0x14

MSBT_MAGIC = 'MsgStdBn'
LBL1_MAGIC = 'LBL1'
ATR1_MAGIC = 'ATR1'
TXT2_MAGIC = 'TXT2'

MSBT_HEADER_STRUCT = '=8s5HI10s'
LBL1_HEADER_STRUCT = '%s4sI8sI'
ATR1_HEADER_STRUCT = '%s4s4I'
TXT2_HEADER_STRUCT = '%s4s4I'

SECTION_END_MAGIC = '\xAB'
COLOR_ESCAPE = '\x03\x00\x04\x00'


class Msbt:
    order = None
    invalid = False
    sections = {}
    section_order = []

    def __init__(self, verbose=False, debug=False, colors=False):
        self.verbose = verbose
        self.debug = debug
        self.colors = colors

    def read(self, filename):
        self.filename = filename
        self.file_size = os.stat(filename).st_size
        data = open(self.filename, 'rb').read()

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
                self._parse_lbl1_data(data[position:position + self.sections['LBL1']['header']['size']])
                position += self.sections['LBL1']['header']['size']

            elif magic == ATR1_MAGIC:
                self._parse_atr1_header(data[position:position + ATR1_HEADER_LEN])
                position += ATR1_HEADER_LEN
                if self.invalid:
                    return

                # TODO: parse ATR1 data?
                position += self.sections['ATR1']['header']['size']

            elif magic == TXT2_MAGIC:
                self._parse_txt2_header(data[position:position + TXT2_HEADER_LEN])
                position += TXT2_HEADER_LEN
                if self.invalid:
                    return
                self._parse_txt2_data(data[position:position + self.sections['TXT2']['header']['size']])
                position += self.sections['TXT2']['header']['size']

            # TODO:
            # elif magic == NLI1_MAGIC:
            
            else:
                position += struct.unpack('%sI' % self.order, data[position + 4:position + 8])[0]
                position += TXT2_HEADER_LEN
                if self.debug:
                    print('\nUnknown section skipped')
                    print('Unknown section Magic bytes\n: %s' % magic)

            sections_left -= 1

            self.section_order.append(magic)

            while position < self.file_size:
                if data[position] != '\xAB':
                    break
                position += 1

    def save(self, filename):
        output = open(filename, 'wb')

        bom = 0
        if self.order == '>':
            bom = 0xFFFE
        elif self.order == '<':
            bom = 0xFEFF

        if self.debug:
            print('\nMSBT Magic: %s' % MSBT_MAGIC)
            print('MSBT Byte-order marker: 0x%x' % bom)
            print('MSBT Unknown1: 0x%x' % self.header_unknowns[0])
            print('MSBT Unknown2: 0x%x' % self.header_unknowns[1])
            print('MSBT Sections: %d' % self.section_count)
            print('MSBT Unknown3: 0x%x' % self.header_unknowns[2])
            print('MSBT File size: (unknown)')
            print('MSBT Unknown4: 0x%s\n' % self.header_unknowns[3].encode('hex'))

        msbt_header = struct.pack(MSBT_HEADER_STRUCT, MSBT_MAGIC, bom, self.header_unknowns[0], self.header_unknowns[1],
                                  self.section_count, self.header_unknowns[2], 0, str(self.header_unknowns[3]))
        output.write(msbt_header)

        for section in self.section_order:
            data = {
                'LBL1': self._serialize_lbl1,
                'ATR1': self._serialize_atr1,
                'TXT2': self._serialize_txt2
            }[section]()
            output.write(data)

            position = output.tell()
            # write the section end bytes until the next 0x10 alignment
            padding = (16 - (position % 16))
            if padding < 16:
                output.write(SECTION_END_MAGIC * padding)

        # update the size in the header with the final size
        size = output.tell()
        output.seek(0x12)
        output.write(struct.pack('=I', size))

        output.close()

        print('\nMSBT File size: %d' % size)

    def to_json(self, filename):
        output = {
            'strings': {},
            'structure': {}
        }

        label_lists = self.sections['LBL1']['data']
        for label_list in label_lists:
            for label in label_list[0]:
                id = label[0]
                name = label[1]
                value = self.sections['TXT2']['data'][id]
                output['strings'][name] = value

        output['structure']['MSBT'] = {
            'header': {
                'byte_order': self.order,
                'sections': self.section_count,
                'section_order': self.section_order,
                'unknowns': self.header_unknowns
            }
        }

        for section in self.sections.keys():
            output['structure'][section] = {
                'header': self.sections[section]['header']
            }

        output['structure']['LBL1']['lists'] = self.sections['LBL1']['data']

        file = open(filename, 'w')
        file.write(json.dumps(output, indent=2, sort_keys=True))

    def from_json(self, filename):
        json_data = json.load(open(filename, 'r'))
        strings = json_data['strings']
        structure = json_data['structure']

        lbl1 = structure['LBL1']
        self.sections['LBL1'] = {
            'header': lbl1['header'],
            'data': lbl1['lists']
        }

        self.sections['ATR1'] = {
            'header': json_data['structure']['ATR1']['header']
        }

        self.sections['TXT2'] = {
            'header': json_data['structure']['TXT2']['header'],
            'data': []
        }

        msbt_header = json_data['structure']['MSBT']['header']
        self.order = msbt_header['byte_order']
        self.section_order = msbt_header['section_order']
        self.section_count = msbt_header['sections']
        self.header_unknowns = msbt_header['unknowns']

        for i in range(len(json_data['strings'])):
            self.sections['TXT2']['data'].append('')

        label_lists = self.sections['LBL1']['data']
        for label_list in label_lists:
            for label in label_list[0]:
                id = label[0]
                name = label[1]
                value = strings[name]

                self.sections['TXT2']['data'][id] = value

    def _parse_header(self, data):
        magic, bom, unknown1, unknown2, sections, unknown3, file_size, unknown4 = struct.unpack(MSBT_HEADER_STRUCT,
                                                                                                data)

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
        magic, size, unknown, entries = struct.unpack(LBL1_HEADER_STRUCT % self.order, data)

        if magic != LBL1_MAGIC:
            print('Invalid LBL1 magic bytes: %s (expected %s)' % (magic, LBL1_MAGIC))
            self.invalid = True
            return

        # -4 from size since we're reading the entries as part of the header
        self.sections['LBL1'] = {
            'header': {
                'size': size - 4,
                'entries': entries,
                'unknown': unknown
            }
        }

        if self.debug:
            print('LBL1 Magic bytes: %s' % magic)
            print('LBL1 Size: %d' % size)
            print('LBL1 Entries: %d' % entries)

            print('\nLBL1 Unknown: 0x%s\n' % unknown.encode('hex'))

    def _parse_lbl1_data(self, data):
        entries = self.sections['LBL1']['header']['entries']
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
                offset = id_offset + 4

                if self.debug:
                    print('  %d: %s' % (id, name))

            lists.append((list_, offset))

        if self.debug:
            print('')

        self.sections['LBL1']['data'] = lists

    def _parse_atr1_header(self, data):
        magic, size, unknown1, unknown2, entries = struct.unpack(ATR1_HEADER_STRUCT % self.order, data)

        if magic != ATR1_MAGIC:
            print('Invalid ATR1 magic bytes: %s (expected %s)' % (magic, ATR1_MAGIC))
            self.invalid = True
            return

        # -4 from size since we're reading the entries as part of the header
        self.sections['ATR1'] = {
            'header': {
                'size': size - 4,
                'entries': entries,
                'unknown1': unknown1,
                'unknown2': unknown2
            }
        }

        if self.debug:
            print('ATR1 Magic bytes: %s' % magic)
            print('ATR1 Size: %d' % size)
            print('ATR1 Entries: %d' % entries)

            print('\nATR1 Unknown1: 0x%x' % unknown1)
            print('ATR1 Unknown2: 0x%x\n' % unknown2)

    def _parse_txt2_header(self, data):
        magic, size, unknown1, unknown2, entries = struct.unpack(TXT2_HEADER_STRUCT % self.order, data)

        if magic != TXT2_MAGIC:
            print('Invalid TXT2 magic bytes: %s (expected %s)' % (magic, TXT2_MAGIC))
            self.invalid = True
            return

        # -4 from size since we're reading the entries as part of the header
        self.sections['TXT2'] = {
            'header': {
                'size': size - 4,
                'entries': entries,
                'unknown1': unknown1,
                'unknown2': unknown2
            }
        }

        if self.debug:
            print('TXT2 Magic bytes: %s' % magic)
            print('TXT2 Size: %d' % size)
            print('TXT2 Entries: %d' % entries)

            print('\nTXT2 Unknown1: 0x%x' % unknown1)
            print('TXT2 Unknown2: 0x%x\n' % unknown2)

    def _parse_txt2_data(self, data):
        entries = self.sections['TXT2']['header']['entries']
        data_len = len(data)

        offsets = []
        strings = []

        for i in range(entries):
            start = i * 4
            end = (i + 1) * 4
            offsets.append(struct.unpack('%sI' % self.order, data[start:end])[0] - 4)

        index = 0
        for i in range(entries):
            start = offsets[i]
            if i < entries - 1:
                end = offsets[i + 1]
            else:
                end = data_len

            string_data = data[start:end]

            position = 0
            string = ''
            substrings = []
            while position < len(string_data):
                if self.colors and len(string) >= 4 and string[-4:] == COLOR_ESCAPE:
                    # save color information
                    color = struct.unpack('%sI' % self.order, string_data[position:position + 4])[0]
                    position += 4
                    string += ('[#%08x]' % color).encode('utf-16-%s' % ('-le' if self.order == '<' else '-be'))
                    continue

                utf16char = string_data[position:position + 2]
                if utf16char != '\x00\x00':
                    string += utf16char
                else:
                    substrings.append(string.decode('utf-16', 'replace'))
                    string = ''
                position += 2

            strings.append(substrings)

            if self.debug:
                print('%d: %s' % (index, string))
                index += 1

        self.sections['TXT2']['data'] = strings

    def _serialize_lbl1(self):
        entries = self.sections['LBL1']['header']['entries']

        header_bytes = struct.pack(LBL1_HEADER_STRUCT % self.order, LBL1_MAGIC, 0,
                                   str(self.sections['LBL1']['header']['unknown']), entries)
        section1_bytes = ''
        section2_bytes = ''

        # each section 1 entry is 8 bytes long
        # but we're including the entries data in the header bytes so we need to compensate for that
        section2_offset = (entries * 8) + 4

        for label_list in self.sections['LBL1']['data']:
            count = len(label_list[0])
            offset = len(section2_bytes)
            for label in label_list[0]:
                length = len(label[1])
                section2_bytes += struct.pack('%sB%dsI' % (self.order, length), length, str(label[1]), label[0])
            section1_bytes += struct.pack('%s2I' % self.order, count, section2_offset + offset)

        size = len(section1_bytes) + len(section2_bytes) + 4
        header_bytes = header_bytes[:4] + struct.pack('%sI' % self.order, size) + header_bytes[8:]

        if self.debug:
            print('\nLBL1 Magic: %s' % LBL1_MAGIC)
            print('LBL1 Size: %d' % size)
            print('LBL1 Unknown: 0x%s' % self.sections['LBL1']['header']['unknown'].encode('hex'))
            print('LBL1 Entries: %d\n' % entries)

        return header_bytes + section1_bytes + section2_bytes

    def _serialize_atr1(self):
        # ATR1 is unknown right now so we're going to just pad the section
        # (which is all we've got in Rhythm Tengoku string files

        header = self.sections['ATR1']['header']

        if self.debug:
            print('\nATR1 Magic: %s' % ATR1_MAGIC)
            print('ATR1 Size: %d' % (header['size'] + 4))
            print('ATR1 Unknown1: 0x%d' % header['unknown1'])
            print('ATR1 Unknown2: 0x%d' % header['unknown2'])
            print('ATR1 Entries: %d\n' % header['entries'])

        header_bytes = struct.pack(ATR1_HEADER_STRUCT % self.order, ATR1_MAGIC, header['size'] + 4, header['unknown1'],
                                   header['unknown2'], header['entries'])

        atr1_data_bytes = struct.pack('%s%ds' % (self.order, header['size']), '\0' * header['size'])

        return header_bytes + atr1_data_bytes

    def _serialize_txt2(self):
        # section 1: offsets for each index to the data section
        # section 2: utf-16 strings with a null terminator

        strings = self.sections['TXT2']['data']
        entries = len(strings)
        header = self.sections['TXT2']['header']

        header_bytes = struct.pack(TXT2_HEADER_STRUCT % self.order, TXT2_MAGIC, 0, header['unknown1'],
                                   header['unknown2'], entries)
        section1_bytes = ''
        section2_bytes = ''

        # each entry is a single 32-bit integer representing an offset from the start of section1 to an area in section2
        section1_length = entries * 4

        order = ''
        if self.order == '<':
            order = '-le'
        elif self.order == '>':
            order = '-be'

        for string_list in strings:
            section1_bytes += struct.pack('%sI' % self.order, section1_length + len(section2_bytes) + 4)
            for string in string_list:
                utf16string = string.encode('utf-16%s' % order)

                if self.colors:
                    haystack = string
                    matcher = ''
                    utf16string = ''

                    while matcher is not None:
                        matcher = re.search('(?P<pre>.*)\\[#(?P<color>[a-fA-F0-9]{8})\\](?P<post>.*)', haystack, re.DOTALL)

                        if matcher is not None:
                            pre = matcher.group('pre')
                            color = matcher.group('color')
                            colorValue = int(color, 16)
                            post = matcher.group('post')
                            utf16string += pre.encode('utf-16%s' % order)
                            utf16string += struct.pack('%sI' % self.order, colorValue)
                            haystack = post
                        else:
                            utf16string += haystack.encode('utf-16%s' % order)

                section2_bytes += struct.pack('=%ds' % len(utf16string), utf16string)
                section2_bytes += '\x00\x00'

        size = len(section1_bytes) + len(section2_bytes) + 4
        header_bytes = header_bytes[:4] + struct.pack('%sI' % self.order, size) + header_bytes[8:]

        if self.debug:
            print('TXT2 Magic: %s' % TXT2_MAGIC)
            print('TXT2 Size: %d' % size)
            print('TXT2 Unknown1: 0x%x' % header['unknown1'])
            print('TXT2 Unknown2: 0x%x' % header['unknown2'])
            print('TXT2 Entries: %d' % entries)

        return header_bytes + section1_bytes + section2_bytes


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
    parser.add_argument('-c', '--colors', help='decode colors in strings', action='store_true', default=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-x', '--extract', help='extract MSBT to plain text', action='store_true', default=False)
    group.add_argument('-p', '--pack', help='pack plain text into an MSBT file', action='store_true', default=False)
    parser.add_argument('-y', '--yes', help='answer "Yes" to any questions (overwriting files)', action='store_true',
                        default=False)
    parser.add_argument('-j', '--json', help='JSON document to read from or write to', required=True)
    parser.add_argument('msbt_file', help='MSBT file to parse')

    args = parser.parse_args()

    if args.extract and not os.path.exists(args.msbt_file):
        print('MSBT file not found!')
        print(args.msbt_file)
        sys.exit(1)

    if args.extract and os.path.exists(args.json) and not args.yes:
        print('JSON output file exists.')
        answer = prompt_yes_no('Overwrite? (y/N) ')

        if answer == 'n':
            print('Aborted.')
            sys.exit(1)

    json_dirname = os.path.dirname(args.json)
    if len(json_dirname) > 0 and not os.path.exists(json_dirname):
        print('Folder not found: %s' % json_dirname)
        sys.exit(1)

    if args.pack and not os.path.exists(args.json):
        print('JSON file not found!')
        print(args.json)
        sys.exit(1)

    if args.pack and os.path.exists(args.msbt_file) and not args.yes:
        print('MSBT output file exists.')
        answer = prompt_yes_no('Overwrite? (y/N) ')

        if answer == 'n':
            print('Aborted.')
            sys.exit(1)

    msbt = Msbt(verbose=args.verbose, debug=args.debug, colors=args.colors)

    if args.pack:
        msbt.from_json(args.json)
        msbt.save(args.msbt_file)
    elif args.extract:
        msbt.read(args.msbt_file)
        if msbt.invalid:
            print('Invalid MSBT file!')
            sys.exit(1)
        msbt.to_json(args.json)
        print('All good!')
