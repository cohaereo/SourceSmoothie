import os
import platform
from ctypes import *

def ptr_to_array(ptr, size, type=c_ubyte):
    return cast(ptr, POINTER(type * size))

if platform.system() == "Windows":
    vtf_lib_name = "VTFLib.x64.dll"
elif platform.system() == "Linux":
    vtf_lib_name = "libVTFLib13.so"
else:
    raise NotImplementedError()

class VtfLib:
    dll = cdll.LoadLibrary(os.path.join(os.path.dirname(__file__), vtf_lib_name))

    lib_Initialize = dll.vlInitialize
    lib_Initialize.restype = c_bool

    lib_ImageLoad = dll.vlImageLoad
    lib_ImageLoad.argtypes = [c_char_p, c_bool]
    lib_ImageLoad.restype = c_bool

    lib_CreateImage = dll.vlCreateImage
    lib_CreateImage.argtypes = [POINTER(c_int)]
    lib_CreateImage.restype = c_bool

    lib_BindImage = dll.vlBindImage
    lib_BindImage.argtypes = [c_int32]
    lib_BindImage.restype = c_bool

    lib_ImageIsLoaded = dll.vlImageIsLoaded
    lib_ImageIsLoaded.restype = c_bool

    lib_ImageConvertToRGBA8888 = dll.vlImageConvertToRGBA8888
    lib_ImageConvertToRGBA8888.argtypes = [
        POINTER(c_byte),
        POINTER(c_byte),
        c_uint32,
        c_int32,
        c_uint32]
    lib_ImageConvertToRGBA8888.restype = None

    lib_ImageGetWidth = dll.vlImageGetWidth
    lib_ImageGetWidth.restype = c_int32

    lib_ImageGetHeight = dll.vlImageGetHeight
    lib_ImageGetHeight.restype = c_int32

    lib_ImageGetDepth = dll.vlImageGetDepth
    lib_ImageGetDepth.restype = c_int32

    lib_ImageGetFrameCount = dll.vlImageGetFrameCount
    lib_ImageGetFrameCount.restype = c_int32

    lib_ImageGetFormat = dll.vlImageGetFormat
    lib_ImageGetFormat.restype = c_uint32

    lib_ImageGetMipmapCount = dll.vlImageGetMipmapCount
    lib_ImageGetMipmapCount.restype = c_int32

    lib_ImageGetData = dll.vlImageGetData
    lib_ImageGetData.argtypes = [c_uint32, c_uint32, c_uint32, c_uint32]
    lib_ImageGetData.restype = POINTER(c_byte)

    lib_ImageComputeSize = dll.vlImageComputeImageSize
    lib_ImageComputeSize.argtypes = [c_int32, c_uint32, c_int32, c_uint32, c_int32]
    lib_ImageComputeSize.restype = c_uint32

    lib_GetLastError = dll.vlGetLastError
    lib_GetLastError.restype = c_char_p

    lib_ImageDestroy = dll.vlImageDestroy
    lib_ImageDestroy.restype = None

    lib_ImageFlipImage = dll.vlImageFlipImage
    lib_ImageFlipImage.argtypes = [POINTER(c_byte), c_uint32, c_int32]
    lib_ImageFlipImage.restype = None

    def destroy_image(self):
        self.lib_ImageDestroy()

    def get_last_error(self):
        error = self.lib_GetLastError().decode('utf-8', "replace")
        return error if error else ""

    def compute_image_size(self, width, height, depth, mipmaps, image_format):
        return self.lib_ImageComputeSize(width, height, depth, mipmaps, image_format)

    def get_image_data(self, frame=0, face=0, slice=0, mipmap_level=0):
        size = self.compute_image_size(self.width(), self.height(), self.depth(), self.mipmap_count(), self.image_format().value)
        buff = self.lib_ImageGetData(frame, face, slice, mipmap_level)
        return ptr_to_array(buff, size, c_ubyte)

    def mipmap_count(self):
        return self.lib_ImageGetMipmapCount()

    def image_format(self):
        return self.lib_ImageGetFormat()
        
    def width(self):
        return self.lib_ImageGetWidth()

    def height(self):
        return self.lib_ImageGetHeight()

    def depth(self):
        return self.lib_ImageGetDepth()

    def initialize(self):
        self.lib_Initialize()

    def bind_image(self, image):
        self.lib_BindImage(image)

    def create_image(self, image):
        self.lib_CreateImage(image)
    
    def load_image(self, path, header_only=False):
        return self.lib_ImageLoad(create_string_buffer(path.encode('ascii')), header_only)

    def image_is_loaded(self):
        return self.lib_ImageIsLoaded()

    def convert_to_rgba8888(self):
        new_size = self.compute_image_size(self.width(), self.height(), self.depth(), self.mipmap_count(), 0)
        new_buffer = cast(create_string_buffer(init=new_size), POINTER(c_byte))
        if(not self.lib_ImageConvertToRGBA8888(self.lib_ImageGetData(0, 0, 0, 0), new_buffer, self.width(), self.height(), self.image_format())):
            return ptr_to_array(new_buffer, new_size, c_ubyte)
        else:
            return 0

    def flip_image(self, image_data, width=None, height=None):
        width = width or self.width()
        height = height or self.height()
        image_data_p = cast(image_data, POINTER(c_byte))
        self.lib_ImageFlipImage(image_data_p, width, height)
        size = width * height * 4

        return ptr_to_array(image_data, size)

    def __init__(self):
        self.initialize()
        self.image_buffer = c_int()
        self.create_image(byref(self.image_buffer))
        self.bind_image(self.image_buffer)