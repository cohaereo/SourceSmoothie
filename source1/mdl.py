import os
import bmesh
import bpy
import numpy as np
from math import sqrt, radians
from collections import namedtuple

from .mdl_data import (MdlData, HU_SCALE_FACTOR)
from bpy.props import (StringProperty, BoolProperty)
from bpy_extras.io_utils import (ImportHelper)
from .vmt import (load_vmt, createNoneMaterial, createNoneTexture)
from ..shared.binhelper import (BinaryReader)
from ..shared import vpk
from ..shared.utils import *


def create_obj(name):
    mesh_data = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh_data)
    
    return obj


def load_mdl(mdl: BinaryReader, vvd: BinaryReader, vtx: BinaryReader, downscale):
    data = MdlData(mdl, vvd, vtx, downscale)
    if(not data.read()):
        return None

    bm = bmesh.new()
    ob = create_obj(data.mdldata.name)
    
    for bodypart in data.vtxdata.bodyparts:
        for model in bodypart:
            for mesh in model[0]: # lod zero (model is the lod array (which needs to be fixed (just like all the other structures in this loop)))
                for stripgroup in mesh:
                    for index in range(0, len(stripgroup.indices), 3):
                        try:
                            face = []
                            face_uv = []

                            for i in [0, 2, 1]:
                                vertex_index = stripgroup.vertices[stripgroup.indices[index + i]].original_vertex
                                vert = bm.verts.new(data.vvddata.vertices[vertex_index].position)
                                vert.normal = data.vvddata.vertices[vertex_index].normal
                                face.append(vert)
                                face_uv.append(data.vvddata.vertices[vertex_index].texcoord)

                            f = bm.faces.new(face)
                            f.smooth = True

                            if(f != 0):
                                uv_layer = bm.loops.layers.uv.verify()
                                bm.faces.ensure_lookup_table()

                                face = bm.faces[-1]
                                for li, loopElement in enumerate(face.loops):
                                    luvLayer = loopElement[uv_layer]
                                    vertex = loopElement.vert.co

                                    try:
                                        uv = face_uv[li]
                                        luvLayer.uv[0] =  uv[0]
                                        luvLayer.uv[1] = -uv[1] + 1.0
                                    except Exception as e:
                                        pass
                        except Exception as e:
                            print(e)
                            pass
    
    if(downscale):
        ob.scale *= HU_SCALE_FACTOR

    bm.to_mesh(ob.data)
    bm.free()
    bpy.context.collection.objects.link(ob)

    return ob
    

class MdlLoader(bpy.types.Operator, ImportHelper):
    """Import MDL model files from the Source engine"""
    bl_idname = "sourcesmoothie.source1_mdl"
    bl_description = "Import Source 1 MDL model files"
    bl_label = "Import Source 1 MDL"

    filename_ext = ".mdl"
    filter_glob: StringProperty(
        default="*.mdl",
        options={'HIDDEN'},
    )

    filepath: StringProperty(subtype="FILE_PATH")
    # import_materials: BoolProperty(name="Import materials", default=True)
    downscale: BoolProperty(name="Rescale model (recommended)", default=True)

    def execute(self, context):
        self.mdl_file = BinaryReader(open(self.filepath, 'rb'))
        self.vvd_file = BinaryReader(open(self.filepath[:-3] + "vvd", 'rb'))
        self.vtx_file = BinaryReader(open(self.filepath[:-3] + "dx90.vtx", 'rb'))
        if(not self.load()):
            return {'CANCELLED'}

        return {'FINISHED'}

    def load(self):
        self.sb = start_bench("Load MDL")
        r = load_mdl(self.mdl_file, self.vvd_file, self.vtx_file, self.downscale)
        end_bench(self.sb)
        return r != None


def menu_import(self, context):
    self.layout.operator(MdlLoader.bl_idname, text='Source 1 MDL (.mdl)')


def register():
    bpy.utils.register_class(MdlLoader)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.utils.unregister_class(MdlLoader)
