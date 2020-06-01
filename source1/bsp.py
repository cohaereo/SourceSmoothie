import bmesh
import zipfile
import bpy
import time
import numpy as np
from math import sqrt, radians
from io import BytesIO
import sys
import traceback
from collections import namedtuple

from .bsp_data import (BspData, HU_SCALE_FACTOR)
from bpy.props import (StringProperty, BoolProperty)
from bpy_extras.io_utils import (ImportHelper)
from .vmt import (load_vmt, createNoneMaterial, createNoneTexture)
from .mdl import (load_mdl)
from ..shared.binhelper import (BinaryReader, try_decompress)
from ..shared import vpk
from ..shared.utils import *

BspLump = namedtuple("BspLump", "offset size version uncompressed_size")
BspModel = namedtuple("BspModel", "min_x min_y min_z max_x max_y max_z origin_x origin_y origin_z head_node first_face face_count")
BspTexData = namedtuple("BspTexData", "reflectivity_r reflectivity_g reflectivity_b name_table_id width height vwidth vheight")
BspDisplacementInfo = namedtuple("BspDisplacementInfo", "start_x start_y start_z disp_vert_start disp_tri_start power min_tess smoothing_angle contents map_face lm_alpha_statr lm_sample_start u0 u1 u2 u3 u4 u5 u6 u7 u8 u9 u10 u11 u12 u13 u14 u15")
BspDisplacementVert = namedtuple("BspDisplacementVert", "vx vy vz dist alpha")
BspTexInfo = namedtuple("BspTexInfo", """
    uv0_0 uv0_1 uv0_2 uv0_3 
    uv1_0 uv1_1 uv1_2 uv1_3

    luv0_0 luv0_1 luv0_2 luv0_3 
    luv1_0 luv1_1 luv1_2 luv1_3

    flags
    texdata
""")
BspFace = namedtuple("BspFace", """
    planenum
    side
    on_node
    first_edge
    edge_count
    texinfo
    dispinfo
    surface_fog_volume_id
    style0 style1 style2 style3
    lightmap_offset area
    lightmap_min_x
    lightmap_min_y
    lightmap_size_x
    lightmap_size_y
    orig_face
    num_prims
    first_prim
    smoothing_groups
""")
##

def parse_entities(entitydata: str):
    entities = []
    lines = entitydata.splitlines()

    for i in range(len(lines)):
        if(lines[i].startswith('{')):
            i += 1
            entity = {}
            while i < len(lines) and not lines[i].startswith('}'):
                kv = [s for s in lines[i].split('"') if s != '' and s != ' ']
                if(len(kv) == 2):
                    entity[kv[0]] = kv[1]
                i += 1

            if('classname' in entity and 'origin' in entity):
                entities.append(entity)
    
    return entities


def angles_to_radians(angles):
    return [radians(x) for x in angles]


def parse_rgba(s: str, default=[1, 1, 1, 1]):
    split = s.split(' ')
    r = default
    if(len(split) == 4):
        try:
            return [float(x) / 255 for x in split]
        except:
            return default
    else:
        return default


def parse_vector(s: str, default=[0,0,0], downscale=False):
    split = s.split(' ')
    if(len(split) == 3):
        try:
            if(downscale):
                return [float(x) * HU_SCALE_FACTOR for x in split]
            else:
                return [float(x) for x in split]
        except:
            pass
    else:
        return default


def calculate_uv(ti: BspTexInfo, td: BspTexData, vertex):
    tu = (ti.uv0_0, ti.uv0_1, ti.uv0_2, ti.uv0_3)
    tv = (ti.uv1_0, ti.uv1_1, ti.uv1_2, ti.uv1_3)

    return (
        (tu[0] * vertex[0] + tu[1] * vertex[1] + tu[2] * vertex[2] + tu[3]) / td.width,
       -(tv[0] * vertex[0] + tv[1] * vertex[1] + tv[2] * vertex[2] + tv[3]) / td.height
    )


def createEmptyTexture():
    image = bpy.data.images.new(
        "NOTEXTURE",
        width=1,
        height=1
    )

    pixels = [
        1.0, 1.0, 1.0, 1.0,
    ]

    image.pixels = pixels
    image.pack()

    return image


