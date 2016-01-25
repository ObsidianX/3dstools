# 3DS Data Tools
Tools for extracting and packing resources found in 3DS games


## msbt.py
String resource extractor for MSBT 'MsgStdBn' files.

Converts between MSBT and JSON files for translation or string modification.

### Usage

```
usage: msbt.py [-h] [-v] [-d] (-x | -p) [-y] -j JSON msbt_file

MsgStdBn Parser

positional arguments:
  msbt_file             MSBT file to parse

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         print more data when working
  -d, --debug           print debug information
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

## sarc.py
SARC (Simple ARChive?) tool that can extract and pack both uncompressed and ZLIB compressed archives.

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
sarc.py -tzf Sample.sarc
```
```
file1.txt
file2.txt
subdir/file3.txt
subdir/file4.txt
```
