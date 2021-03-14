#! /usr/bin/python3
# -*- coding: utf-8 -*-
'''
bbd_lz_rle

A tool for compressing and decompressing data in GameBoy Advance games:
1606 - B-Densetsu! Battle B-Daman - Moero! B-Tamashii! (J)
2414 - B-Densetsu! Battle B-Daman - Fire Spirit! Honootamashii! (J)
2463 - Battle B-Daman (U)
2507 - Battle B-Daman - Fire Spirits (U)
and possibly other Atlus games.

Version:   0.9
Author:    Griever
Web site:  https://github.com/romhack/bbd_lz_rle
License:   MIT License https://opensource.org/licenses/mit-license.php
'''


try:
    from io import BytesIO
    from itertools import repeat
    from collections import namedtuple
    import click

except ImportError as err:
    print("Could not load %s module." % (err))
    raise SystemExit


MAX_CHUNK_LEN = 0x1F  # 5 bits for chunk length
MAX_PLAIN_COUNT = 0x3FF  # 10 bits on plain length
MAX_OFFSET = 0xFFFF  # 16 bits on LZ offs
MAX_RAW_LEN = 0x7F  # 7 bits on raw counter

# during compression candidates are compared first by gain, if equal, by encoded plain length
ComparePair = namedtuple('ComparePair', 'gain plain_len')
CompressCandidate = namedtuple(
    'CompressCandidate', 'cmp_pair command')


@click.group()
def cli():
    """A tool for compressing and decompressing data for Battle B-Daman GBA games.
    """
    pass


@cli.command(name='unpack', short_help='decompress file')
@click.argument('in_name')
@click.option('--address', '-a', default='0', help='Offset of compressed block start.')
@click.option('--out_name', '-o', default='decompressed.bin', help='Output plain file name.')
def decompress_file(in_name, address, out_name):
    """Decompress packed block from given IN_NAME file.
    Offset and output file name can be provided, otherwise default '0' and 'decompressed.bin' will be used.

    """
    address = int(address, 0)
    with open(in_name, "rb") as encoded_file:
        encoded_file.seek(address)
        encoded = BytesIO(encoded_file.read())
    comms = deserialize(encoded)
    decoded = decode(comms)
    with open(out_name, "wb") as decoded_file:
        decoded_file.write(bytes(decoded))
    print(f"Compressed block size was 0x{encoded.tell():X}")


@cli.command(name='pack', short_help='compress file')
@click.argument('in_name')
@click.option('--out_name', '-o', default='compressed.bin', help='Output packed file name.')
def compress_file(in_name, out_name):
    """Compress plain IN_NAME file.
    Output file name can be provided, otherwise default 'compressed.bin' will be used.

    """
    with open(in_name, "rb") as plain_file:
        plain = list(plain_file.read())
    encoded = encode(plain)
    serialized = serialize(encoded)
    with open(out_name, "wb") as encoded_file:
        encoded_file.write(bytes(serialized))


def deserialize(stream):
    """
    Deserializes given compressed stream to list of dict commands

    Parameters
    ----------
    stream : BinaryIO.bytes
        Input compressed bytes stream.

    Raises
    ------
    error
        If attempt to read from exhausted stream, it's corrupted, deserialize failed.

    Returns
    -------
    list of dictionaries
        list of dicts (compress commands) for further unpacking by decode.
        {"method": "lz", "len": plain_len, "offs": lz_offs},
        {"method": "rle", "len": plain_len, "chunk": chunk} or
        {"method": "raw", "data": list(read_safe(plain_len))}

    """
    def read_safe(n):
        bstr = stream.read(n)
        assert len(bstr) >= n, "Compressed stream ended prematurely"
        return bstr

    flag = ord(read_safe(1))
    if flag & 0x80:  # compression
        chunk_size = (flag & 0x7F) >> 2
        plain_len = ((flag & 3) << 8) + ord(read_safe(1))
        if chunk_size == MAX_CHUNK_LEN:  # lz coding
            lz_offs = int.from_bytes(read_safe(2), "little")
            return [{"method": "lz", "len": plain_len, "offs": lz_offs}] + deserialize(stream)
        # rle coding
        chunk = list(read_safe(chunk_size + 1))
        return [{"method": "rle", "len": plain_len, "chunk": chunk}] + deserialize(stream)
    # raw method
    plain_len = flag & 0x7f
    if plain_len != 0:
        return [{"method": "raw", "data": list(read_safe(plain_len))}] + deserialize(stream)
    # end of compression found
    return []


