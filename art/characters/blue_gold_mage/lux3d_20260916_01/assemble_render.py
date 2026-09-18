import bpy
import math
from mathutils import Vector
from pathlib import Path

ROOT = Path(r"G:\Program Files\GodotFiles\godot_FanstaryCard\art\characters\blue_gold_mage\lux3d_20260916_01")
MODEL = Path(r"G:\Program Files\GodotFiles\godot_FanstaryCard\art\characters\blue_gold_mage\lux3d_20260916_01.glb")
ROOT.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.film_transparent = False
scene.render.image_settings.color_depth = '8'

world = bpy.data.worlds.new('Reference Grey World')
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.48, 0.50, 0.53, 1.0)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.32

def mat(name, color, rough=0.65, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1.0)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1.0)
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Metallic'].default_value = metallic
    return m

floor_mat = mat('Neutral Grey Floor', (0.42, 0.44, 0.47), 0.8)
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
floor = bpy.context.object
floor.name = 'Reference_Ground'
floor.data.materials.append(floor_mat)

# Import the Lux3D asset as the editable source model.
bpy.ops.import_scene.gltf(filepath=str(MODEL))
imported = list(bpy.context.selected_objects)
for obj in imported:
    obj.select_set(False)

# Normalize model base to the ground while preserving its proportions.
mesh_objs = [o for o in imported if o.type == 'MESH']
if not mesh_objs:
    raise RuntimeError('Lux3D GLB contains no mesh objects')
corners = []
for o in mesh_objs:
    corners.extend([o.matrix_world @ Vector(c) for c in o.bound_box])
min_z = min(v.z for v in corners)
center_x = (min(v.x for v in corners) + max(v.x for v in corners)) * 0.5
center_y = (min(v.y for v in corners) + max(v.y for v in corners)) * 0.5
for o in imported:
    if o.parent is None:
        o.location.x -= center_x
        o.location.y -= center_y
        o.location.z -= min_z

# Recompute bounds after normalization.
corners = []
for o in mesh_objs:
    corners.extend([o.matrix_world @ Vector(c) for c in o.bound_box])
min_v = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
max_v = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
target = (min_v + max_v) * 0.5
height = max_v.z - min_v.z
width = max(max_v.x - min_v.x, max_v.y - min_v.y)

# Soft studio lighting matching the neutral effect-sheet background.
def area(name, loc, energy, size, color):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = loc
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    return obj

area('Key_Softbox', (4.5, -6.0, height * 1.25), 1000, 5.0, (1.0, 0.91, 0.78))
area('Fill_Softbox', (-4.0, -2.0, height * 0.8), 700, 4.0, (0.70, 0.84, 1.0))
area('Rim_Softbox', (0.0, 4.5, height * 1.35), 1200, 3.5, (0.62, 0.78, 1.0))

cam_data = bpy.data.cameras.new('Turnaround_Camera')
camera = bpy.data.objects.new('Turnaround_Camera', cam_data)
scene.collection.objects.link(camera)
scene.camera = camera
cam_data.type = 'ORTHO'
cam_data.ortho_scale = max(height * 1.18, width * 1.9)

def look_at(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()

views = {
    'front': ((0.0, -height * 2.8, target.z), target),
    'left_side': ((height * 2.8, 0.0, target.z), target),
    'back': ((0.0, height * 2.8, target.z), target),
    'top': ((0.0, -height * 1.9, height * 3.4), target),
}

for name, (loc, aim) in views.items():
    camera.location = loc
    look_at(camera, aim)
    if name == 'top':
        cam_data.ortho_scale = max(width * 2.0, height * 0.9)
    else:
        cam_data.ortho_scale = max(height * 1.18, width * 1.9)
    scene.render.filepath = str(ROOT / f'blue_gold_mage_{name}.png')
    bpy.ops.render.render(write_still=True)

# Save an editable Blender scene and an assembled GLB including the studio ground.
blend_path = ROOT / 'blue_gold_mage_lux3d_assembled.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
scene_glb = ROOT / 'blue_gold_mage_lux3d_scene.glb'
bpy.ops.export_scene.gltf(filepath=str(scene_glb), export_format='GLB', export_apply=True)
print('LUX3D_ASSEMBLY_DONE', blend_path, scene_glb)
