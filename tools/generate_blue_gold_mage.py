import bpy
import importlib
import math
import os
import sys
from mathutils import Vector


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "art", "characters", "blue_gold_mage")
os.makedirs(OUT_DIR, exist_ok=True)
BLEND_PATH = os.path.join(OUT_DIR, "blue_gold_mage.blend")
GLB_PATH = os.path.join(OUT_DIR, "blue_gold_mage.glb")
PREVIEW_PATH = os.path.join(OUT_DIR, "blue_gold_mage_preview.png")
EYES_PATH = os.path.join(ROOT, "third_party", "makehuman_system_assets", "eyes", "high-poly", "high-poly.mhclo")
HAIR_PATH = os.path.join(ROOT, "third_party", "makehuman_system_assets", "hair", "cortu_short_messy_hair", "cortu_short_messy_hair.mhclo")
EYEBROWS_PATH = os.path.join(ROOT, "third_party", "makehuman_system_assets", "eyebrows", "eyebrow001", "eyebrow001.mhclo")

BONE_MAP = {
    'root': 'Root', 'spine': 'spine_01', 'chest': 'spine_03',
    'neck': 'neck_01', 'head': 'head',
    'clavicle.L': 'clavicle_l', 'upper_arm.L': 'upperarm_l',
    'forearm.L': 'lowerarm_l', 'hand.L': 'hand_l',
    'clavicle.R': 'clavicle_r', 'upper_arm.R': 'upperarm_r',
    'forearm.R': 'lowerarm_r', 'hand.R': 'hand_r',
    'thigh.L': 'thigh_l', 'shin.L': 'calf_l', 'foot.L': 'foot_l',
    'thigh.R': 'thigh_r', 'shin.R': 'calf_r', 'foot.R': 'foot_r',
    'cape.L': 'spine_03', 'cape.R': 'spine_03',
}


def mpfb_symbol(module_suffix, key):
    for module_name in sys.modules:
        if module_name.endswith(module_suffix):
            return getattr(importlib.import_module(module_name), key)
    raise RuntimeError('MPFB 2.x is required and must be enabled in Blender: ' + module_suffix)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.armatures, bpy.data.materials):
        pass


def mat(name, color, metallic=0.0, roughness=0.5, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1.0)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    if emission:
        bsdf.inputs['Emission Color'].default_value = (*emission, 1.0)
        bsdf.inputs['Emission Strength'].default_value = strength
    if name not in {'EyeWhite','Pupil','Arcane_Crystal'}:
        noise=m.node_tree.nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 95.0 if metallic > .4 else 65.0
        noise.inputs['Detail'].default_value = 3.0
        noise.inputs['Roughness'].default_value = .55
        bump=m.node_tree.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = .11 if metallic > .4 else .075
        bump.inputs['Distance'].default_value = .018
        m.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height'])
        m.node_tree.links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    if name == 'Skin' and 'Subsurface Weight' in bsdf.inputs:
        bsdf.inputs['Subsurface Weight'].default_value=.075
    return m


def finish(obj, material, name, parent=None, bone=None, bevel=0.0):
    obj.name = name
    obj.data.materials.append(material)
    if bevel > 0:
        mod = obj.modifiers.new('Soft edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
    if parent:
        if bone:
            bone = BONE_MAP.get(bone, bone)
            # Child Of constraints preserve authored world placement reliably
            # across Blender versions while still following pose bones.
            con = obj.constraints.new('CHILD_OF')
            con.name = 'Follow Bone'
            con.target = parent
            con.subtarget = bone
            bone_world = parent.matrix_world @ parent.pose.bones[bone].matrix
            con.inverse_matrix = bone_world.inverted()
        else:
            obj.parent = parent
            obj.matrix_parent_inverse = parent.matrix_world.inverted()
    return obj


def cube(name, loc, scale, material, parent=None, bone=None, bevel=0.05, rot=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o, material, name, parent, bone, bevel)


def sphere(name, loc, scale, material, parent=None, bone=None, seg=16, rings=10):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, location=loc)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_smooth()
    return finish(o, material, name, parent, bone)


