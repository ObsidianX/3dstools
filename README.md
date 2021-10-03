# 3DS Data Tools
Tools for extracting and packing resources found in 3DS games


## msbt.py
String resource extractor for MSBT 'MsgStdBn' files.

Converts between MSBT and JSON files for translation or string modification.

### Usage

```
usage: msbt.py [-h] [-v] [-d] [-c] (-x | -p) [-y] -j JSON msbt_file

MsgStdBn Parser

positional arguments:
  msbt_file             MSBT file to parse

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         print more data when working
  -d, --debug           print debug information
  -c, --colors          decode colors in strings
  -x, --extract         extract MSBT to plain text
  -p, --pack            pack plain text into an MSBT file
  -y, --yes             answer "Yes" to any questions (overwriting files)
  -j JSON, --json JSON  JSON document to read from or write to
```

#### Examples

Convert an MSBT to JSON for editing:

```
msbt.py -x -j Sample.json Sample.msbt
```

Convert from JSON back to MSBT:

```
msbt.py -p -j Sample.json Sample.msbt
```

If strings contain color codes (which are invalid UTF-16 bytes) then use the `--colors` flag to parse them:

```
msbt.py -x -c -j Sample.json Sample.msbt
```

Make sure you mirror the `--colors` flag when repacking:

```
msbt.py -p -c -j Sample.json Sample.msbt
```


### Colors

In at least one game, colors are prefixed with two bytes, `\u0003\u0004` followed by a 32-bit color code.  The `--colors` flag will ensure that the 4 bytes following the color prefix are not parsed as UTF-16.  The resulting output string will look like:

```json
"\u0003\u0004[#ff112233]Color"
```

When packing the MSBT with the `--colors` flag, the parser will look for those color markers and write them as 4-byte integers just as they were read out originally.  For example (little endian):

```
30 00 40 00 33 22 11 ff 43 6f 6c 6f 72
```

## sarc.py
SARC (Sorted ARChive?) tool that can extract and pack both uncompressed and ZLIB compressed archives.

Uses TAR-like command line syntax.

### Usage

```
usage: sarc.py [-h] [-v] [-d] [-y] [-z] [--compression-level LEVEL]
               (-x | -c | -t) [-l | -b] -f archive
               [file [file ...]]

SARC Archive Tool

positional arguments:
  file                  files to add to an archive

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         print more data when working
  -d, --debug           print debug information
  -y, --yes             answer "yes" to questions (overwriting files)
  -z, --zlib            use ZLIB to compress or decompress the archive
  --compression-level LEVEL
                        ZLIB compression level (default: 6)
  -x, --extract         extract the SARC
  -c, --create          create a SARC
  -t, --list            list contents
  -l, --little-endian   use little endian encoding when creating an archive
                        (default)
  -b, --big-endian      use big endian encoding when creating an archive
  -f archive, --archive archive
                        the SARC filename
```

#### Examples

Extract an uncompressed SARC:

```
sarc.py -xf Sample.sarc
```

Create a compressed SARC:

```
sarc.py -czf Sample.zlib file1.txt file2.txt subdir/
```

List contents of a compressed SARC:

```
sarc.py -tzf Sample.zlib
```
```
subdir/file3.txt
subdir/file4.txt
file1.txt
file2.txt
```

## bffnt.py

BFFNT extract/create tool.  Creates a PNG file from the texture atlases in a BFFNT as well as a JSON manifest.

### Usage

```
usage: bffnt [-h] [-v] [-d] [-y] [-l | -b] (-c | -x) -f bffnt

BFFNT Converter Tool

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         print more data when working
  -d, --debug           print debug information
  -y, --yes             answer yes to any questions (overwriting files)
  -a, --ensure-ascii    turn off ensure_ascii option when dump json file
  -l, --little-endian   Use little endian encoding in the created BFFNT file
                        (default)
  -b, --big-endian      Use big endian encoding in the created BFFNT file
  -c, --create          create BFFNT file from extracted files
  -x, --extract         extract BFFNT into PNG/JSON files
  -f bffnt, --file bffnt
                        BFFNT file
```

#### Examples

Extract a BFFNT to PNG/JSON:

```
bffnt.py -xf Sample.bffnt
```

Results:

```
Sample_manifest.json
Sample_sheet0.png
```

Create a BFFNT from PNG/JSON:

```
bffnt.py -cf Sample.bffnt
```

Note: `Sample_manifest.json` and `Sample_sheet0.png` must be in the current directory to build `Sample.bffnt`

## bflim.py

BFLIM converter to and from PNG files.  This tool is still in development.

Goal: Apply swizzle when creating BFLIMs.

### Usage

```
usage: bflim [-h] [-v] [-d] [-y] [-l | -b] [-s {0,8,4}] (-c png | -x | -i)
             bflim_file

BFLIM Converter

positional arguments:
  bflim_file            FLIM file

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         print more data when working
  -d, --debug           print debug information
  -y, --yes             answer yes to any questions (overwriting files)
  -l, --little-endian   use Little Endian when reading/writing (default)
  -b, --big-endian      use Big Endian when reading/writing
  -s {0,8,4}, --swizzle {0,8,4}
                        set the swizzle type of the output BFLIM (default: 0)
                        0 - none; 4 - rotate 90deg; 8 - transpose
  -c png, --create png  create BFLIM file from PNG
  -x, --extract         convert BFLIM to PNG
  -i, --info            just list debug info and quit
```

#### Examples

Convert BFLIM to PNG:

```
bflim.py -x image.bflim
```

Convert PNG to BFLIM:

```
bflim.py -c image.png image.bflim
```

Convert PNG to BFLIM, setting swizzle to 90 degree rotation:

Note: Swizzling is only applied if OpenCV is available.

```
bflim.py -s 4 -c image.png image.bflim
```
