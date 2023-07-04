'''
Code for rendering the groundtruths of Doc3D dataset 
https://www3.cs.stonybrook.edu/~cvl/projects/dewarpnet/storage/paper.pdf (ICCV 2019)

This code renders the checkerboards using the .blend files 
saved from render_mesh.py 

Written by: Sagnik Das
Stony Brook University, New York
January 2019
'''
import json
import os
import random
import sys
from pathlib import Path

import bpy


def select_object(ob):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.scene.objects.active = None
    ob.select = True
    bpy.context.scene.objects.active = ob


def render_img_newtex(texpath):
    mesh_name = bpy.data.meshes[0].name
    mesh = bpy.data.objects[mesh_name]
    # mesh.select=True
    select_object(mesh)
    page_texturing(mesh, texpath)


def page_texturing(mesh, texpath):
    select_object(mesh)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.material_slot_add()
    bpy.data.materials.new('Material.001')
    mesh.material_slots[0].material = bpy.data.materials['Material.001']
    mat = bpy.data.materials['Material.001']
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    # clear default nodes
    for n in nodes:
        nodes.remove(n)
    out_node = nodes.new(type='ShaderNodeOutputMaterial')
    bsdf_node = nodes.new(type='ShaderNodeBsdfDiffuse')
    texture_node = nodes.new(type='ShaderNodeTexImage')

    texture_node.image = bpy.data.images.load(texpath)

    links = mat.node_tree.links
    links.new(bsdf_node.outputs[0], out_node.inputs[0])
    links.new(texture_node.outputs[0], bsdf_node.inputs[0])

    bsdf_node.inputs[0].show_expanded = True
    texture_node.extension = 'EXTEND'
    texturecoord_node = nodes.new(type='ShaderNodeTexCoord')
    links.new(texture_node.inputs[0], texturecoord_node.outputs[2])


def render():
    bpy.context.scene.camera = bpy.data.objects['Camera']
    bpy.data.scenes['Scene'].render.image_settings.color_depth = '8'
    bpy.data.scenes['Scene'].render.image_settings.color_mode = 'RGB'
    # bpy.data.scenes['Scene'].render.image_settings.file_format='OPEN_EXR'
    bpy.data.scenes['Scene'].render.image_settings.compression = 0
    bpy.ops.render.render(write_still=False)


def get_albedo_img(img_name, path_to_output_alb: str):
    scene = bpy.data.scenes['Scene']
    scene.render.layers['RenderLayer'].use_pass_diffuse_color = True
    bpy.context.scene.use_nodes = True
    tree = bpy.context.scene.node_tree
    links = tree.links

    # clear default nodes
    for n in tree.nodes:
        tree.nodes.remove(n)

    # create input render layer node
    render_layers = tree.nodes.new('CompositorNodeRLayers')

    file_output_node = tree.nodes.new('CompositorNodeOutputFile')
    comp_node = tree.nodes.new('CompositorNodeComposite')

    # file_output_node_0.format.file_format = 'OPEN_EXR'
    out_path = os.path.join(path_to_output_alb)

    file_output_node.base_path = out_path
    file_output_node.file_slots[0].path = img_name
    links.new(render_layers.outputs[21], file_output_node.inputs[0])
    links.new(render_layers.outputs[21], comp_node.inputs[0])


def prepare_no_env_render():
    # Remove lamp
    for lamp in bpy.data.lamps:
        bpy.data.lamps.remove(lamp, do_unlink=True)

    world = bpy.data.worlds['World']
    world.use_nodes = True
    links = world.node_tree.links
    # clear default nodes
    for l in links:
        links.remove(l)
    scene = bpy.data.scenes['Scene']
    scene.cycles.samples = 1
    scene.cycles.use_square_samples = True
    scene.view_settings.view_transform = 'Default'


def main():
    config_file = Path(sys.argv[-1])

    with config_file.open("r") as fp:
        config = json.load(fp)

    random.seed(config["seed"])

    # load blend file
    bpy.ops.wm.open_mainfile(filepath=config["blender_file"])

    render_img_newtex(config["tex_file"])
    prepare_no_env_render()
    get_albedo_img(Path(config["blender_file"]).stem, path_to_output_alb=config["output_dir"])
    render()


if __name__ == "__main__":
    main()
