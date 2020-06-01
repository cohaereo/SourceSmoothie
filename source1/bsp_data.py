from collections import namedtuple
from ..shared.binhelper import BinaryReader, try_decompress
from ..shared import vpk
import zipfile

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
    light_offset
    area
    lightmap_min_x lightmap_min_y
    lightmap_size_x lightmap_size_y
    original_face
    prim_count
    first_prim
    smoothing_groups
""")

HU_SCALE_FACTOR = 0.01904


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


class BspData:
    def __init__(self, br: BinaryReader, downscale=True):
        self.downscale = downscale
        self.f = br
        signature = self.f.readString(4)
        if(signature != 'VBSP'):
            raise Exception("Invalid BSP file (signature doesn't match)")

        self.version = self.f.read32()
        self.lumps = self.f.read_named(16 * 64, '4I', BspLump)

    def read(self):
        self.f.seek(self.lumps[0].offset, False)
        entitydata = try_decompress(self.f.f.read(self.lumps[0].size)).decode('ascii')
        open("entities.kv", 'w').write(entitydata)
        self.entities = parse_entities(entitydata)
        self.model_origins = {}
        for e in self.entities:
            if(e.get('model') and e['model'][0] == "*"):
                index = int(e['model'][1:])
                origin = (
                    parse_vector(e['origin'], downscale=self.downscale),
                    parse_vector(e['angles']) if e.get('angles') else [0, 0, 0]
                )

                self.model_origins[index] = origin

        self.f.seek(self.lumps[2].offset, False)
        self.texdata = self.f.read_named(self.lumps[2].size, '3fI2I2I', BspTexData, decompress=True)

        self.f.seek(self.lumps[3].offset, False)
        self.vertices = self.f.read_iterative(self.lumps[3].size, '3f', decompress=True)
        
        self.f.seek(self.lumps[6].offset, False)
        self.texinfo = self.f.read_named(self.lumps[6].size, '8f8fII', BspTexInfo, decompress=True)

        self.f.seek(self.lumps[7].offset, False)
        self.faces = self.f.read_named(self.lumps[7].size, 'HBBIhhhh4BIfIIIIIHHI', BspFace, decompress=True)

        self.f.seek(self.lumps[12].offset, False)
        self.edges = self.f.read_iterative(self.lumps[12].size, '2H', decompress=True)

        self.f.seek(self.lumps[13].offset, False)
        self.surfedges = self.f.read_iterative_single(self.lumps[13].size, 'i', decompress=True)

        self.f.seek(self.lumps[14].offset, False)
        self.models = self.f.read_named(self.lumps[14].size, '3f3f3fIII', BspModel, decompress=True)
        
        self.f.seek(self.lumps[26].offset, False)
        self.displacementinfo = self.f.read_named(self.lumps[26].size, "3fiiiifiHii11Q5Q", BspDisplacementInfo, decompress=True)

        self.f.seek(self.lumps[33].offset, False)
        self.displacement_verts = self.f.read_named(self.lumps[33].size, "3fff", BspDisplacementVert, decompress=True)

        self.f.seek(self.lumps[40].offset, False)
        pakdata = try_decompress(self.f.f.read(self.lumps[40].size))
        open("pak.zip", 'wb').write(pakdata)
        # pakfile = zipfile.ZipFile("pak.zip")
        vpk.mount("pak.zip")

        self.f.seek(self.lumps[43].offset, False)
        self.texstrdata = try_decompress(self.f.f.read(self.lumps[43].size))

        self.f.seek(self.lumps[44].offset, False)
        self.texstrtable = self.f.read_iterative_single(self.lumps[44].size, "I", decompress=True)

        return True