# TODO:
# This mess is only temporary. This system needs to be heavily optimised and moved around
# VPKs are supposed, like a few other files (including BSP and ZIP), to be derived from a `Mountable` class which implements the necessary features that are currently defined in Vpk

from .binhelper import BinaryReader
import io
import os
from sys import argv
import time
from .mountable import Mountable
import zipfile

class VpkFile(io.IOBase):
    def __init__(self, vpk_path, offset, size):
        self.file = open(vpk_path, 'rb')
        self.offset = offset
        self.size = size
        self.pos = 0

        self.file.seek(offset)

    def read(self, size=-1):
        if(size == -1):
            size = self.size-self.pos
            self.file.seek(self.offset+self.pos)
            self.pos += size
            return self.file.read(size)
        else:
            self.file.seek(self.offset+self.pos)
            self.pos += size
            return self.file.read(size)
    
    def seek(self, offset, whence=0):
        if(whence == 0):
            self.pos = offset
        elif(whence == 1):
            self.pos += offset
        elif(whence == 2):
            self.pos = self.size - offset
    
    def tell(self):
        return self.pos


# Split a path into the path and file extension
def split_path(path):
    return (path[:path.rfind('.')], path[path.rfind('.')+1:])


class ZipWrapper(Mountable):
    def __init__(self, path):
        self.file = zipfile.ZipFile(path)
        self.path = path

        self.fetch_filelist()
    
    def fetch_filelist(self):
        self.filelist = {}
        for p in self.file.namelist():
            path, ext = split_path(p)
            if(self.filelist.get(ext)):
                self.filelist[ext] += path
            else:
                self.filelist[ext] = [path]
    
    def open_file(self, path):
        path_noext, path_ext = split_path(path)
        if(self.filelist.get(path_ext)):
            for n in self.file.namelist():
                if(n.lower() == path.lower()):
                    try:
                        f = self.file.open(n)

                        # Make sure the file is readable
                        # Python's zipfile is really strict when it comes to CRCs
                        f.read(1)
                        f.seek(0)

                        return f
                    except:
                        return None

        return None

    def has_file(self, path):
        path_noext, path_ext = split_path(path)
        try:
            if(self.filelist.get(path_ext)):
                for f in self.filelist[path_ext]:
                    if(f.lower() == path_noext.lower()):
                        return True
        except:
            return False

        return False


class Vpk(Mountable):
    def __init__(self, path):
        self.file = BinaryReader(open(path, 'rb'))
        self.path_template = path.replace("dir", "%03d")

        sig = self.file.read32()
        version = self.file.read32()

        if(sig != 0x55aa1234):
            raise Exception("Invalid VPK file (signature doesn't match)")

        if(version not in [1, 2]):
            raise Exception(f"Invalid/unknown VPK version {version}")
    
        self.dirtree_size = self.file.read32()
        self.dirtree_offset = [12, 28][version-1]
        
        self.fetch_filelist()
    
    def open_file(self, path):
        path_noext = path[:path.rfind('.')].lower()
        path_ext = path[path.rfind('.')+1:].lower()


        if(self.filelist.get(path_ext)):
            if(self.filelist[path_ext].get(path_noext)):
                f = self.filelist[path_ext][path_noext]
                if(f[0] == 0x7fff):
                    # Not supported right now
                    return None
                    # return VpkFile(self.path, f[5], f[4])
                else:
                    return VpkFile(self.path_template % f[0], f[1], f[2])

                return True
        # if(self.filelist.get(path_ext)):
        #     for f in self.filelist[path_ext]:
        #         if(f[0].lower() == path_noext):
        #             if(f[1] == 0x7fff):
        #                 # Not supported right now
        #                 return None
        #                 # return VpkFile(self.path, f[5], f[4])
        #             else:
        #                 return VpkFile(self.path_template % f[1], f[2], f[3])

        return None

    def has_file(self, path):
        path_noext = path[:path.rfind('.')].lower()
        path_ext = path[path.rfind('.')+1:].lower()
        if(self.filelist.get(path_ext)):
            if(self.filelist[path_ext].get(path_noext)):
                return True
            # for f in self.filelist[path_ext]:
            #     if(f[0].lower() == path_noext):
            #         return True

        return False

    def fetch_filelist(self):
        if(self.dirtree_offset <= 0):
            raise Exception("Directory tree offset is zero")

        self.filelist = {}
        self.file.seek(self.dirtree_offset, False)
        temp_data = self.file.f.read(self.dirtree_size)
        br = BinaryReader(io.BytesIO(temp_data))

        files = 0
        start_time = time.time_ns()
        while True:
            extension = br.readString()
            if(extension == ""):
                break

            # paths = []
            paths = {}
            while True:
                path = br.readString()
                if(path == ""):
                    break

                while True:
                    filename = br.readString()
                    if(filename == ""):
                        break

                    # paths.append(os.path.join(path, filename))
                    header = br.readt("IHHIIH")
                    crc = header[0]
                    preload_bytes = header[1]
                    archive_index = header[2]
                    entry_offset = header[3]
                    entry_size = header[4]
                    terminator = header[5]
                    p = f"{path}/{filename}"
                    paths[p] = (archive_index, entry_offset, entry_size)
                    files += 1

                    br.seek(preload_bytes)
                    # print(f"\rFound {files} files", end='')

                    # print(f"{p} | {archive_index}")

            # TODO: Check for double entries and prevent original entries from being overwritten
            if(self.filelist.get(extension)):
                self.filelist[extension] += paths
            else:
                self.filelist[extension] = paths
        # print(f" in {(time.time_ns()-start_time) / 1e+6}ms")
        # print(f"found {files} files in {(time.time_ns()-start_time) / 1e+6}ms")

mounted_archives = {}

def open_archive(path):
    ext = path[-3:]
    if(ext == "vpk"):
        return Vpk(path)
    elif(ext == "zip"):
        return ZipWrapper(path)
    else:
        raise Exception(f"Unsupported archive format '{ext}'")

def mount(path):
    if(mounted_archives.get(path)):
        del mounted_archives[path]

    arc = open_archive(path)
    mounted_archives[path] = arc

def open_from_mounted(path):
    fixed_path = path.replace('\\', '/').strip('\0\r\n\t')
    for p, v in mounted_archives.items():
        f = v.open_file(fixed_path)
        if(f):
            return f
    
    return None

# to_mount = [
#    "/home/lucas/.steam/steam/steamapps/common/Team Fortress 2/tf/tf2_textures_dir.vpk",
#    "/home/lucas/.steam/steam/steamapps/common/Team Fortress 2/tf/tf2_misc_dir.vpk",
#    "/home/lucas/.steam/steam/steamapps/common/Team Fortress 2/platform/platform_misc_dir.vpk",
#    "/home/lucas/.steam/steam/steamapps/common/Team Fortress 2/hl2/hl2_textures_dir.vpk"
# ]

# mounted = []

# if(len(argv) < 2):
#     print("hell, you know how this works.")
#     exit(1)

# for mp in to_mount:
#     print(f"Mounting VPK {mp[mp.rfind('/'):]}")
#     mounted.append(Vpk(mp))

# path_noext = argv[1][:argv[1].rfind('.')].lower()
# path_ext = argv[1][argv[1].rfind('.')+1:].lower()
# for v in mounted:
#     f = v.open_file(argv[1])
#     if(f):
#         open(f"tmp.{path_ext}", 'wb').write(f.read())
#         exit(0)

# print(f"File '{argv[1]}' not found ({path_noext}, {path_ext})")