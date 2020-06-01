import bpy
from math import radians

from bpy.props import (StringProperty, BoolProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper)
from ..shared.binhelper import BinaryReader
from .vtf import load_vtf
from ..shared import vpk

def createNoneTexture():
    image = bpy.data.images.new(
        "NOTEXTURE",
        width=2,
        height=2
    )

    pixels = [
        1.0, 0.0, 0.0, 1.0,
        0.0, 0.0, 0.0, 1.0,
        0.0, 0.0, 0.0, 1.0,
        1.0, 0.0, 0.0, 1.0,
    ]

    image.pixels = pixels
    image.pack()

    return image


def createNoneMaterial(name):
    m = bpy.data.materials.new(name)
    m.use_backface_culling = True
    m.use_nodes = True
    node_tree = m.node_tree
    node_tree.nodes.remove(node_tree.nodes["Principled BSDF"])
    node_output = node_tree.nodes["Material Output"]
    node_texture = node_tree.nodes.new(type='ShaderNodeTexImage')
    node_texture.image = createNoneTexture()
    node_texture.interpolation = 'Closest'

    node_tree.links.new(node_texture.outputs[0], node_output.inputs[0])
    return m


def parse_kv(source: str):
    keys = {}
    # print(source)
    lines = [l.strip() for l in source.splitlines()]
    keys['materialtype'] = lines[0][1:-1].lower()

    # Kind of hacky (not actual kv parsing), but it works for now
    for i in range(len(lines)):
        if(lines[i].startswith('{')):
            i += 1
            while i < len(lines) and not lines[i].startswith('}'):
                if(lines[i].startswith('{')):
                    while(i < len(lines) and not lines[i].startswith('}')):
                        i += 1

                if(lines[i].startswith('/')):
                    i += 1
                    continue

                kv = [s.lower() for s in lines[i].split('"') if s != '' and s != ' ' and s != '\t\t' and s != '\t']
                # print(f"adding key {lines[i]} => {kv}")
                if(len(kv) == 2):
                    keys[kv[0].lower()] = kv[1]
                i += 1

    return keys