def cyl(name, loc, radius, depth, material, parent=None, bone=None, vertices=12, rot=(0,0,0), bevel=0.02):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot)
    return finish(bpy.context.object, material, name, parent, bone, bevel)


def bone_points(armature, bone_name):
    mapped = BONE_MAP.get(bone_name, bone_name)
    data_bone = armature.data.bones[mapped]
    return armature.matrix_world @ data_bone.head_local, armature.matrix_world @ data_bone.tail_local


def cyl_between(name, start, end, radius, material, parent=None, bone=None, vertices=24, bevel=0.015):
    direction = Vector(end) - Vector(start)
    midpoint = (Vector(start) + Vector(end)) * .5
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=direction.length, location=midpoint)
    obj = bpy.context.object
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = Vector((0,0,1)).rotation_difference(direction.normalized())
    return finish(obj, material, name, parent, bone, bevel)


def cone_between(name, start, end, radius_start, radius_end, material, parent=None, bone=None, vertices=24):
    direction = Vector(end) - Vector(start)
    midpoint = (Vector(start) + Vector(end)) * .5
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius_start, radius2=radius_end, depth=direction.length, location=midpoint)
    obj = bpy.context.object
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = Vector((0,0,1)).rotation_difference(direction.normalized())
    return finish(obj, material, name, parent, bone, .015)


def cone(name, loc, r1, r2, depth, material, parent=None, bone=None, vertices=12, rot=(0,0,0)):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=depth, location=loc, rotation=rot)
    return finish(bpy.context.object, material, name, parent, bone, 0.025)


def crystal(name, loc, scale, material, parent=None, bone=None):
    verts = [(0,0,1.25),(0,0,-1.25)]
    for z, r in ((0.36,0.62),(-0.36,0.62)):
        for i in range(6):
            a=2*math.pi*i/6
            verts.append((r*math.cos(a),r*math.sin(a),z))
    faces=[]
    for i in range(6):
        j=(i+1)%6
        faces += [(0,2+i,2+j),(1,8+j,8+i),(2+i,8+i,8+j,2+j)]
    mesh=bpy.data.meshes.new(name+'Mesh')
    mesh.from_pydata(verts,[],faces); mesh.update()
    o=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(o)
    o.location=loc; o.scale=scale
    return finish(o,material,name,parent,bone,0.025)


def prism(name, pts_front, y0, y1, material, parent=None, bone=None):
    verts=[(x,y0,z) for x,z in pts_front]+[(x,y1,z) for x,z in pts_front]
    n=len(pts_front); faces=[]
    faces.append(tuple(range(n))); faces.append(tuple(range(n,2*n)))
    for i in range(n):
        j=(i+1)%n; faces.append((i,j,n+j,n+i))
    me=bpy.data.meshes.new(name+'Mesh'); me.from_pydata(verts,[],faces); me.update()
    o=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(o)
    return finish(o,material,name,parent,bone,0.025)


clear_scene()

navy = mat('Cloth_Navy', (0.015,0.045,0.13), 0.05, 0.38)
blue = mat('Armor_RoyalBlue', (0.025,0.13,0.38), 0.72, 0.22)
gold = mat('Trim_Gold', (0.75,0.38,0.055), 0.88, 0.2)
dark_gold = mat('Gold_Shadow', (0.22,0.085,0.018), 0.7, 0.25)
leather = mat('Leather', (0.055,0.022,0.012), 0.05, 0.38)
skin = mat('Skin', (0.57,0.28,0.17), 0.0, 0.48)
hair = mat('Hair', (0.018,0.009,0.006), 0.0, 0.32)
white = mat('EyeWhite', (0.72,0.72,0.67), 0.0, 0.25)
cyan = mat('Arcane_Crystal', (0.0,0.45,1.0), 0.18, 0.12, (0.0,0.55,1.0), 7.0)
black = mat('Pupil', (0.001,0.003,0.006), 0.0, 0.18)