def decode(commands):
    """
    decodes given commands to plain buffer of unpacked bytes

    Parameters
    ----------
    commands : dictionary list
        commands to unpack

    Returns
    -------
    buffer : list of ints
        unpacked bytes list.

    """
    buffer = []
    for com in commands:
        if com["method"] == "rle":
            buffer += com["chunk"] * com["len"]
        elif com["method"] == "lz":
            lz_offs = com["offs"]
            lz_len = com["len"]
            # for lz outbound copy
            cyclic_buffer = buffer + buffer[lz_offs:] * lz_len
            buffer += cyclic_buffer[lz_offs: lz_offs+lz_len]
        else:  # raw copy
            buffer += com["data"]
    return buffer


def common_start_len(lst1, lst2):
    """
    Count length of longest common match for the beginning of two iterators

    Parameters
    ----------
    lst1 : list
        First compared list.
    lst2 : list
        Second compared list.

    Returns
    -------
    count : Int
        Common start length.

    """
    count = 0
    for c1, c2 in zip(lst1, lst2):
        # maximum count (serializes in 10 bits)
        if c1 != c2 or count >= MAX_PLAIN_COUNT:
            break
        count += 1
    return count


def find_adapt_rle(lst):
    """
    Find all possible RLE candidates from the beginnin of given list

    Parameters
    ----------
    lst : list of 8-bit ints
        Input list to search from start.

    Returns
    ------
    list of CompressCandidates 
        Compression rle commands with compare tuples
    """

    def break_chunks(n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    candidates = []
    if not lst:
        return []
    for i in range(1, 31):  # test 31 lengths of chunks cases (5 bits minus one)
        orig = break_chunks(i)
        chunk = lst[:i]
        count = common_start_len(orig, repeat(chunk))
        # calculate compress stream gain for this rle:
        # 2 bytes for flag + chunk -> unpacks to chunk_len * count bytes
        plain_len = len(chunk)*count
        chunk_len = len(chunk)
        gain = plain_len - (2+chunk_len)
        # add match to rle_candidates list
        candidates.append(CompressCandidate(ComparePair(gain, plain_len), {
            "method": "rle", "len": count, "chunk": chunk}))
    return candidates


def get_list_hashes(lst):
    """
    For LZ to be more effective, than worst case 'fresh' raw dump,
    you need to lz encode minimum 4 bytes length. Break into 4 bytes chunks and hash

    Parameters
    ----------
    lst : list
        Input list to form hashes from (lz haystack).

    Returns
    -------
    enumerated list: (n, hash)
        list of enumerated hashes.

    """
    assert len(lst) > 0, 'Empty list in list hashes'
    return [(x, hash(tuple(lst[x:x + 4]))) for x in range(len(lst))]


def find_lz(lst, hashes, pos):
    """
    Find all possible LZ candidates, match starting from given position.

    Parameters
    ----------
    lst : list of ints
        Haystack. Plain buffer to search in.
    hashes : list of (n, hash)
        Hashes for 4-byte chunks for each position. Precalculated for full haystack
    pos : Int
        Search starting positon.

    Returns
    -------
    list of dicts
       Compression LZ commands with compare tuples

    """
    if not lst or pos >= min(len(lst), len(hashes)):
        return []  # position out of bounds or empty list
    needle_hash = hashes[pos][1]
    # indexes of probable matches.
    candidate_offsets = [i for i, val in hashes[:pos] if val == needle_hash]
    candidates = []
    needle = lst[pos:]

    for offs in candidate_offsets:
        plain_len = common_start_len(needle, lst[offs:])
        gain = plain_len - 4  # 4 bytes for flag,len,offset -> unpack to len bytes
        # add match to lz_candidates list
        candidates.append(CompressCandidate(ComparePair(gain, plain_len),  {
                          "method": "lz", "len": plain_len, "offs": offs}))
    return candidates


def encode(lst):
    """
    Encodes given plain data to list of best found compression commands.

    Parameters
    ----------
    lst : list of bytes
        Plain data.

    Returns
    -------
    list of dicts
       List of found compression commands.

    """
    def get_raw_gain(raws):
        return -1 if len(raws) <= 1 else 0

    pos = 0
    raws = []
    encoded = []
    # Found offset should be serialized in 16 bits
    haystack_hashes = get_list_hashes(lst[:MAX_OFFSET+1])

    with click.progressbar(length=len(lst),
                           label='Compressing file') as bar:

        while pos < len(lst):
            # compare first by gain, then by longest output length, then by earliest match
            # Return raw entry if no methods found on current or next position
            curRaws = raws + [lst[pos]]
            curRawEntry = CompressCandidate(ComparePair(gain=get_raw_gain(curRaws), plain_len=len(curRaws)),
                                            command={"method": "raw", "data": curRaws})
            curEntry = max([i for i in find_adapt_rle(lst[pos:]) + find_lz(lst, haystack_hashes, pos)
                            if i is not None], key=lambda cand: cand.cmp_pair,
                           default=curRawEntry)
            skipRaws = raws + lst[pos:pos+2]
            skipRawsEntry = CompressCandidate(ComparePair(gain=get_raw_gain(skipRaws), plain_len=len(skipRaws)), command={
                "method": "raw", "data": skipRaws})
            skipEntry = max([i for i in find_adapt_rle(lst[pos + 1:]) + find_lz(lst, haystack_hashes, pos + 1)
                             if i is not None], key=lambda cand: cand.cmp_pair,
                            default=skipRawsEntry)

            if curEntry.cmp_pair.gain > curRawEntry.cmp_pair.gain and curEntry.cmp_pair.gain >= curRawEntry.cmp_pair.gain + skipEntry.cmp_pair.gain:
                # current compress command is the best option:
                # time to dump accumulated raws and emit compress command
                if raws:
                    encoded.append({"method": "raw", "data": raws})
                encoded.append(curEntry.command)
                raws = []
                pos += curEntry.cmp_pair.plain_len  # add plain len
                bar.update(curEntry.cmp_pair.plain_len)
            else:  # no options better, than raw
                if len(curRaws) < MAX_RAW_LEN:  # raw length to be serialized in 7 bits
                    raws = curRaws
                else:  # time to dump accumulated raws, as counter exhausted
                    encoded.append(curRawEntry.command)
                    raws = []
                pos += 1
                bar.update(1)

    if raws:
        # dump rest of raws if any
        encoded.append({"method": "raw", "data": raws})

    return encoded


def serialize(commands):
    """
    Serializes list of commands down to bytes for further dump to binary file

    Parameters
    ----------
    commands : list of dicts
        Compression commands.

    Raises
    ------
    AssertionError
        If data is too big to fit in flag bytes, AssertionError is raised.   

    Returns
    -------
    buffer : list of ints
        Serialized compressed stream bytes.

    """
    buffer = []
    for com in commands:
        if com["method"] == "rle":
            chunk_size = len(com["chunk"])
            chunk_count = com["len"]
            assert chunk_size <= MAX_CHUNK_LEN and chunk_count <= MAX_PLAIN_COUNT, 'Rle flag overflow'
            rle_flag_hi = 0x80 | (
                (chunk_size - 1) & 0x1F) << 2 | ((chunk_count & 0x300) >> 8)
            rle_flag_lo = chunk_count & 0xFF
            buffer += [rle_flag_hi, rle_flag_lo] + com["chunk"]
        elif com["method"] == "lz":
            lz_len = com["len"]
            offs = com["offs"]
            assert lz_len <= MAX_PLAIN_COUNT and offs <= MAX_OFFSET, 'Lz flag overflow'
            lz_flag_hi = 0xFC | ((lz_len & 0x300) >> 8)
            lz_flag_lo = lz_len & 0xFF
            offs_lo = offs & 0xFF
            offs_hi = (offs >> 8) & 0xFF
            buffer += [lz_flag_hi, lz_flag_lo, offs_lo, offs_hi]
        else:  # raw copy
            raw_len = len(com["data"])
            assert raw_len < 0x80, 'Raw flag overflow'
            buffer += [raw_len & 0x7F] + com["data"]
    buffer += [0]
    return buffer


if __name__ == '__main__':
    cli()