def load_vmt(file: BinaryReader, name, diffuse_colour=[1.0, 1.0, 1.0, 1.0]):
    imported_material = parse_kv(file.read().decode('utf-8'))
    if('include' in imported_material):
        try:
            imported_material.update(parse_kv(vpk.open_from_mounted(imported_material['include']).read().decode('utf-8')))
        except:
            print(f"Failed to import included material {imported_material['include']}")
            pass

    if('$basetexture' in imported_material):
        texture_filter = 'Linear'
        texture_file = vpk.open_from_mounted("materials/" + imported_material['$basetexture'] + '.vtf')
        if(texture_file):
            texture = load_vtf(texture_file, imported_material['$basetexture'])
        else:
            texture_filter = 'Closest'
            texture = createNoneTexture()
    else:
        texture_filter = 'Closest'
        texture = createNoneTexture()

    m = bpy.data.materials.new(name)
    m.use_backface_culling = True
    m.use_nodes = True
    m.diffuse_color = diffuse_colour
    node_tree = m.node_tree
    node_tree.nodes.remove(node_tree.nodes["Principled BSDF"])
    node_output = node_tree.nodes["Material Output"]
    node_texture = node_tree.nodes.new(type='ShaderNodeTexImage')
    node_texture.image = texture
    node_texture.interpolation = texture_filter

    if('%compilewater' in imported_material):
        node_transparent = node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
        node_mix = node_tree.nodes.new(type='ShaderNodeMixShader')
        node_gloss = node_tree.nodes.new(type='ShaderNodeBsdfGlossy')
        node_gloss.inputs[1].default_value = 0.1

        node_tree.links.new(node_transparent.outputs[0], node_mix.inputs[1])
        node_tree.links.new(node_gloss.outputs[0], node_mix.inputs[2])
        node_tree.links.new(node_mix.outputs[0], node_output.inputs[0])
        m.blend_method = 'BLEND'
        m.use_screen_refraction = True
    elif(imported_material['materialtype'] == "refract"):
        if('$normalmap' in imported_material):
            normalmap = load_vtf(vpk.open_from_mounted("materials/" + imported_material['$normalmap'] + '.vtf'), imported_material['$normalmap'])
            node_texture.image = normalmap

        node_refract = node_tree.nodes.new(type='ShaderNodeBsdfRefraction')
        node_transparent = node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
        node_mix = node_tree.nodes.new(type='ShaderNodeMixShader')

        node_tree.links.new(node_texture.outputs[1], node_mix.inputs[0])
        node_tree.links.new(node_transparent.outputs[0], node_mix.inputs[1])
        node_tree.links.new(node_refract.outputs[0], node_mix.inputs[2])
        node_tree.links.new(node_texture.outputs[0], node_refract.inputs[3])
        node_tree.links.new(node_mix.outputs[0], node_output.inputs[0])
    elif('$translucent' in imported_material or '$alphatest' in imported_material or '$additive' in imported_material):
        node_diffuse = node_tree.nodes.new(type='ShaderNodeBsdfDiffuse')
        node_transparent = node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
        node_mix = node_tree.nodes.new(type='ShaderNodeMixShader')

        node_tree.links.new(node_texture.outputs[1], node_mix.inputs[0])
        node_tree.links.new(node_transparent.outputs[0], node_mix.inputs[1])
        node_tree.links.new(node_texture.outputs[0], node_diffuse.inputs[0])
        node_tree.links.new(node_diffuse.outputs[0], node_mix.inputs[2])
        node_tree.links.new(node_mix.outputs[0], node_output.inputs[0])
    else:
        node_diffuse = node_tree.nodes.new(type='ShaderNodeBsdfDiffuse')

        if('$normalmap' in imported_material or '$bumpmap' in imported_material):
            which_one = '$normalmap' if '$normalmap' in imported_material else '$bumpmap'
            normalmap_file = vpk.open_from_mounted("materials/" + imported_material[which_one] + '.vtf')

            if(normalmap_file):
                normalmap = load_vtf(normalmap_file, imported_material[which_one])
                node_bump = node_tree.nodes.new(type='ShaderNodeTexImage')
                node_bump.image = normalmap
                # node_bump.image.colorspace_settings.name = 'Non-Color'

                node_normalmap = node_tree.nodes.new(type='ShaderNodeNormalMap')
                node_normalmap.space = 'WORLD'
                node_normalmap.inputs[0].default_value = 0.3

                node_tree.links.new(node_bump.outputs[0], node_normalmap.inputs[1])
                node_tree.links.new(node_normalmap.outputs[0], node_diffuse.inputs[2])
                if('$ssbump' in imported_material):
                    node_ssbump_separate = node_tree.nodes.new(type='ShaderNodeSeparateRGB')
                    node_ssbump_combine = node_tree.nodes.new(type='ShaderNodeCombineRGB')

                    node_tree.links.new(node_bump.outputs[0], node_ssbump_separate.inputs[0])
                    node_tree.links.new(node_ssbump_combine.outputs[0], node_normalmap.inputs[1])

                    # Swizzle the channels so they work properly in blender
                    node_tree.links.new(node_ssbump_separate.outputs[0], node_ssbump_combine.inputs[1])
                    node_tree.links.new(node_ssbump_separate.outputs[1], node_ssbump_combine.inputs[0])
                    node_tree.links.new(node_ssbump_separate.outputs[2], node_ssbump_combine.inputs[2])

        node_tree.links.new(node_texture.outputs[0], node_diffuse.inputs[0])
        node_tree.links.new(node_texture.outputs[1], node_diffuse.inputs[1])
        node_tree.links.new(node_diffuse.outputs[0], node_output.inputs[0])

    try:
        if('$basetexturetransform' in imported_material):
            transform = imported_material['$basetexturetransform'].split(' ')
            node_texcoord = node_tree.nodes.new(type='ShaderNodeTexCoord')
            node_mapping = node_tree.nodes.new(type='ShaderNodeMapping')

            node_mapping.inputs[1].default_value = [float(transform[9]),    float(transform[10]),   0] # Transform
            node_mapping.inputs[2].default_value = [0,                      0,                      radians(float(transform[7]))] # Rotation
            node_mapping.inputs[3].default_value = [float(transform[4]),    float(transform[5]),    0] # Scale
            
            node_tree.links.new(node_texcoord.outputs[2], node_mapping.inputs[0])
            node_tree.links.new(node_mapping.outputs[0], node_texture.inputs[0])
    except:
        pass

    if('$translucent' in imported_material or '$alphatest' in imported_material):
        m.blend_method = 'CLIP' if '$alphatest' in imported_material else 'BLEND' 
        if("$alphatest" in imported_material):
            if('$alphatestreference' in imported_material):
                m.alpha_threshold = float(imported_material['$alphatestreference'])

    return m


class VmtLoader(bpy.types.Operator, ImportHelper):
    """Import VMT material files from the Source engine"""
    bl_idname = "sourcesmoothie.source1_vmt"
    bl_description = "Import Source 1 VMT material files"
    bl_label = "Import Source 1 VMT"

    filename_ext = ".vmt"
    filter_glob: StringProperty(
        default="*.vmt",
        options={'HIDDEN'},
    )

    filepath: StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        self.file = open(self.filepath, 'rb')

        if(not self.load()):
            return {'CANCELLED'}

        return {'FINISHED'}
    
    def load(self):
        material = load_vmt(self.file, bpy.path.display_name_from_filepath(self.filepath))
        return True if material != None else False


def menu_import(self, context):
    self.layout.operator(VmtLoader.bl_idname, text='Source 1 VMT (.vmt)')


def register():
    bpy.utils.register_class(VmtLoader)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.utils.unregister_class(VmtLoader)