def createEmptyMaterial(name, diffuse_colour=[1.0, 1.0, 1.0]):
    m = bpy.data.materials.new(name)
    m.use_backface_culling = True
    m.use_nodes = True
    m.diffuse_color = diffuse_colour
    node_tree = m.node_tree
    node_principled = node_tree.nodes["Principled BSDF"]
    node_output = node_tree.nodes["Material Output"]

    node_tree.links.new(node_principled.outputs[0], node_output.inputs[0])
    return m


def parse_gamelump(data: bytes):
    br = BinaryReader(BytesIO(data))
    lump_count = br.read32()
    return br.read_iterative(lump_count * 16, 'IHHII')


def parse_static_props(data: bytes, lump_version):
    br = BinaryReader(BytesIO(data))
    name_entries = br.read32()
    model_names = []

    for i in range(name_entries):
        model_names.append(br.readString(128))

    leaf_entries = br.read32()
    br.seek(leaf_entries * 2) # Skip these, as we won't be using them

    model_count = br.read32()
    models = []
    model_struct_size = (len(data) - br.f.tell()) // model_count
    for i in range(model_count):
        origin = br.readVec3()
        angles = br.readVec3()

        name_index = br.read16()

        br.seek(model_struct_size - 26)
        models.append((model_names[name_index], origin, angles))
    
    return models


def create_obj(name):
    mesh_data = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh_data)
    
    return obj


