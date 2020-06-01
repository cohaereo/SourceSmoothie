import numpy as np
import bpy
import io

from bpy.props import (StringProperty, BoolProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper)
from .libs.vtflib_wrapper import VtfLib

vtflib = VtfLib()

def load_vtf(file, name):
    open("tmp.vtf", 'wb').write(file.read()) # TODO: Decode image data from memory instead of doing this
    res = vtflib.load_image("tmp.vtf")
    
    if(res == False):
        raise Exception(f"Failed to load VTF file: {vtflib.get_last_error()}")

    data = vtflib.convert_to_rgba8888()
    data = vtflib.flip_image(data)
    pixels = np.array(data.contents, np.uint8).astype(np.float, copy=False)

    fixed_pixels = np.divide(pixels, 255)[:vtflib.width() * vtflib.height() * 4]

    image = bpy.data.images.new(
        name,
        width=vtflib.width(),
        height=vtflib.height()
    )

    image.pixels[:] = fixed_pixels.tolist()
    image.pack()

    vtflib.destroy_image()

    return image


# For compatibility, needs to be removed
def load_vtf2(file, name):
    return load_vtf(file, name)


class VtfLoader(bpy.types.Operator, ImportHelper):
    """Import VTF texture files from the Source engine"""
    bl_idname = "sourcesmoothie.source1_vtf"
    bl_description = "Import Source 1 VTF texture files"
    bl_label = "Import Source 1 VTF"

    filename_ext = ".vtf"
    filter_glob: StringProperty(
        default="*.vtf",
        options={'HIDDEN'},
    )

    filepath: StringProperty(subtype="FILE_PATH")
    quality: EnumProperty(
        name="Texture quality",
        items=(
            ("100", "Maximum", ""),
            ("75",  "High", ""),
            ("50",  "Medium", ""),
            ("25",  "Low", ""),
        ),
    )


    def execute(self, context):
        self.file = open(self.filepath, 'rb')

        if(not self.load()):
            return {'CANCELLED'}

        return {'FINISHED'}
    

    def load(self):
        # image = load_vtf(self.file, "tex_" + bpy.path.display_name_from_filepath(self.filepath), quality=int(self.quality))
        image = load_vtf2(self.file, "tex_" + bpy.path.display_name_from_filepath(self.filepath))
        return True if image != None else False


def menu_import(self, context):
    self.layout.operator(VtfLoader.bl_idname, text='Source 1 VTF (.vtf)')


def register():
    bpy.utils.register_class(VtfLoader)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.utils.unregister_class(VtfLoader)
