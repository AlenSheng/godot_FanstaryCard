import bpy
from mathutils import Vector
from pathlib import Path

ROOT = Path(r"G:\Program Files\GodotFiles\godot_FanstaryCard\art\characters\blue_gold_mage\lux3d_20260916_01\single_character")
MODEL = Path(r"G:\Program Files\GodotFiles\godot_FanstaryCard\art\characters\blue_gold_mage\lux3d_20260916_01\correction_pass.glb")
ROOT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(MODEL))
mesh = next(o for o in bpy.context.selected_objects if o.type == 'MESH')

# The service returned a horizontal turnaround strip. Keep the left/front character island.
bpy.context.view_layer.objects.active = mesh
mesh.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
for v in mesh.data.vertices:
    v.select = v.co.x > -0.22
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.delete(type='VERT')
bpy.ops.object.mode_set(mode='OBJECT')

# Recenter and place the extracted character on the ground.
corners = [mesh.matrix_world @ Vector(c) for c in mesh.bound_box]
min_z = min(v.z for v in corners)
cx = (min(v.x for v in corners) + max(v.x for v in corners)) * 0.5
cy = (min(v.y for v in corners) + max(v.y for v in corners)) * 0.5
mesh.location.x -= cx; mesh.location.y -= cy; mesh.location.z -= min_z

floor_mat = bpy.data.materials.new('Neutral Grey Floor'); floor_mat.diffuse_color=(0.42,0.44,0.47,1)
bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0)); floor=bpy.context.object; floor.name='Reference_Ground'; floor.data.materials.append(floor_mat)
world=bpy.data.worlds.new('Reference Grey World'); bpy.context.scene.world=world; world.use_nodes=True
world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.48,0.50,0.53,1); world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.35

corners=[mesh.matrix_world @ Vector(c) for c in mesh.bound_box]; mn=Vector((min(v.x for v in corners),min(v.y for v in corners),min(v.z for v in corners))); mx=Vector((max(v.x for v in corners),max(v.y for v in corners),max(v.z for v in corners))); target=(mn+mx)*0.5; h=mx.z-mn.z; w=max(mx.x-mn.x,mx.y-mn.y)
def light(name,loc,energy,size,color):
    d=bpy.data.lights.new(name,'AREA'); d.energy=energy; d.size=size; d.color=color; o=bpy.data.objects.new(name,d); bpy.context.scene.collection.objects.link(o); o.location=loc; o.rotation_euler=(target-o.location).to_track_quat('-Z','Y').to_euler()
light('Key',(4,-6,h*1.2),900,5,(1,.92,.8)); light('Fill',(-4,-2,h*.8),650,4,(.7,.84,1)); light('Rim',(0,4,h*1.3),1000,3,(.62,.78,1))
camd=bpy.data.cameras.new('Camera'); cam=bpy.data.objects.new('Camera',camd); bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera=cam; camd.type='ORTHO'; camd.ortho_scale=max(h*1.22,w*1.8)
def aim(loc): cam.location=loc; cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
scene=bpy.context.scene; scene.render.engine='BLENDER_EEVEE'; scene.render.resolution_x=1024; scene.render.resolution_y=1024; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'; scene.render.film_transparent=False
for name,loc in {'front':(0,-h*2.8,target.z),'left_side':(h*2.8,0,target.z),'back':(0,h*2.8,target.z),'top':(0,-h*1.8,h*3.5)}.items():
    aim(loc); camd.ortho_scale=max(h*1.22,w*1.8) if name!='top' else max(w*2.0,h*.9); scene.render.filepath=str(ROOT/f'blue_gold_mage_{name}.png'); bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blue_gold_mage_single_character.blend'))
bpy.ops.export_scene.gltf(filepath=str(ROOT/'blue_gold_mage_single_character.glb'),export_format='GLB',export_apply=True)
print('SINGLE_CHARACTER_DONE',ROOT)
