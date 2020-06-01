import bpy
from bpy.props import (CollectionProperty, StringProperty)
import os
import sys
from pathlib import Path

from .shared import (vpk)
from .source1 import (bsp, vtf, vmt, mdl)

bl_info = {
    "name": "Import Source Engine BSP, MDL, VTF and VMT formats",
    "description": "Tools for importing assets from Source 1",
    "author": "Lucas 'cohaereo' Cohaereo",
    "blender": (2, 80, 0),
    "location": "File -> Import",
    "category": "Import-Export",
}

# TODO: Figure this out later
# class SourceSmoothiePreferencesVpkList(bpy.types.UIList):
#     def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
#         ob = data
#         slot = item
#         ma = slot.material
#         layout.label(text="/home/lucas/.steam/steam/steamapps/common/Team Fortress 2/tf/tf2_misc_dir.vpk", translate=False, icon='FILE')

class SourceSmoothiePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    # game_paths: CollectionProperty(name="VPK (game) paths", type=bpy.types.OperatorFileListElement)
    vpk_path: StringProperty(name="Search directory")

    def draw(self, context):
        layout = self.layout
        layout.label(text='Path to search for VPKs (restart required after changing):')
        row = layout.row()
        row.prop(self, 'vpk_path')

namespaces = {
    bsp,
    vtf,
    vmt,
    mdl,
}

def mount_vpks():
    paths = [str(x) for x in Path(bpy.context.preferences.addons[__name__].preferences.vpk_path).rglob("*_dir.vpk")]
    paths.reverse() # Hacky solution for TF2 textures
    for vi, v in enumerate(paths):
        print(f"\r[SourceSmoothie] Mounting VPKs {vi+1}/{len(paths)}", end='')
        vpk.mount(v)
    print("")

def register():
    for n in namespaces:
        n.register()

    bpy.utils.register_class(SourceSmoothiePreferences)

    mount_vpks()

def unregister():
    for n in namespaces:
        n.unregister()

    bpy.utils.unregister_class(SourceSmoothiePreferences)

if __name__ == "__main__":
    register()
