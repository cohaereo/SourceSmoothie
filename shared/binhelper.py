from struct import (unpack as up, pack as pa)
import lzma
import struct
import io
import functools, itertools
from collections import namedtuple
import contextlib

def unpack_named(data: bytes, packing: str, nt: namedtuple):
    return [nt._make(x) for x in struct.iter_unpack(packing, data)]

def unpack_iterative(data: bytes, packing: str):
    return [x for x in struct.iter_unpack(packing, data)]

def unpack_iterative_single(data: bytes, packing: str):
    return [x[0] for x in struct.iter_unpack(packing, data)]

def try_decompress(data: bytes):
    if(data[:4] == b'LZMA'):
        actual_size = up('I', data[4:8])[0]
        properties = up('5B', data[12:17])
        new_header = pa('<5BQ', *properties, actual_size)
        result = lzma.decompress(new_header + data[17:])
    else:
        result = data

    return result

class BinaryReader:
    def __init__(self, file):
        if(file == None):
            self.is_valid = False
        else:
            self.is_valid = True
        self.f = file

    def readt(self, packing: str):
        return up(packing, self.f.read(struct.calcsize(packing)))

    def read_named(self, size: int, packing: str, nt: namedtuple, decompress=False):
        data = try_decompress(self.f.read(size)) if decompress else self.f.read(size)
        return unpack_named(data, packing, nt)

    def read_iterative(self, size: int, packing: str, decompress=False):
        data = try_decompress(self.f.read(size)) if decompress else self.f.read(size)
        return unpack_iterative(data, packing)

    def read_iterative_single(self, size: int, packing: str, decompress=False):
        data = try_decompress(self.f.read(size)) if decompress else self.f.read(size)
        return [x[0] for x in struct.iter_unpack(packing, data)]

    def read(self, packing: str, size):
        return up(packing, self.f.read(size))[0]

    def read8(self):
        return self.read('B', 1)

    def read16(self):
        return self.read('H', 2)

    def read32(self):
        return self.read('I', 4)

    def read64(self):
        return self.read('Q', 8)

    def readFloat(self):
        return self.read('f', 4)
    
    def readVec2(self):
        return self.readt('ff')
    
    def readVec3(self):
        return self.readt('fff')

    @contextlib.contextmanager
    def save_pos(self):
        saved = self.f.tell()
        yield
        self.seek(saved, False)

    def readString(self, size=-1):
        if(size == -1):
            read_char = iter(functools.partial(self.f.read, 1), b'')
            # TODO: Fix this (?)
            return (b''.join(itertools.takewhile(b'\0'.__ne__, read_char))).decode('ascii')
        else:
            return self.f.read(size).decode('utf-8')

    def seek(self, offset, relative=True):
        self.f.seek(offset, 1 if relative else 0)