# Realistic MakeHuman/MPFB body and game-ready deformation rig. The former
# procedural body primitives have been removed; only costume/prop meshes are
# authored below and attached to this skeleton.
HumanService = mpfb_symbol('mpfb.services.humanservice', 'HumanService')
HumanObjectProperties = mpfb_symbol('mpfb.entities.objectproperties', 'HumanObjectProperties')
TargetService = mpfb_symbol('mpfb.services.targetservice', 'TargetService')
human = HumanService.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True, feet_on_ground=True, scale=0.1)
human.name = 'BlueGoldMage_Body'
for prop,value in [('gender',1.0),('age',0.42),('muscle',0.62),('weight',0.42),('proportions',0.72),('caucasian',0.35),('asian',0.65),('african',0.0)]:
    HumanObjectProperties.set_value(prop, value, entity_reference=human)
TargetService.reapply_macro_details(human)
rig = HumanService.add_builtin_rig(human, 'game_engine')
rig.name='RIG_BlueGoldMage'
rig.data.name='BlueGoldMage_Skeleton'
rig.show_in_front=True
rig.scale=(1.72,1.72,1.72)
bpy.context.view_layer.objects.active=rig
rig.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
rig.select_set(False)
human.data.materials.clear()
human.data.materials.append(skin)
if not os.path.isfile(EYES_PATH):
    raise RuntimeError('Missing MakeHuman CC0 eye asset: ' + EYES_PATH)
eyes = HumanService.add_mhclo_asset(
    EYES_PATH,
    human,
    asset_type='Eyes',
    subdiv_levels=0,
    material_type='GAMEENGINE',
    set_up_rigging=True,
    interpolate_weights=True,
)
eyes.name = 'BlueGoldMage_Eyes'
# The rig scale is applied before body-part import, while the already-parented
# basemesh keeps that scale on its child transform. Match it explicitly so the
# imported eyes sit in the scaled head rather than at the original 1.66 m body.
eyes.scale = human.scale.copy()
hair_mesh = HumanService.add_mhclo_asset(
    HAIR_PATH, human, asset_type='Hair', subdiv_levels=0,
    material_type='NONE', set_up_rigging=True, interpolate_weights=True,
)
hair_mesh.name = 'BlueGoldMage_Hair'
hair_mesh.scale = human.scale.copy()
eyebrows_mesh = HumanService.add_mhclo_asset(
    EYEBROWS_PATH, human, asset_type='Eyebrows', subdiv_levels=0,
    material_type='NONE', set_up_rigging=True, interpolate_weights=True,
)
eyebrows_mesh.name = 'BlueGoldMage_Eyebrows'
eyebrows_mesh.scale = human.scale.copy()
protected_meshes = {human, eyes, hair_mesh, eyebrows_mesh}

# Importing an MHCLO asset purges unused Blender data blocks. Recreate the
# costume palette now that every retained MakeHuman body part is present.
navy = mat('Cloth_Navy', (0.015,0.045,0.13), 0.05, 0.38)
blue = mat('Armor_RoyalBlue', (0.025,0.13,0.38), 0.72, 0.22)
gold = mat('Trim_Gold', (0.75,0.38,0.055), 0.88, 0.2)
dark_gold = mat('Gold_Shadow', (0.22,0.085,0.018), 0.7, 0.25)
leather = mat('Leather', (0.055,0.022,0.012), 0.05, 0.38)
hair = mat('Hair', (0.018,0.009,0.006), 0.0, 0.32)
cyan = mat('Arcane_Crystal', (0.0,0.45,1.0), 0.18, 0.12, (0.0,0.55,1.0), 7.0)
for asset in (hair_mesh, eyebrows_mesh):
    asset.data.materials.clear()
    asset.data.materials.append(hair)

# Use the anatomical mesh itself as the fitted cloth underlayer. This keeps a
# believable torso and leg silhouette and avoids intersecting primitive
# "barrel" armor while ensuring skin never flashes through clothing gaps.
human.data.materials.append(navy)
for poly in human.data.polygons:
    center = sum((human.data.vertices[i].co for i in poly.vertices), Vector()) / len(poly.vertices)
    world_center = human.matrix_world @ center
    torso_cloth = 1.02 < world_center.z < 2.43 and abs(world_center.x) < .72
    leg_cloth = .28 < world_center.z <= 1.42 and abs(world_center.x) < .52
    if torso_cloth or leg_cloth:
        poly.material_index = 1

