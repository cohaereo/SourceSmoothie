from collections import namedtuple
from ..shared.binhelper import BinaryReader

VvdVertex = namedtuple("VvdVertex", "position normal texcoord")
VtxStripGroup = namedtuple("VtxStripGroup", "vertices indices")
VtxVertex = namedtuple("VtxStripGroup", "boneweight_index_0 boneweight_index_1 boneweight_index_2 bone_count original_vertex bone_id_0 bone_id_1 bone_id_2")

# TODO: This needs to be moved to a more convenient file, as it's used in the BSP loader as well
HU_SCALE_FACTOR = 0.01904
DEFAULT_LOD = 0

class MdlData:
    def __init__(self, mdl: BinaryReader, vvd: BinaryReader, vtx: BinaryReader, downscale=True):
        self.downscale = downscale

        self.mdldata = MdlHeader(mdl)
        self.vvddata = VvdData(vvd)
        self.vtxdata = VtxData(vtx)

    def read(self):
        if(not self.mdldata.read()):
            return False

        if(not self.vvddata.read()):
            return False

        return self.vtxdata.read()


class VvdData:
    def __init__(self, vvd: BinaryReader):
        self.f = vvd
        signature = self.f.readString(4)
        if(signature != 'IDSV'):
            raise Exception("Invalid VVD file (signature doesn't match)")

        self.version = self.f.read32()
    
    def read(self):
        self.lod_vertex_count = [0] * 8

        (
            self.checksum,
            self.lod_count,

            # TODO: can this be done in one line instead of 8 lines?
            self.lod_vertex_count[0],
            self.lod_vertex_count[1],
            self.lod_vertex_count[2],
            self.lod_vertex_count[3],
            self.lod_vertex_count[4],
            self.lod_vertex_count[5],
            self.lod_vertex_count[6],
            self.lod_vertex_count[7],

            self.fixup_count,

            self.fixup_offset,
            self.vertex_offset,
            self.tangent_offset
        ) = self.f.readt("14I")

        self.f.seek(self.vertex_offset, False)

        self.vertices = []
        for i in range(self.lod_vertex_count[DEFAULT_LOD]):
            self.f.seek(16) # Skip bone weights for now
            self.vertices.append(VvdVertex(
                self.f.readVec3(),
                self.f.readVec3(),
                self.f.readVec2()
            ))

        return True


class MdlHeader:
    def __init__(self, mdl: BinaryReader):
        self.f = mdl
        signature = self.f.readString(4)
        if(signature != 'IDST'):
            raise Exception("Invalid MDL file (signature doesn't match)")

        self.version = self.f.read32()
    
    def read(self):
        self.checksum = self.f.read32()
        self.name = self.f.readString(64).strip()
        self.data_length = self.f.read32()

        self.eyepos = self.f.readVec3()
        self.illumpos = self.f.readVec3()
        self.hull_min = self.f.readVec3()
        self.hull_max = self.f.readVec3()
        self.view_bbmin = self.f.readVec3()
        self.view_bbmax = self.f.readVec3()

        self.flags = self.f.read32()

        (
            self.bone_count,
            self.bone_offset,

            self.bonecontroller_count,
            self.bonecontroller_offset,

            self.hitbox_count,
            self.hitbox_offset,

            self.localanim_count,
            self.localanim_offset,

            self.localseq_count,
            self.localseq_offset,

            self.activitylistversion,
            self.eventsindexed,

            self.texture_count,
            self.texture_offset,

            self.texturedir_count,
            self.texturedir_offset,

            self.skinreference_count,
            self.skinfamily_count,
            self.skinreference_index,

            self.bodypart_count,
            self.bodypart_offset,

            self.attachment_count,
            self.attachment_offset,

            self.localnode_count,
            self.localnode_index,
            self.localnode_name_index,

            self.flexdesc_count,
            self.flexdesc_index,

            self.flexcontroller_count,
            self.flexcontroller_index,

            self.flexrules_count,
            self.flexrules_index,

            self.ikchain_count,
            self.ikchain_index,

            self.mouths_count,
            self.mouths_index,

            self.localposeparam_count,
            self.localposeparam_index,

            self.surfaceprop_index,

            self.keyvalue_count,
            self.keyvalue_offset,

            self.iklock_count,
            self.iklock_offset,
        ) = self.f.readt("43I")

        return True

BODYPART_SIZE = 8

class VtxData:
    def __init__(self, vtx: BinaryReader):
        self.f = vtx

        self.version = self.f.read32()
        if(self.version != 7):
            raise Exception("Unsupported VTX version")
    
    def read(self):
        (
            self.vert_cache_size,
            self.max_bones_per_strip,
            self.max_bones_per_tri,
            self.max_bones_per_vert,

            self.checksum,
            self.lod_count,
            self.material_replacement_list_offset,

            self.bodypart_count,
            self.bodypart_offset
        ) = self.f.readt("IHH6I")

        self.f.seek(self.bodypart_offset, False)
        self.bodyparts = []
        for i in range(self.bodypart_count):
            self.bodyparts.append(self.read_bodypart())
        
        return True
    
    def read_bodypart(self):
        cpos = self.f.f.tell()
        model_count = self.f.read32()
        model_offset = self.f.read32()

        models = []
        with self.f.save_pos():
            self.f.seek(cpos + model_offset, False)
            for i in range(model_count):
                models.append(self.read_model())
        
        return models

    def read_model(self):
        cpos = self.f.f.tell()
        lod_count = self.f.read32()
        lod_offset = self.f.read32()

        lods = []
        with self.f.save_pos():
            self.f.seek(cpos + lod_offset, False)
            for i in range(lod_count):
                lods.append(self.read_lod())
        
        return lods

    def read_lod(self):
        cpos = self.f.f.tell()
        mesh_count = self.f.read32()
        mesh_offset = self.f.read32()
        switch_point = self.f.readFloat()

        meshes = []
        with self.f.save_pos():
            self.f.seek(cpos + mesh_offset, False)
            for i in range(mesh_count):
                meshes.append(self.read_mesh())
        
        return meshes

    def read_mesh(self):
        cpos = self.f.f.tell()
        stripgroup_count = self.f.read32()
        stripgroup_offset = self.f.read32()
        flags = self.f.read8()

        stripgroups = []
        with self.f.save_pos():
            self.f.seek(cpos + stripgroup_offset, False)
            for i in range(stripgroup_count):
                stripgroups.append(self.read_stripgroup())
        
        return stripgroups

    def read_stripgroup(self):
        cpos = self.f.f.tell()
        verts_count = self.f.read32()
        verts_offset = self.f.read32()

        indices_count = self.f.read32()
        indices_offset = self.f.read32()

        strip_count = self.f.read32()
        strip_offset = self.f.read32()

        flags = self.f.read8()

        indices = []
        verts = []
        with self.f.save_pos():
            self.f.seek(cpos + indices_offset, False)
            for i in range(indices_count):
                indices.append(self.f.read16())

            self.f.seek(cpos + verts_offset, False)
            for i in range(verts_count):
                verts.append(VtxVertex._make(self.f.readt("4BH3B")))
        
        return VtxStripGroup._make((verts, indices))