class BspLoader(bpy.types.Operator, ImportHelper):
    """Import BSP map files from the Source engine"""
    bl_idname = "sourcesmoothie.source1_bsp"
    bl_description = "Import Source 1 BSP map files"
    bl_label = "Import Source 1 BSP"

    filename_ext = ".bsp"
    filter_glob: StringProperty(
        default="*.bsp",
        options={'HIDDEN'},
    )

    filepath: StringProperty(subtype="FILE_PATH")
    import_materials: BoolProperty(name="Import materials", default=True)
    # import_props: BoolProperty(name="Import props", default=True) 
    downscale: BoolProperty(name="Rescale map (recommended)", default=True)
    lock_objects: BoolProperty(name="Make objects unselectable", default=False)


    def execute(self, context):
        self.file = BinaryReader(open(self.filepath, 'rb'))
        if(not self.load()):
            return {'CANCELLED'}

        return {'FINISHED'}


    def load(self):
        self.sb = start_bench("Load BSP")
        b = start_bench("Read data")
        self.data = BspData(self.file, self.downscale)
        if(not self.data.read()):
            return False
        end_bench(b)

        self.collection = bpy.data.collections.new(bpy.path.display_name_from_filepath(self.filepath))
        bpy.context.scene.collection.children.link(self.collection)

        return self.build_mesh()


    def build_mesh(self):
        b = start_bench("Build mesh")

        current_texture_index = 0
        global_material_cache = {}
        for mi, m in enumerate(self.data.models):
            if(mi != 0 and mi not in self.data.model_origins):
                continue
            bm = bmesh.new()
            if(mi == 0):
                ob = create_obj(f"worldspawn")
            else:
                ob = create_obj(f"model ({mi})")

            update_bench(b, f"{mi+1}/{len(self.data.models)}")
            material_cache = {}
            for f in self.data.faces[m.first_face : m.first_face+m.face_count]:
                ti = self.data.texinfo[f.texinfo]
                td = self.data.texdata[ti.texdata]
                if(ti.flags & 0x2c0):
                    continue

                # TODO: Copied from quake 3 bsp loader, needs to be rewritten and moved to it's own task (benchmark)
                material_id = -1
                if self.import_materials:
                    texture_name_offset = self.data.texstrtable[td.name_table_id]
                    material_path = self.data.texstrdata[texture_name_offset:self.data.texstrdata.index(b'\0', texture_name_offset)].decode('ascii')
                    if(ti.texdata in material_cache):
                        material_id = material_cache[ti.texdata][1]
                    elif(ti.texdata in global_material_cache):
                        ob.data.materials.append(global_material_cache[ti.texdata])
                        material_id = len(ob.data.materials) - 1
                        material_cache[ti.texdata] = (global_material_cache[ti.texdata], material_id)
                    else:
                        # TODO: Fix the progress indicator
                        update_bench(b, f"{mi+1}/{len(self.data.models)}, texture {current_texture_index}/{len(self.data.texdata)}")
                        material_path_withext = material_path if material_path[-4:].lower() == '.vmt' else material_path + ".vmt"
                        material_file = vpk.open_from_mounted("materials/" + material_path_withext)
                    
                        if(material_file):
                            imported_material = load_vmt(material_file, material_path, [td.reflectivity_r, td.reflectivity_g, td.reflectivity_b, 1.0])
                            ob.data.materials.append(imported_material)
                            material_id = len(ob.data.materials) - 1
                            global_material_cache[ti.texdata] = imported_material
                            material_cache[ti.texdata] = (imported_material, material_id)
                            current_texture_index += 1
                        else:
                            print(f"Failed to open material file '{material_path_withext}'")
                            global_material_cache[ti.texdata] = None
                            material_cache[ti.texdata] = (None, -1)
                            current_texture_index += 1

                if(f.dispinfo != -1):
                    di = self.data.displacementinfo[f.dispinfo]
                    low_base = (di.start_x, di.start_y, di.start_z)
                    if(f.edge_count != 4):
                        print(f"Bad displacement (face #{i})")
                        continue

                    corner_verts = list()
                    corner_indices = list()
                    base_dist = np.inf
                    base_index = -1
                    for k in range(4):
                        ei = self.data.surfedges[f.first_edge+k]
                        vi = self.data.edges[-ei if ei < 0 else ei][1 if ei < 0 else 0]

                        corner_verts.append(self.data.vertices[vi])
                        corner_indices.append(vi)
                        this_dist = abs(corner_verts[k][0] - low_base[0]) + abs(corner_verts[k][1] - low_base[1]) + abs(corner_verts[k][2] - low_base[2])
                        if(this_dist < base_dist):
                            base_dist = this_dist
                            base_index = k
                    
                    if(base_index == -1):
                        print(f"Bad base in displacement #{i}")
                        continue

                    high_base = corner_verts[(base_index+3) % 4]
                    high_ray = np.subtract(corner_verts[(base_index+2) % 4], high_base)
                    low_ray = np.subtract(corner_verts[(base_index+1) % 4], low_base)

                    verts_wide = (2 << (di.power - 1)) + 1
                    base_verts = []
                    base_dispvert_index = di.disp_vert_start
                    if(base_dispvert_index < 0):
                        base_dispvert_index = abs(base_dispvert_index)
                    
                    for y in range(verts_wide):
                        fy = y / (verts_wide-1)
                        mid_base = np.add(low_base, np.multiply(low_ray, fy))
                        mid_ray = np.subtract(np.add(high_base, np.multiply(high_ray, fy)), mid_base)

                        for x in range(verts_wide):
                            fx = x / (verts_wide - 1)
                            i = x + y * verts_wide
                            
                            dv = self.data.displacement_verts[base_dispvert_index+i]
                            offset = (dv.vx, dv.vy, dv.vz)
                            scale = dv.dist

                            base_verts.append(np.add(np.add(mid_base, np.multiply(mid_ray, fx)), np.multiply(offset, scale)))


                    for y in range(verts_wide-1):
                        for x in range(verts_wide-1):
                            i = x + y * verts_wide

                            face = [
                                bm.verts.new(base_verts[i]),
                                bm.verts.new(base_verts[i+1]),
                                bm.verts.new(base_verts[i+verts_wide+1]),
                                bm.verts.new(base_verts[i+verts_wide])
                            ]

                            bface = 0
                            try:
                                bface = bm.faces.new(face)
                            except Exception as e:
                                # Skip duplicates (why is bmesh so rude..)
                                continue
                
                            if(bface != 0):
                                uv_layer = bm.loops.layers.uv.verify()
                                bm.faces.ensure_lookup_table()

                                face = bm.faces[-1]
                                for loopElement in face.loops:
                                    luvLayer = loopElement[uv_layer]
                                    vertex = loopElement.vert.co

                                    tu = (ti.uv0_0, ti.uv0_1, ti.uv0_2, ti.uv0_3)
                                    tv = (ti.uv1_0, ti.uv1_1, ti.uv1_2, ti.uv1_3)
                                    try:
                                        luvLayer.uv[0] =  (vertex.dot(tu) + ti.uv0_3) / td.width
                                        luvLayer.uv[1] = -(vertex.dot(tv) + ti.uv1_3) / td.height
                                    except Exception as e:
                                        pass

                                if(material_id >= 0):
                                    face.material_index = material_id
                else:
                    face = []
                    for ei in range(f.edge_count):
                        surfedge = self.data.surfedges[f.first_edge + ei]
                        vi = self.data.edges[abs(surfedge)][1 if surfedge < 0 else 0]
                        # face.append(bm.verts[vi])
                        face.append(bm.verts.new(self.data.vertices[vi]))

                    face.reverse()
                    bface = 0
                    try:
                        bface = bm.faces.new(face)
                    except:
                        # Skip duplicates (why is bmesh so rude..)
                        continue

                
                    if(bface != 0):
                        uv_layer = bm.loops.layers.uv.verify()
                        bm.faces.ensure_lookup_table()

                        face = bm.faces[-1]
                        for loopElement in face.loops:
                            luvLayer = loopElement[uv_layer]
                            vertex = loopElement.vert.co

                            tu = (ti.uv0_0, ti.uv0_1, ti.uv0_2, ti.uv0_3)
                            tv = (ti.uv1_0, ti.uv1_1, ti.uv1_2, ti.uv1_3)
                            try:
                                luvLayer.uv[0] =  (vertex.dot(tu) + ti.uv0_3) / td.width
                                luvLayer.uv[1] = -(vertex.dot(tv) + ti.uv1_3) / td.height
                            except Exception as e:
                                pass

                        if(material_id >= 0):
                            face.material_index = material_id
            
            if(mi != 0):
                origin = self.data.model_origins[mi]
                ob.location = origin[0]
                ob.rotation_euler = angles_to_radians((origin[1][2], origin[1][0], origin[1][1]))

            if(self.downscale):
                ob.scale *= HU_SCALE_FACTOR
            
            if(self.lock_objects):
                ob.hide_select = True

            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001) # Distance value might need some tweaking

            bm.to_mesh(ob.data)
            bm.free()
            self.collection.objects.link(ob)

        end_bench(b)

        end_bench(self.sb)
        
        return True