# The torso uses the fitted cloth material on the anatomical basemesh; armor
# is layered only as trims, pauldrons and bracers like the supplied concept.
cube('Chest_Gold_V',(0,-.225,2.02),(.055,.035,.32),gold,rig,'chest',.025,rot=(0.0,0.0,math.radians(32)))
cube('Chest_Gold_V2',(0,-.225,2.02),(.055,.035,.32),gold,rig,'chest',.025,rot=(0.0,0.0,math.radians(-32)))
crystal('Chest_Gem',(0,-.29,1.91),(.12,.075,.14),cyan,rig,'chest')
cyl('Belt',(0,0,1.25),.38,.13,leather,rig,'pelvis',vertices=16)
crystal('Belt_Gem',(0,-.39,1.25),(.105,.065,.12),cyan,rig,'pelvis')

# Coat tails and cape panels
for side in (-1,1):
    prism(f'CoatTail_{side}',[(.0,1.28),(.34,1.22),(.5,.26),(.18,.07)],-.12,.10,navy,rig,'pelvis').scale.x=side
    prism(f'CoatTrim_{side}',[(.31,1.19),(.37,1.17),(.5,.26),(.45,.22)],-.145,.12,gold,rig,'pelvis').scale.x=side
cape_pts=[(.0,2.16),(.5,2.02),(.63,.25),(.15,.08)]
cape1=prism('Cape_L',cape_pts,.15,.205,navy,rig,'cape.L'); cape1.scale.x=1
cape2=prism('Cape_R',cape_pts,.15,.205,navy,rig,'cape.R'); cape2.scale.x=-1
for side in (-1,1):
    prism(f'Cape_Edge_{side}',[(.47,1.98),(.54,1.96),(.63,.25),(.56,.22)],.13,.225,gold,rig,'cape.L' if side==1 else 'cape.R').scale.x=side

# Arms, gauntlets, shoulder pauldrons
for side,label in ((1,'L'),(-1,'R')):
    upperbone=f'upper_arm.{label}'; forebone=f'forearm.{label}'; handbone=f'hand.{label}'
    upper_start,upper_end=bone_points(rig,upperbone)
    fore_start,fore_end=bone_points(rig,forebone)
    hand_start,hand_end=bone_points(rig,handbone)
    cyl_between(f'Sleeve_{label}',upper_start.lerp(upper_end,.08),upper_end,.125,navy,rig,upperbone,vertices=28)
    cone_between(f'Bracer_{label}',fore_start.lerp(fore_end,.20),fore_end,.085,.118,blue,rig,forebone,vertices=28)
    cyl_between(f'Glove_{label}',hand_start,hand_end,.092,leather,rig,handbone,vertices=24)
    # Three overlapping shoulder plates create the layered concept silhouette.
    shoulder_axis=(upper_end-upper_start).normalized()
    for layer,(offset,sx,sz) in enumerate(((0.02,.19,.075),(.11,.155,.062),(.19,.12,.050))):
        center=upper_start+shoulder_axis*offset+Vector((0,-.025,.035-layer*.015))
        sphere(f'Pauldron_{label}_{layer}',center,(sx,.15,sz),blue,rig,upperbone,seg=32,rings=18)
        cube(f'PauldronGold_{label}_{layer}',center+Vector((0,-.145,0)),(.10,.014,.014),gold,rig,upperbone,.01,rot=(0,0,math.radians(-8*side)))
    crystal(f'BracerGem_{label}',fore_start.lerp(fore_end,.62)+Vector((0,-.13,0)),(.055,.035,.075),cyan,rig,forebone)

# Legs, plated boots
for side,label in ((1,'L'),(-1,'R')):
    thighbone=f'thigh.{label}'; shinbone=f'shin.{label}'; footbone=f'foot.{label}'
    thigh_start,thigh_end=bone_points(rig,thighbone)
    shin_start,shin_end=bone_points(rig,shinbone)
    foot_start,foot_end=bone_points(rig,footbone)
    cone_between(f'Trouser_{label}',thigh_start.lerp(thigh_end,.03),thigh_end,.165,.19,navy,rig,thighbone,vertices=28)
    cone_between(f'Greave_{label}',shin_start.lerp(shin_end,.08),shin_end,.105,.135,blue,rig,shinbone,vertices=28)
    cyl_between(f'BootAnkle_{label}',foot_start,foot_end,.13,leather,rig,footbone,vertices=28,bevel=.025)
    cube(f'BootToe_{label}',foot_end+Vector((0,-.10,.015)),(.14,.20,.095),leather,rig,footbone,.055)
    crystal(f'KneeGem_{label}',shin_start+Vector((0,-.15,-.04)),(.06,.035,.08),cyan,rig,shinbone)

