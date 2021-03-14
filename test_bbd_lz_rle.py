import io
import pytest
from bbd_lz_rle import find_adapt_rle, find_lz, get_list_hashes, encode, serialize, deserialize, decode


def get_max_candidate(candidates):
    """Helper function to get max candidate from list first comparing by gain,
    then by plain outcome length, not comparing compression commands themselves.
    Return extracted command from tuples
    """
    return max(candidates, key=lambda t: t[0], default=(None, None))[1]


def test_find_adapt_rle():
    candidates = find_adapt_rle([])
    assert get_max_candidate(candidates) == None
    candidates = find_adapt_rle([0])
    assert get_max_candidate(candidates) == {
        'method': 'rle', 'len': 1, 'chunk': [0]}
    candidates = find_adapt_rle([0]*5)
    assert get_max_candidate(candidates) == {
        'method': 'rle', 'len': 5, 'chunk': [0]}
    candidates = find_adapt_rle([0, 0, 0, 0, 0, 99])
    assert get_max_candidate(candidates) == {
        'method': 'rle', 'len': 5, 'chunk': [0]}
    candidates = find_adapt_rle([2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2])
    assert get_max_candidate(candidates) == {
        'method': 'rle', 'len': 2, 'chunk': [2, 2, 2, 1]}


def test_find_lz():
    lst = []
    with pytest.raises(AssertionError):
        candidates = find_lz(lst, get_list_hashes(lst), 0)
        candidates = find_lz(lst, get_list_hashes(lst), 1)

    lst = range(10)
    candidates = find_lz(lst, get_list_hashes(lst), 5)
    assert candidates == []
    lst = [99]*10
    candidates = find_lz(lst, get_list_hashes(lst), 0)
    assert candidates == []
    candidates = find_lz(lst, get_list_hashes(lst), 1)  # outbound lz copy case
    assert get_max_candidate(candidates) == {
        "method": "lz", "len": 9, "offs": 0}
    lst = [0, 1, 2, 3, 9, 6, 7, 6, 1, 2, 3, 8]  # match less than 4
    candidates = find_lz(lst, get_list_hashes(lst), 8)
    assert candidates == []
    candidates = find_lz(lst, get_list_hashes(lst), 11)  # last element search
    assert candidates == []
    lst = [7, 0, 1, 2, 3, 9, 6, 7, 0, 1, 2, 3, 8,
           6, 0, 1, 2, 3, 8]  # bigger match later
    candidates = find_lz(lst, get_list_hashes(lst), 14)
    assert get_max_candidate(candidates) == {
        "method": "lz", "len": 5, "offs": 8}


def test_decode():
    assert decode([{'method': 'raw', 'data': [00, 98, 99]}, {
                  'method': 'lz', 'len': 5, 'offs': 1}]) == [00, 98, 99, 98, 99, 98, 99, 98]  # off bound lz


def test_encode():
    with pytest.raises(AssertionError):
        assert encode([]) == []
    assert encode([99]) == [{'method': 'raw', 'data': [99]}]
    assert encode([1, 2, 3, 3, 3, 3]) == [{'method': 'raw', 'data': [1, 2]}, {
        'method': 'rle', 'len': 4, 'chunk': [3]}]
    # better not to emit zero gain LZ
    lst = [1, 2, 3, 4, 97, 98, 99, 1, 2, 3, 4]
    assert encode(lst) == [{'method': 'raw', 'data': [
        1, 2, 3, 4, 97, 98, 99, 1, 2, 3, 4]}]
    lst = [1, 2, 3, 4, 5, 6, 7, 81, 82, 9, 1, 2, 3, 4, 83, 84, 9, 1, 2, 3,
           4, 5, 6, 7]  # better add second 9 to the raws (non-greedy matching)
    assert encode(lst) == [{'method': 'raw',
                            'data': [1, 2, 3, 4, 5, 6, 7, 81, 82, 9, 1, 2, 3, 4, 83, 84, 9]},
                           {'method': 'lz', 'len': 7, 'offs': 0}]

    lst = [1, 2, 3, 4, 5, 99, 2, 3, 4, 5, 6,
           7, 98, 98, 98, 98, 1, 2, 3, 4, 5, 6, 7]
    # better not to skip first LZ: gain is equal to skip position:
    assert encode(lst) == [{'method': 'raw', 'data': [1, 2, 3, 4, 5, 99, 2, 3, 4, 5, 6, 7]},
                           {'method': 'rle', 'len': 4, 'chunk': [98]},
                           {'method': 'lz', 'len': 5, 'offs': 0},
                           {'method': 'raw', 'data': [6, 7]}]
    lst = [99, 1, 2, 3, 1, 2, 3, 1, 2, 98, 1, 2, 3, 1, 2, 3, 1, 2, 3]
    # last candidates have same gain: rle 3 3 or lz 8,
    # but rle has longer plain len, need to choose rle for greedy parsing
    assert encode(lst) == [{'method': 'raw', 'data': [99]},
                           {'method': 'rle', 'len': 2, 'chunk': [1, 2, 3]},
                           {'method': 'raw', 'data': [1, 2, 98]},
                           {'method': 'rle', 'len': 3, 'chunk': [1, 2, 3]}]


def test_deserialize():
    assert deserialize(io.BytesIO(b'\x81\x3c\x00\x00')) == [
        {'method': 'rle', 'len': 0x13c, 'chunk': [0]}]
    assert deserialize(io.BytesIO(b'\x9B\xFF\x00\x00\x00\x00\x00\x00\x00\x00')) == [
        {'method': 'rle', 'len': 1023, 'chunk': [0, 0, 0, 0, 0, 0, 0]}]
    assert deserialize(io.BytesIO(b'\xFE\x21\x67\x45\x00')) == [
        {'method': 'lz', 'len': 0x221, 'offs': 0x4567}]
    assert deserialize(io.BytesIO(b'\x03\x01\x02\x03\x00')) == [
        {'method': 'raw', 'data': [1, 2, 3]}]


def test_serialize():
    assert serialize([]) == [0]
    assert serialize([{'method': 'raw', 'data': [1, 2, 3]}]) == [3, 1, 2, 3, 0]
    with pytest.raises(AssertionError):
        serialize([{'method': 'raw', 'data': list(range(0x80))}])
    assert serialize([{"method": "lz", "len": 0x221, "offs": 0x4567}]) == [
        0xFE, 0x21, 0x67, 0x45, 0]
    with pytest.raises(AssertionError):
        assert serialize([{"method": "lz", "len": 0x456, "offs": 0x4567}])
    with pytest.raises(AssertionError):
        assert serialize([{"method": "lz", "len": 0x221, "offs": 0x12456}])
    assert serialize([{"method": "rle", "len": 0x321, "chunk": [1, 2, 3]}]) == [
        0x8B, 0x21, 1, 2, 3, 0]
    with pytest.raises(AssertionError):
        assert serialize(
            [{"method": "rle", "len": 0x456, "chunk": [1, 2, 3]}])
    with pytest.raises(AssertionError):
        assert serialize(
            [{"method": "rle", "len": 0x321, "chunk": list(range(0x20))}])