class BspLoaderOld(bpy.types.Operator, ImportHelper):
    """Import BSP map files from the Source engine"""
    bl_idname = "sourcesmoothie.source1_bsp_old"
    bl_description = "Import Source 1 BSP map files (old importer)"
    bl_label = "Import Source 1 BSP (DEPRECATED IMPORTER)"

    filename_ext = ".bsp"
    filter_glob: StringProperty(
        default="*.bsp",
        options={'HIDDEN'},
    )

    filepath: StringProperty(subtype="FILE_PATH")
    import_textures: BoolProperty(name="Import textures", default=True)
    import_props: BoolProperty(name="Import props", default=True) 
    downscale: BoolProperty(name="Rescale map (recommended)", default=True)

    def execute(self, context):
        self.file = BinaryReader(open(self.filepath, 'rb'))
        if(not self.load()):
            return {'CANCELLED'}

        return {'FINISHED'}


    def load(self):
        signature = self.file.readString(4)
        if(signature != 'VBSP'):
            raise Exception("Invalid BSP file (signature doesn't match)")

        self.version = self.file.read32()

        sb = start_bench("Load BSP")
        self.lumps = self.file.read_named(16 * 64, '4I', BspLump, decompress=True)

        b = start_bench("Read entities")
        self.file.seek(self.lumps[0].offset, False)
        entitydata = try_decompress(self.file.f.read(self.lumps[0].size)).decode('ascii')
        open("entities.kv", 'w').write(entitydata)
        entities = parse_entities(entitydata)
        entity_origins = {}
        for e in entities:
            if(e.get('model') and e['model'][0] == "*"):
                index = int(e['model'][1:])
                origin = parse_vector(e['origin'])
                entity_origins[index] = origin

        end_bench(b)

        b = start_bench("Read texdata")
        self.file.seek(self.lumps[2].offset, False)
        texdata = self.file.read_named(self.lumps[2].size, '3fI2I2I', BspTexData, decompress=True)
        end_bench(b)

        b = start_bench("Read vertices")
        self.file.seek(self.lumps[3].offset, False)
        verts = self.file.read_iterative(self.lumps[3].size, '3f', decompress=True)
        original_verts = verts.copy()
        end_bench(b)

        b = start_bench("Read texinfo")
        self.file.seek(self.lumps[6].offset, False)
        texinfo = self.file.read_named(self.lumps[6].size, '8f8fII', BspTexInfo, decompress=True)
        end_bench(b)

        # Faces
        b = start_bench("Read faces")
        self.file.seek(self.lumps[7].offset, False)
        faces = self.file.read_named(self.lumps[7].size, 'HBBIhhhh4BIfIIIIIHHI', BspFace, decompress=True)
        end_bench(b)

        # Edges
        b = start_bench("Read edges")
        self.file.seek(self.lumps[12].offset, False)
        edges = self.file.read_iterative(self.lumps[12].size, 'HH', decompress=True)
        end_bench(b)

        # Surfedges
        b = start_bench("Read surfedges")
        self.file.seek(self.lumps[13].offset, False)
        surfedges = self.file.read_iterative_single(self.lumps[13].size, "i", decompress=True)
        end_bench(b)

        # Models
        b = start_bench("Read models")
        self.file.seek(self.lumps[14].offset, False)
        models = self.file.read_named(self.lumps[14].size, "3f3f3fIII", BspModel, decompress=True)
        end_bench(b)

        # Displacement info
        b = start_bench("Read displacement info")
        self.file.seek(self.lumps[26].offset, False)
        displacementinfo = self.file.read_named(self.lumps[26].size, "3fiiiifiHii11Q5Q", BspDisplacementInfo, decompress=True)
        end_bench(b)

        # Displacement verts
        b = start_bench("Read displacement verts")
        self.file.seek(self.lumps[33].offset, False)
        displacement_verts = self.file.read_named(self.lumps[33].size, "3fff", BspDisplacementVert, decompress=True)
        end_bench(b)

        # Game lump
        b = start_bench("Read game lump")
        self.file.seek(self.lumps[35].offset, False)
        game_lump = parse_gamelump(self.file.f.read(self.lumps[35].size))
        static_props = []
        for gl in game_lump:
            if(gl[0] == 0x73707270):
                self.file.seek(gl[3], False)
                static_props = parse_static_props(try_decompress(self.file.f.read(gl[4])), gl[2])
                break
        end_bench(b)

        b = start_bench("Read pakfile")
        self.file.seek(self.lumps[40].offset, False)
        pakdata = try_decompress(self.file.f.read(self.lumps[40].size))
        open("pak.zip", 'wb').write(pakdata)
        pakfile = zipfile.ZipFile("pak.zip")
        vpk.mount("pak.zip")
        end_bench(b)

        # Texture string data
        b = start_bench("Read texture string data")
        self.file.seek(self.lumps[43].offset, False)
        tex_stringdata = try_decompress(self.file.f.read(self.lumps[43].size))
        end_bench(b)

        # Texture string table
        b = start_bench("Read texture string table")
        self.file.seek(self.lumps[44].offset, False)
        tex_stringtable = self.file.read_iterative_single(self.lumps[44].size, "I", decompress=True)
        end_bench(b)

        b = start_bench("Process faces")
        processed_faces = []
        processed_verts = []
        processed_textureindices = []
        texture_coordinates = []
        stripped_faces = []
        hasbeentouched = [False] * len(verts)

        displacement_finishedverts = []
        displacement_faces = []
        displacement_texture_coordinates = []
        displacement_textureindices = []
        displacement_indices = []
        displacement_facecolours = []
        displacement_current = 0
        for bi, m in enumerate(models):
            origin = [0, 0, 0]
            if(bi != 0): # Skip everything that's not worldspawn (we'll do this later)
                if(not entity_origins.get(bi)):
                    continue
                origin = entity_origins[bi]

            for fi in range(m.face_count):
                f = faces[m.first_face + fi]
                if(f.texinfo == -1):
                    continue
    
                ti = texinfo[f.texinfo]
                td = texdata[ti.texdata]
                if(ti.flags & 0x2c0):
                    continue

                # TODO: Study how displacements are calculated, and optimise this
                if(f.dispinfo != -1):
                    # continue
                    di = displacementinfo[f.dispinfo]
                    low_base = (di.start_x, di.start_y, di.start_z)
                    if(f.edge_count != 4):
                        print(f"Bad displacement (face #{i})")
                        continue

                    corner_verts = list()
                    corner_indices = list()
                    base_dist = np.inf
                    base_index = -1
                    for k in range(4):
                        ei = surfedges[f.first_edge+k]
                        vi = edges[-ei if ei < 0 else ei][1 if ei < 0 else 0]

                        corner_verts.append(verts[vi])
                        corner_indices.append(vi)
                        this_dist = abs(corner_verts[k][0] - low_base[0]) + abs(corner_verts[k][1] - low_base[1]) + abs(corner_verts[k][2] - low_base[2])
                        if(this_dist < base_dist):
                            base_dist = this_dist
                            base_index = k
                    
                    if(base_index == -1):
                        print(f"Bad base in displacement #{i}")
                        continue

                    high_base = corner_verts[(base_index+3) % 4]
                    high_ray = np.subtract(corner_verts[(base_index+2) % 4], high_base)
                    low_ray = np.subtract(corner_verts[(base_index+1) % 4], low_base)

                    verts_wide = (2 << (di.power - 1)) + 1
                    base_verts = []
                    base_dispvert_index = di.disp_vert_start
                    if(base_dispvert_index < 0):
                        base_dispvert_index = abs(base_dispvert_index)
                    
                    for y in range(verts_wide):
                        fy = y / (verts_wide-1)
                        mid_base = np.add(low_base, np.multiply(low_ray, fy))
                        mid_ray = np.subtract(np.add(high_base, np.multiply(high_ray, fy)), mid_base)

                        for x in range(verts_wide):
                            fx = x / (verts_wide - 1)
                            i = x + y * verts_wide
                            
                            dv = displacement_verts[base_dispvert_index+i]
                            offset = (dv.vx, dv.vy, dv.vz)
                            scale = dv.dist

                            base_verts.append(np.add(np.add(mid_base, np.multiply(mid_ray, fx)), np.multiply(offset, scale)))


                    for y in range(verts_wide-1):
                        for x in range(verts_wide-1):
                            i = x + y * verts_wide

                            displacement_finishedverts.append(base_verts[i])
                            displacement_finishedverts.append(base_verts[i+1])
                            displacement_finishedverts.append(base_verts[i+verts_wide])
                            displacement_finishedverts.append(base_verts[i+verts_wide+1])

                            displacement_texture_coordinates.append((
                                calculate_uv(texinfo[f.texinfo], td, base_verts[i]),
                                calculate_uv(texinfo[f.texinfo], td, base_verts[i+1]),
                                calculate_uv(texinfo[f.texinfo], td, base_verts[i+verts_wide]),
                                calculate_uv(texinfo[f.texinfo], td, base_verts[i+verts_wide+1]),
                            ))

                            displacement_textureindices.append(texinfo[f.texinfo].texdata)
                            displacement_faces.append(f)

                            td = texdata[texinfo[f.texinfo].texdata]
                            c = (td.reflectivity_r, td.reflectivity_g, td.reflectivity_b)
                            displacement_facecolours.append((*np.sqrt(c), 1.0))

                            if(i%2):
                                displacement_indices.append((
                                    displacement_current,   # v1
                                    displacement_current+1, # v2
                                    displacement_current+3, # v4
                                    displacement_current+2  # v3
                                ))
                            else:
                                displacement_indices.append((
                                    displacement_current,   # v1
                                    displacement_current+1, # v2
                                    displacement_current+3, # v4
                                    displacement_current+2  # v3
                                ))

                            displacement_current += 4
                        
                else:
                    stripped_faces.append(f)
                    processed_textureindices.append(texinfo[f.texinfo].texdata)
                    face = []
                    texcoord = []
                    faceverts = []
                    for ei in range(f.edge_count):
                        surfedge = surfedges[f.first_edge + ei]
                        vi = edges[abs(surfedge)][1 if surfedge < 0 else 0]
                        texcoord.append(calculate_uv(ti, td, original_verts[vi]))
                        if(not hasbeentouched[vi]):
                            v = verts[vi]
                            nv = (
                                v[0] + origin[0],
                                v[1] + origin[1],
                                v[2] + origin[2]
                            )
                            verts[vi] = nv
                            hasbeentouched[vi] = True
                        face.append(vi)

                    texcoord.reverse()
                    face.reverse()
                    texture_coordinates.append(tuple(texcoord))
                    processed_verts.append(tuple(faceverts))
                    processed_faces.append(tuple(face))

        end_bench(b)

        b = start_bench("Create mesh")
        obj_name = bpy.path.display_name_from_filepath(self.filepath)

        mesh = bpy.data.meshes.new(obj_name + "_mesh")
        ob = bpy.data.objects.new(obj_name, mesh)
        mesh.from_pydata(verts, [], processed_faces)

        dmesh = bpy.data.meshes.new(obj_name + "_displacement_mesh")
        dob = bpy.data.objects.new(obj_name + "_displacement", dmesh)
        dmesh.from_pydata(displacement_finishedverts, [], displacement_indices)

        if dmesh.vertex_colors:
            vcol_layer = dmesh.vertex_colors.active
        else:
            vcol_layer = dmesh.vertex_colors.new()
        for pi, poly in enumerate(dmesh.polygons):
            for li in poly.loop_indices:
                vcol_layer.data[li].color = displacement_facecolours[pi]

        if(self.downscale):
            ob.scale *= HU_SCALE_FACTOR
            dob.scale *= HU_SCALE_FACTOR

        
        collection = bpy.data.collections.new("Map " + obj_name)
        bpy.context.scene.collection.children.link(collection)
        collection.objects.link(ob)
        collection.objects.link(dob)
        end_bench(b)

        b = start_bench("Create entity placeholders")
        entity_collection = bpy.data.collections.new("entities")
        light_collection = bpy.data.collections.new("light")
        collection.children.link(entity_collection)
        collection.children.link(light_collection)
        for e in entities:
            if(e.get("origin")):
                if("targetname" in e):
                    eobj = bpy.data.objects.new(f"{e['targetname']} ({e['classname']})", None)
                if('hammerid' in e):
                    eobj = bpy.data.objects.new(f"{e['hammerid']} ({e['classname']})", None)
                else:
                    eobj = bpy.data.objects.new(f"untitled ({e['classname']})", None)
                eobj.location = parse_vector(e["origin"], downscale=self.downscale)
                if(e.get("angles")):
                    eobj.rotation_euler = angles_to_radians(parse_vector(e["angles"]))
                eobj.scale *= 0.25

                if(e['classname'] == "light"):
                    light = bpy.data.lights.new(name="light", type='POINT')
                    if('_light' in e):
                        light.color = parse_rgba(e['_light'])[:3]
                    light_object = bpy.data.objects.new("light", object_data=light)
                    light_object.parent = eobj
                    light_collection.objects.link(light_object)

                entity_collection.objects.link(eobj)


        model_duplicates = 0
        if(self.import_props):
            dupe_count = 0
            dupe_find = []
            for p in static_props:
                mname = p[0].strip().lower()
                for d in dupe_find:
                    if(mname == d):
                        dupe_count += 1
                        break
                dupe_find.append(mname)

            model_collection = bpy.data.collections.new("static props")
            collection.children.link(model_collection)
            duplicate_cache = {}
            model_cache = {}
            for i, p in enumerate(static_props):
                pobj = bpy.data.objects.new(f"static prop #{i} ({p[0]})", None)
                pobj['model_path'] = p[0]
                pobj.location = np.multiply(p[1], HU_SCALE_FACTOR) if self.downscale else p[1]
                pobj.rotation_euler = angles_to_radians((p[2][2], p[2][0], p[2][1])) # angles_to_radians((p[2][0], p[2][1] + 90, p[2][2] - 90))
                if(self.downscale):
                    pobj.scale *= HU_SCALE_FACTOR
                try:
                    update_bench(b, f"{i+1}/{len(static_props)}")
                    
                    mname = p[0].strip().lower()
                    if(model_cache.get(mname)):
                        dupe_count -= 1
                        duplicate_cache[i] = p
                    else:

                        mdl_file = BinaryReader(vpk.open_from_mounted(p[0]))
                        vvd_file = BinaryReader(vpk.open_from_mounted(p[0].replace('mdl', 'vvd')))
                        vtx_file = BinaryReader(vpk.open_from_mounted(p[0].replace('mdl', 'dx90.vtx')))
                        if(not mdl_file.is_valid):
                            print("Failed to load model: MDL file not found")
                            continue
                        if(not vvd_file.is_valid):
                            print("Failed to load model: VVD file not found")
                            continue
                        if(not vtx_file.is_valid):
                            print("Failed to load model: VTX file not found")
                            continue

                        mobj = load_mdl(mdl_file, vvd_file, vtx_file, False)
                        model_cache[mname] = mobj

                        mobj.parent = pobj

                except Exception as e:
                    print(f"Error importing static prop: '{e}'")
                    traceback.print_exc(file=sys.stdout)
                    pass

            for i, p in duplicate_cache.items():
                pobj = bpy.data.objects.new(f"static prop #{i} ({p[0]})", None)
                pobj['model_path'] = p[0]
                pobj.location = np.multiply(p[1], HU_SCALE_FACTOR) if self.downscale else p[1]
                pobj.rotation_euler = angles_to_radians((p[2][2], p[2][0], p[2][1])) # angles_to_radians((p[2][0], p[2][1] + 90, p[2][2] - 90))
                if(self.downscale):
                    pobj.scale *= HU_SCALE_FACTOR
                try:
                    mname = p[0].strip().lower()
                    if(model_cache.get(mname)):
                        dupe_count -= 1
                        original_model = model_cache[mname]

                        duplicate_model = original_model.copy()
                        duplicate_model.data = original_model.data.copy()
                        duplicate_model.parent = pobj
                        model_collection.objects.link(duplicate_model)
                    else:
                        raise Exception(f"Couldn't find original '{mname}' in cache")
                except Exception as e:
                    print(f"Error copying static prop: '{e}'")
                    traceback.print_exc(file=sys.stdout)
                    pass
                
                model_collection.objects.link(pobj)

        end_bench(b)

        b = start_bench("Import materials")
        for i, td in enumerate(texdata):
            usefilter = False
            # td = texdata[ti.texdata]
            texture_name_offset = tex_stringtable[td.name_table_id]
            material_path = tex_stringdata[texture_name_offset:tex_stringdata.index(b'\0', texture_name_offset)].decode('ascii')
            update_bench(b, f"{i+1}/{len(texdata)}")
            if(self.import_textures):
                # Hack-ish
                material_path_withext = material_path if material_path[-4:].lower() == '.vmt' else material_path + ".vmt"
                material_file = vpk.open_from_mounted("materials/" + material_path_withext)

                if(not material_file):
                    print(f"Material '{material_path}' not found in mounted archives")
                    imported_material = createNoneMaterial(material_path)
                else:
                    imported_material = load_vmt(material_file, material_path, diffuse_colour=[sqrt(td.reflectivity_r), sqrt(td.reflectivity_g), sqrt(td.reflectivity_b), 1.0])
            else:
                imported_material = createEmptyMaterial(material_path, diffuse_colour=[sqrt(td.reflectivity_r), sqrt(td.reflectivity_g), sqrt(td.reflectivity_b), 1.0])

            ob.data.materials.append(imported_material)
        end_bench(b)

        b = start_bench("Apply texture coordinates")
        if(mesh.is_editmode):
            bm = bmesh.from_edit_mesh(mesh)
        else:
            bm = bmesh.new()
            bm.from_mesh(mesh)

        uv_layer = bm.loops.layers.uv.verify()
        for i, face in enumerate(bm.faces):
            ti = texinfo[faces[i].texinfo]
            td = texdata[ti.texdata]
            start_edge = faces[i].first_edge

            uv_face = texture_coordinates[i]
            for li, loop in enumerate(face.loops):
                loop[uv_layer].uv = uv_face[li]
        
        if bm.is_wrapped:
            bmesh.update_edit_mesh(me, False, False)
        else:
            bm.to_mesh(mesh)
            mesh.update()
        end_bench(b)

        b = start_bench("Assign materials")
        for i, f in enumerate(stripped_faces): # stripped_faces is a workaround
            tdi = processed_textureindices[i]
            texture_name_offset = tex_stringtable[texdata[tdi].name_table_id]
            texture_name = tex_stringdata[texture_name_offset:tex_stringdata.index(b'\0', texture_name_offset)].decode('ascii')
            if(texture_name not in bpy.data.materials):
                # print(f"WARNING: Missing material {texture_name}")
                continue

            if(texinfo[f.texinfo].flags & 0x6 and not ob.data.materials[tdi].node_tree.nodes.get("Emission")): # Hacky-ish workaround for the skybox. Doesn't remove the texture node but that's okay for now
                m = ob.data.materials[tdi]
                m.shadow_method = 'NONE'
                node_tree = m.node_tree
                node_output = node_tree.nodes["Material Output"]
                node_emission = node_tree.nodes.new(type='ShaderNodeEmission')
                node_emission.inputs[0].default_value = m.diffuse_color
                node_tree.links.new(node_emission.outputs[0], node_output.inputs[0])

            ob.data.polygons[i].material_index = tdi

        end_bench(b)

        print('-' * (64 + 3))

        end_bench(sb)

        return True


def menu_import(self, context):
    self.layout.operator(BspLoader.bl_idname, text='Source 1 BSP (.bsp)')
    self.layout.operator(BspLoaderOld.bl_idname, text='Source 1 BSP (.bsp) (DEPRECATED IMPORTER')


def register():
    bpy.utils.register_class(BspLoaderOld)
    bpy.utils.register_class(BspLoader)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.utils.unregister_class(BspLoader)
    bpy.utils.unregister_class(BspLoaderOld)