# Staff parented to right hand; its local motion follows arm animation.
cyl('Staff_Shaft',(-1.12,0,1.45),.045,2.55,leather,rig,'hand.R',vertices=12)
cyl('Staff_GoldSpine',(-1.12,0,2.73),.085,.34,gold,rig,'hand.R',vertices=10)
crystal('Staff_Crystal',(-1.12,0,3.08),(.175,.175,.34),cyan,rig,'hand.R')
for side in (-1,1):
    cone(f'Staff_Prong_{side}',(-1.12+.17*side,0,2.87),.07,.015,.58,gold,rig,'hand.R',vertices=8,rot=(0,math.radians(20*side),0))
cyl('Staff_Grip',(-1.12,0,1.5),.065,.5,dark_gold,rig,'hand.R',vertices=10)

# Tailoring details follow the concept's cloth tunic rather than stacking
# rectangular abdominal armor plates across the torso.
for side in (-1, 1):
    cube(f'Tunic_Vertical_Trim_{side}',(.205*side,-.155,1.66),(.018,.012,.31),gold,rig,'spine',.008,rot=(0,0,math.radians(3*side)))
cube('Tunic_Waist_Trim',(0,-.166,1.37),(.27,.012,.018),gold,rig,'spine',.008)
for side in (-1,1):
    # Raised collar, chest edge and cape embroidery bands.
    cube(f'Raised_Collar_{side}',(.19*side,-.10,2.24),(.16,.055,.065),blue,rig,'chest',.025,rot=(0,math.radians(-12*side),math.radians(18*side)))
    cube(f'Chest_Edge_{side}',(.295*side,-.205,1.98),(.025,.018,.25),gold,rig,'chest',.012,rot=(0,0,math.radians(6*side)))
    for i in range(4):
        cube(f'Cape_Embroidery_{side}_{i}',((.24+.075*i)*side,.232,1.82-.31*i),(.012,.012,.18),gold,rig,'cape.L' if side==1 else 'cape.R',.006,rot=(0,0,math.radians(3*side)))

# Name collection for export selection
char_objs=[o for o in bpy.context.scene.objects if o.type in {'MESH','ARMATURE'}]
for o in char_objs:
    o['asset_role']='BlueGoldMage'

# Distribute a restrained level of surface subdivision by source complexity so
# the exported evaluated mesh stays close to the production target of 50k
# triangles. The asset is intended for the hall preview and a mid-poly hero
# model, not a cinematic close-up.
deps=bpy.context.evaluated_depsgraph_get()
mesh_cost=[]
for o in char_objs:
    if o.type != 'MESH' or o in protected_meshes:
        continue
    eo=o.evaluated_get(deps); me=eo.to_mesh(); me.calc_loop_triangles()
    mesh_cost.append((o,len(me.loop_triangles)))
    eo.to_mesh_clear()
TARGET_TRIANGLES = 50000
base_total=sum(t for _,t in mesh_cost)
upgrade_budget=max(0,TARGET_TRIANGLES-base_total)
upgrade=set(); running=0
for o,t in sorted(mesh_cost,key=lambda item:item[1],reverse=True):
    if o in protected_meshes:
        continue
    if running + t <= upgrade_budget:
        upgrade.add(o.name); running += t
for o,t in mesh_cost:
    if o.name in upgrade:
        dense=o.modifiers.new('Target Surface Subdivision','SUBSURF')
        material_name=o.data.materials[0].name if o.data.materials else ''
        dense.subdivision_type='CATMULL_CLARK' if material_name in {'Skin','Hair'} else 'SIMPLE'
        dense.levels=1
        dense.render_levels=1

# Commit bevel and density modifiers so both the .blend edit mesh and exported
# GLB contain the requested topology instead of relying on viewport evaluation.
for o in char_objs:
    if o.type != 'MESH' or o in protected_meshes:
        continue
    bpy.context.view_layer.objects.active=o
    o.select_set(True)
    for modifier in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    o.select_set(False)

# Keep the authored bevels and medium-poly silhouette, then reduce only when
# the accumulated mesh cost exceeds the production budget. Applying one
# proportional collapse pass per mesh keeps materials, armature parenting and
# the separate staff intact while bringing the exported asset near 50k tris.
deps=bpy.context.evaluated_depsgraph_get()
current_triangles=0
protected_triangles=0
for o in char_objs:
    if o.type != 'MESH':
        continue
    eo=o.evaluated_get(deps); me=eo.to_mesh(); me.calc_loop_triangles()
    object_triangles=len(me.loop_triangles)
    current_triangles += object_triangles
    if o in protected_meshes:
        protected_triangles += object_triangles
    eo.to_mesh_clear()
if current_triangles > TARGET_TRIANGLES:
    costume_triangles=max(1,current_triangles-protected_triangles)
    costume_budget=max(1000,TARGET_TRIANGLES-protected_triangles)
    collapse_ratio=min(1.0,float(costume_budget) / float(costume_triangles))
    for o in char_objs:
        if o.type != 'MESH' or o in protected_meshes:
            continue
        decimate=o.modifiers.new('Production Triangle Budget','DECIMATE')
        decimate.decimate_type='COLLAPSE'
        decimate.ratio=collapse_ratio
        bpy.context.view_layer.objects.active=o
        o.select_set(True)
        bpy.ops.object.modifier_apply(modifier=decimate.name)
        o.select_set(False)

# Pose defaults and animation actions
bpy.context.view_layer.objects.active=rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='POSE')
for pb in rig.pose.bones:
    pb.rotation_mode='XYZ'
bpy.ops.object.mode_set(mode='OBJECT')

def make_action(name, length, keys):
    rig.animation_data_create()
    act=bpy.data.actions.new(name=name)
    act.use_fake_user=True
    rig.animation_data.action=act
    for frame, transforms in keys:
        for bn, rot in transforms.items():
            pb=rig.pose.bones[BONE_MAP.get(bn, bn)]
            pb.rotation_euler=rot
            pb.keyframe_insert(data_path='rotation_euler',frame=frame,group=bn)
    # make every curve cyclic and linear/Bezier-friendly
    # Blender 5.x stores curves in layered action slots; the exporter reads all
    # compatible actions directly, so no legacy fcurve/NLA access is required.
    rig.animation_data.action=None
    return act

Z=(0.0,0.0,0.0)
make_action('Idle_Breathe',80,[
    (1,{'spine':Z,'chest':Z,'head':Z,'upper_arm.L':Z,'upper_arm.R':Z,'cape.L':Z,'cape.R':Z}),
    (21,{'spine':(math.radians(1.4),0,0),'chest':(math.radians(-1.2),0,0),'head':(math.radians(-1),0,0),'upper_arm.L':(0,0,math.radians(1.6)),'upper_arm.R':(0,0,math.radians(-1.6)),'cape.L':(math.radians(2),0,math.radians(1)),'cape.R':(math.radians(2),0,math.radians(-1))}),
    (41,{'spine':Z,'chest':Z,'head':Z,'upper_arm.L':Z,'upper_arm.R':Z,'cape.L':Z,'cape.R':Z}),
    (61,{'spine':(math.radians(-.8),0,0),'chest':(math.radians(.7),0,0),'head':(math.radians(.5),0,0),'upper_arm.L':(0,0,math.radians(-.8)),'upper_arm.R':(0,0,math.radians(.8)),'cape.L':(math.radians(-1),0,0),'cape.R':(math.radians(-1),0,0)}),
    (80,{'spine':Z,'chest':Z,'head':Z,'upper_arm.L':Z,'upper_arm.R':Z,'cape.L':Z,'cape.R':Z})])

make_action('Idle_LookAround',120,[
    (1,{'head':Z,'neck':Z,'chest':Z}),
    (30,{'head':(math.radians(-3),math.radians(2),math.radians(18)),'neck':(0,0,math.radians(5)),'chest':(0,0,math.radians(2))}),
    (55,{'head':Z,'neck':Z,'chest':Z}),
    (85,{'head':(math.radians(2),math.radians(-2),math.radians(-15)),'neck':(0,0,math.radians(-4)),'chest':(0,0,math.radians(-2))}),
    (120,{'head':Z,'neck':Z,'chest':Z})])

make_action('Idle_StaffFocus',96,[
    (1,{'upper_arm.R':Z,'forearm.R':Z,'hand.R':Z,'head':Z,'chest':Z}),
    (24,{'upper_arm.R':(0,math.radians(-7),math.radians(-5)),'forearm.R':(0,math.radians(-9),0),'hand.R':(0,math.radians(6),0),'head':(math.radians(-4),0,math.radians(-7)),'chest':(0,0,math.radians(-2))}),
    (48,{'upper_arm.R':(0,math.radians(-12),math.radians(-8)),'forearm.R':(0,math.radians(-14),0),'hand.R':(0,math.radians(10),0),'head':(math.radians(-6),0,math.radians(-10)),'chest':(0,0,math.radians(-3))}),
    (72,{'upper_arm.R':(0,math.radians(-7),math.radians(-5)),'forearm.R':(0,math.radians(-9),0),'hand.R':(0,math.radians(6),0),'head':(math.radians(-4),0,math.radians(-7)),'chest':(0,0,math.radians(-2))}),
    (96,{'upper_arm.R':Z,'forearm.R':Z,'hand.R':Z,'head':Z,'chest':Z})])

scene=bpy.context.scene
scene.frame_start=1; scene.frame_end=120; scene.render.fps=24
scene['Animation_List']='Idle_Breathe (80f); Idle_LookAround (120f); Idle_StaffFocus (96f)'
scene['Design_Reference']='Blue-gold fantasy mage based on supplied UI concept art'

# Preview floor, camera and lights (kept in blend, not exported)
bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=1.65,depth=.12,location=(0,0,-.08))
floor=finish(bpy.context.object,dark_gold,'PREVIEW_Plinth',bevel=.04)
bpy.ops.object.camera_add(location=(2.7,-7.2,3.35))
cam=bpy.context.object; cam.name='PREVIEW_Camera'; scene.camera=cam
def point_camera(obj, target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
point_camera(cam,(0,0,1.48)); cam.data.lens=58
for name,loc,energy,color,size in [
    ('Key',(3.8,-4.5,6),1250,(0.55,0.72,1.0),4.0),
    ('Rim',(-4,1.5,4),1450,(0.0,0.35,1.0),3.0),
    ('Warm',(-2.5,-3,2.8),850,(1.0,0.42,0.12),2.2)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    l=bpy.context.object; l.name='PREVIEW_'+name; l.data.energy=energy; l.data.color=color; l.data.shape='DISK'; l.data.size=size; point_camera(l,(0,0,1.5))

scene.render.engine='BLENDER_EEVEE'
scene.render.resolution_x=720; scene.render.resolution_y=900; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'; scene.render.filepath=PREVIEW_PATH
scene.render.film_transparent=False
scene.world.color=(0.004,0.008,0.018)
scene.view_settings.look='AgX - Medium High Contrast'

# Face camera and use neutral pose
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)

# Export only character assets
bpy.ops.object.select_all(action='DESELECT')
for o in char_objs: o.select_set(True)
bpy.context.view_layer.objects.active=rig
bpy.ops.export_scene.gltf(filepath=GLB_PATH,export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='ACTIONS',export_materials='EXPORT')

# Render and report polygon totals
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.render.render(write_still=True)
poly=sum(len(o.data.polygons) for o in char_objs if o.type=='MESH')
tri=0
deps=bpy.context.evaluated_depsgraph_get()
for o in char_objs:
    if o.type=='MESH':
        eo=o.evaluated_get(deps); me=eo.to_mesh(); me.calc_loop_triangles(); tri+=len(me.loop_triangles); eo.to_mesh_clear()
print(f'ASSET_REPORT blend={BLEND_PATH} glb={GLB_PATH} preview={PREVIEW_PATH} polygons={poly} triangles={tri} actions={len(bpy.data.actions)}')
