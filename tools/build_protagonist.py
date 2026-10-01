"""Rebuild the blue-gold mage protagonist inside Blender's bpy interpreter.

The geometry is original procedural modeling. Palette, silhouette, gem layout
and gold trim follow art/references/protagonist_concept.png; no pixels are copied.

Run:
    blender --background --factory-startup --python tools/build_protagonist.py
"""
from __future__ import annotations

from pathlib import Path
import json
import math
import sys


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "art"
OUTPUT = ROOT / "client/assets/characters"


def srgb(r, g, b):
    def channel(value):
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
    return (channel(r), channel(g), channel(b))


def main():
    import bmesh
    import bpy
    from mathutils import Vector

    ART.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.collections):
        for item in list(block):
            block.remove(item)

    scene = bpy.context.scene
    col = bpy.data.collections.new("Protagonist")
    scene.collection.children.link(col)
    extras = bpy.data.collections.new("Studio")
    scene.collection.children.link(extras)

    def link(obj, parent=None, collection=col):
        for other in list(obj.users_collection):
            other.objects.unlink(obj)
        collection.objects.link(obj)
        if parent is not None:
            obj.parent = parent
        return obj

    root = bpy.data.objects.new("Protagonist", None)
    link(root)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.2

    def mat(name, color, metallic=0.0, roughness=0.5, emission=0.0,
            emission_color=None, transmission=0.0, subsurface=0.0, spec=0.5):
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        shader = material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*color, 1)
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Specular IOR Level"].default_value = spec
        if emission:
            shader.inputs["Emission Color"].default_value = (*(emission_color or color), 1)
            shader.inputs["Emission Strength"].default_value = emission
        if transmission:
            shader.inputs["Transmission Weight"].default_value = transmission
            shader.inputs["IOR"].default_value = 1.52
        if subsurface:
            shader.inputs["Subsurface Weight"].default_value = subsurface
            shader.inputs["Subsurface Radius"].default_value = (0.8, 0.25, 0.15)
        material.diffuse_color = (*color, 1)
        return material

    cloth = mat("Mage cloth", srgb(0.14, 0.36, 0.78), roughness=0.46, spec=0.4)
    cloth_dark = mat("Cape inner", srgb(0.08, 0.18, 0.48), roughness=0.5)
    gold = mat("Armor gold", srgb(0.89, 0.68, 0.22), metallic=1.0, roughness=0.25, spec=1.0)
    gem = mat("Ice gem", srgb(0.22, 0.72, 1.0), roughness=0.08, emission=1.6,
              emission_color=srgb(0.25, 0.78, 1.0), transmission=0.2, spec=1.0)
    crystal = mat("Staff crystal", srgb(0.40, 0.84, 1.0), roughness=0.06, emission=2.2,
                  emission_color=srgb(0.45, 0.88, 1.0), transmission=0.28, spec=1.0)
    skin = mat("Skin", srgb(0.83, 0.62, 0.50), roughness=0.44, subsurface=0.18, spec=0.4)
    lip = mat("Lip", srgb(0.68, 0.36, 0.32), roughness=0.36, subsurface=0.08)
    brow = mat("Brow", srgb(0.10, 0.06, 0.04), roughness=0.48)
    eye_white = mat("Eye white", srgb(0.95, 0.95, 0.93), roughness=0.2)
    iris = mat("Iris", srgb(0.28, 0.16, 0.10), roughness=0.16)
    pupil = mat("Pupil", srgb(0.03, 0.02, 0.02), roughness=0.1)
    hair = mat("Hair", srgb(0.16, 0.09, 0.05), roughness=0.36)
    hair_dark = mat("Hair shadow", srgb(0.08, 0.045, 0.025), roughness=0.48)
    leather = mat("Boot leather", srgb(0.38, 0.22, 0.11), roughness=0.52)
    leather_dark = mat("Boot sole", srgb(0.16, 0.09, 0.05), roughness=0.6)
    pants = mat("Pants", srgb(0.10, 0.10, 0.12), roughness=0.56)
    glove = mat("Glove", srgb(0.07, 0.06, 0.06), roughness=0.46)
    wood = mat("Staff wood", srgb(0.30, 0.16, 0.08), roughness=0.5)

    def select(obj):
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        return obj

    def shade(obj, angle=40):
        select(obj)
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
        return obj

    def apply_scale(obj):
        select(obj)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return obj

    def subsurf(obj, levels=2, bevel=0.0, angle=40):
        if bevel:
            modifier = obj.modifiers.new("Bevel", "BEVEL")
            modifier.width = bevel
            modifier.segments = 3
            modifier.limit_method = "ANGLE"
            modifier.angle_limit = math.radians(38)
        if levels:
            modifier = obj.modifiers.new("Subsurf", "SUBSURF")
            modifier.levels = levels
            modifier.render_levels = max(levels, 2)
        shade(obj, angle)
        return obj

    def mesh_obj(name, verts, faces, material, location=(0, 0, 0), parent=root):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        obj.location = location
        link(obj, parent)
        obj.data.materials.append(material)
        return obj

    def cube(name, location, size, material, parent=root, bevel=0.01, sub=1, rot=None):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.name = name
        if rot:
            obj.rotation_euler = rot
        obj.scale = size
        apply_scale(obj)
        link(obj, parent)
        obj.data.materials.append(material)
        return subsurf(obj, sub, bevel)

    def sphere(name, location, radius, material, parent=root, sub=1, scale=None, rot=None):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=location)
        obj = bpy.context.object
        obj.name = name
        if rot:
            obj.rotation_euler = rot
        if scale:
            obj.scale = scale
            apply_scale(obj)
        link(obj, parent)
        obj.data.materials.append(material)
        return subsurf(obj, sub, 0)

    def ico(name, location, radius, material, parent=root, sub=1, scale=None, rot=None):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=radius, location=location)
        obj = bpy.context.object
        obj.name = name
        if rot:
            obj.rotation_euler = rot
        if scale:
            obj.scale = scale
            apply_scale(obj)
        link(obj, parent)
        obj.data.materials.append(material)
        return subsurf(obj, sub, 0)

    def cylinder(name, location, radius, depth, material, parent=root, verts=24, bevel=0.006, sub=1, rot=None, scale=None):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=location)
        obj = bpy.context.object
        obj.name = name
        if rot:
            obj.rotation_euler = rot
        if scale:
            obj.scale = scale
        apply_scale(obj)
        link(obj, parent)
        obj.data.materials.append(material)
        return subsurf(obj, sub, bevel)

    def torus(name, location, major, minor, material, parent=root, rot=None):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=location,
                                         major_segments=28, minor_segments=10)
        obj = bpy.context.object
        obj.name = name
        if rot:
            obj.rotation_euler = rot
        link(obj, parent)
        obj.data.materials.append(material)
        return subsurf(obj, 1, 0)

    def cone(name, location, radius1, depth, material, parent=root, radius2=0.0, rot=None, verts=8):
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=radius1, radius2=radius2, depth=depth, location=location)
        obj = bpy.context.object
        obj.name = name
        if rot:
            obj.rotation_euler = rot
        link(obj, parent)
        obj.data.materials.append(material)
        return subsurf(obj, 1, 0.004)

    def octahedron(name, location, rx, ry, rz, material, parent=root, sub=1, rot=None):
        verts = [(0, 0, rz), (rx, 0, 0), (0, ry, 0), (-rx, 0, 0), (0, -ry, 0), (0, 0, -rz)]
        faces = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4)]
        obj = mesh_obj(name, verts, faces, material, location, parent)
        if rot:
            obj.rotation_euler = rot
        return subsurf(obj, sub, 0.0, 28)

    def diamond_plate(name, location, width, height, depth, material, parent=root, rot=None):
        w, h, d = width / 2, height / 2, depth / 2
        verts = [(0, -d, h), (w, -d, 0), (0, -d, -h), (-w, -d, 0),
                 (0, d, h), (w, d, 0), (0, d, -h), (-w, d, 0)]
        faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        obj = mesh_obj(name, verts, faces, material, location, parent)
        if rot:
            obj.rotation_euler = rot
        return subsurf(obj, 1, 0.002)

    def ice_gem(name, location, size=0.04, parent=root, rot=None, tall=1.25, outward=0.012):
        loc = Vector(location)
        loc.y -= outward
        frame = diamond_plate(name + " frame", loc, size * 2.15, size * 2.6 * tall, 0.014, gold, parent, rot)
        stone = octahedron(name, loc + Vector((0, -0.008, 0)), size * 0.88, size * 0.18, size * 1.2 * tall, gem, parent, 1, rot)
        return stone, frame

    # --- Head -----------------------------------------------------------------
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.118, location=(0, -0.02, 1.625))
    head = bpy.context.object
    head.name = "Head"
    bm = bmesh.new()
    bm.from_mesh(head.data)
    for vert in bm.verts:
        x, y, z = vert.co
        z *= 1.14
        x *= 0.92
        y *= 1.06
        if z < -0.01:
            squeeze = 1 - 0.22 * min(1.0, (-0.01 - z) / 0.12)
            x *= squeeze
            if y < 0:
                y -= 0.01 * min(1.0, (-0.01 - z) / 0.10)
        if y < -0.04:
            y = -0.04 + (y + 0.04) * 0.72
        if z > 0.04 and y < 0:
            y *= 0.94
        vert.co = (x, y, z)
    bm.to_mesh(head.data)
    bm.free()
    link(head, root)
    head.data.materials.append(skin)
    subsurf(head, 2, 0.0)

    cylinder("Neck", (0, 0.0, 1.468), 0.046, 0.11, skin, bevel=0.01, sub=2)

    def eyeball(tag, x):
        sphere(f"Eye white {tag}", (x, -0.118, 1.616), 0.016, eye_white, sub=0, scale=(1.05, 0.38, 0.95))
        sphere(f"Iris {tag}", (x, -0.126, 1.616), 0.0088, iris, sub=0, scale=(1.05, 0.32, 1.0))
        sphere(f"Pupil {tag}", (x, -0.130, 1.616), 0.0044, pupil, sub=0, scale=(1.0, 0.28, 1.0))
        sphere(f"Catchlight {tag}", (x + 0.004, -0.132, 1.622), 0.0018, eye_white, sub=0)
        cube(f"Lid upper {tag}", (x, -0.118, 1.628), (0.034, 0.011, 0.005), skin, bevel=0.003, sub=2, rot=(0.08, 0, 0))
        cube(f"Lid lower {tag}", (x, -0.118, 1.604), (0.032, 0.009, 0.004), skin, bevel=0.002, sub=2, rot=(-0.06, 0, 0))

    eyeball("L", 0.033)
    eyeball("R", -0.033)
    cube("Brow L", (0.034, -0.116, 1.640), (0.038, 0.008, 0.005), brow, bevel=0.002, sub=1, rot=(0.08, 0, 0.16))
    cube("Brow R", (-0.034, -0.116, 1.640), (0.038, 0.008, 0.005), brow, bevel=0.002, sub=1, rot=(0.08, 0, -0.16))
    sphere("Nose", (0, -0.122, 1.572), 0.015, skin, sub=1, scale=(0.48, 1.05, 0.82))
    cube("Bridge", (0, -0.112, 1.592), (0.014, 0.028, 0.034), skin, bevel=0.006, sub=2)
    cube("Upper lip", (0, -0.116, 1.530), (0.036, 0.011, 0.006), lip, bevel=0.003, sub=2)
    cube("Lower lip", (0, -0.114, 1.521), (0.030, 0.010, 0.005), lip, bevel=0.003, sub=2)
    cube("Mouth line", (0, -0.122, 1.525), (0.026, 0.003, 0.002), brow, bevel=0.001, sub=0)
    for tag, x in (("L", 0.108), ("R", -0.108)):
        sphere(f"Ear {tag}", (x, 0.0, 1.598), 0.026, skin, sub=1,
               scale=(0.32, 0.68, 1.02), rot=(0.12, 0.4 if x > 0 else -0.4, 0))

    # --- Hair: cap plus swept locks ------------------------------------------
    bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=14, radius=0.128, location=(0, -0.005, 1.655))
    cap = bpy.context.object
    cap.name = "Hair cap"
    bm = bmesh.new()
    bm.from_mesh(cap.data)
    drop = []
    for vert in bm.verts:
        vert.co.x *= 1.02
        vert.co.y *= 1.10
        vert.co.z *= 0.82
        # Keep the helmet; cut only the visor over the face.
        if vert.co.y < -0.015 and vert.co.z < 0.03:
            drop.append(vert)
    bmesh.ops.delete(bm, geom=drop, context="VERTS")
    bm.to_mesh(cap.data)
    bm.free()
    link(cap, root)
    cap.data.materials.append(hair)
    subsurf(cap, 2, 0.0)

    locks = [
        ("Bang C", (0.01, -0.10, 1.715), 0.038, (1.25, 0.45, 0.28), (0.75, 0.04, 0.06), hair),
        ("Bang L", (0.05, -0.09, 1.71), 0.034, (0.95, 0.45, 0.32), (0.65, 0.1, 0.4), hair),
        ("Bang R", (-0.04, -0.085, 1.712), 0.032, (0.9, 0.42, 0.3), (0.6, -0.06, -0.28), hair),
        ("Forelock", (0.02, -0.06, 1.74), 0.04, (0.95, 0.7, 0.38), (0.4, 0.15, 0.2), hair),
        ("Crown C", (0.0, 0.01, 1.76), 0.072, (1.15, 1.05, 0.36), (0.05, 0.0, 0.0), hair),
        ("Crown L", (0.05, 0.02, 1.75), 0.06, (1.05, 0.95, 0.34), (0.08, 0.18, 0.08), hair),
        ("Crown R", (-0.04, 0.03, 1.748), 0.058, (1.0, 1.0, 0.32), (0.06, -0.12, -0.06), hair),
        ("Side L", (0.11, -0.02, 1.64), 0.05, (0.48, 0.85, 1.15), (0.12, 0.45, 0.05), hair),
        ("Side R", (-0.105, -0.01, 1.645), 0.048, (0.46, 0.8, 1.1), (0.1, -0.4, 0.0), hair),
        ("Temple L", (0.09, -0.07, 1.63), 0.032, (0.55, 0.7, 0.8), (0.45, 0.5, 0.18), hair),
        ("Temple R", (-0.085, -0.06, 1.635), 0.03, (0.5, 0.65, 0.75), (0.4, -0.45, -0.12), hair),
        ("Back", (0.0, 0.11, 1.66), 0.068, (1.15, 0.58, 0.8), (-0.15, 0.0, 0.0), hair),
        ("Back L", (0.07, 0.10, 1.63), 0.048, (0.75, 0.55, 0.85), (0.18, 0.15, 0.0), hair_dark),
        ("Back R", (-0.07, 0.10, 1.63), 0.048, (0.75, 0.55, 0.85), (0.18, -0.15, 0.0), hair_dark),
        ("Nape", (0.0, 0.08, 1.58), 0.036, (1.0, 0.42, 0.4), (0.35, 0.0, 0.0), hair_dark),
        ("Volume L", (0.08, 0.05, 1.70), 0.05, (0.75, 0.82, 0.5), (0.08, 0.22, 0.08), hair),
        ("Volume R", (-0.07, 0.06, 1.695), 0.048, (0.7, 0.78, 0.48), (0.06, -0.18, 0.0), hair),
        ("Sweep", (0.03, 0.0, 1.755), 0.036, (1.1, 0.72, 0.32), (0.4, 0.3, 0.35), hair),
    ]
    for name, loc, radius, scale, rot, material in locks:
        ico(name, loc, radius, material, sub=1, scale=scale, rot=rot)

    # --- Torso / collar / armor ----------------------------------------------
    cylinder("Torso", (0, 0.01, 1.22), 0.132, 0.40, cloth, verts=28, bevel=0.018, sub=2, scale=(1.12, 0.70, 1))
    cube("Chest", (0, -0.02, 1.28), (0.28, 0.15, 0.26), cloth, bevel=0.035, sub=2)
    cube("Waist", (0, 0.0, 1.04), (0.24, 0.13, 0.16), cloth, bevel=0.025, sub=2)
    cube("Pelvis", (0, 0.01, 0.92), (0.26, 0.14, 0.15), cloth, bevel=0.025, sub=2)
    cylinder("Collar", (0, 0.01, 1.445), 0.068, 0.085, cloth, verts=24, bevel=0.01, sub=2, scale=(1.08, 0.88, 1))
    torus("Collar gold", (0, 0.01, 1.488), 0.074, 0.009, gold)
    cube("Collar gold front", (0, -0.052, 1.45), (0.085, 0.016, 0.07), gold, bevel=0.006, sub=1)

    diamond_plate("Chest gold frame", (0, -0.098, 1.335), 0.145, 0.18, 0.028, gold)
    ice_gem("Chest gem", (0, -0.102, 1.35), 0.048, tall=1.15, outward=0.008)
    ice_gem("Collarbone L", (0.078, -0.09, 1.405), 0.022, tall=1.1, outward=0.01)
    ice_gem("Collarbone R", (-0.078, -0.09, 1.405), 0.022, tall=1.1, outward=0.01)
    cube("Sternum gold", (0, -0.092, 1.21), (0.03, 0.018, 0.15), gold, bevel=0.005, sub=1)
    cube("Coat edge L", (0.075, -0.082, 1.16), (0.012, 0.016, 0.36), gold, bevel=0.003, sub=1)
    cube("Coat edge R", (-0.075, -0.082, 1.16), (0.012, 0.016, 0.36), gold, bevel=0.003, sub=1)
    cube("Gold V L", (0.04, -0.086, 1.12), (0.016, 0.014, 0.11), gold, bevel=0.003, sub=1, rot=(0, 0.5, 0))
    cube("Gold V R", (-0.04, -0.086, 1.12), (0.016, 0.014, 0.11), gold, bevel=0.003, sub=1, rot=(0, -0.5, 0))

    cube("Belt", (0, 0.0, 0.975), (0.30, 0.17, 0.05), gold, bevel=0.008, sub=1)
    ice_gem("Belt gem", (0, -0.09, 0.975), 0.03, tall=1.05, outward=0.008)

    def hip_flap(tag, x):
        cube(f"Hip flap {tag}", (x, -0.06, 0.76), (0.105, 0.048, 0.36), cloth, bevel=0.018, sub=2)
        cube(f"Hip gold L {tag}", (x - 0.05, -0.086, 0.76), (0.012, 0.012, 0.36), gold, bevel=0.002, sub=1)
        cube(f"Hip gold R {tag}", (x + 0.05, -0.086, 0.76), (0.012, 0.012, 0.36), gold, bevel=0.002, sub=1)
        cube(f"Hip gold bottom {tag}", (x, -0.086, 0.585), (0.10, 0.012, 0.02), gold, bevel=0.002, sub=1)
        ice_gem(f"Hip gem {tag}", (x, -0.082, 0.62), 0.02, tall=1.15, outward=0.0)

    hip_flap("L", 0.085)
    hip_flap("R", -0.085)

    def pauldron(tag, x):
        sign = 1 if x > 0 else -1
        cube(f"Pauldron {tag}", (x, 0.0, 1.40), (0.16, 0.17, 0.10), cloth, bevel=0.028, sub=2)
        cube(f"Pauldron gold top {tag}", (x, 0.0, 1.452), (0.17, 0.18, 0.022), gold, bevel=0.008, sub=1)
        cube(f"Pauldron gold low {tag}", (x, 0.0, 1.348), (0.17, 0.18, 0.02), gold, bevel=0.008, sub=1)
        cube(f"Pauldron plate {tag}", (x + sign * 0.078, -0.01, 1.40), (0.03, 0.15, 0.08), gold, bevel=0.008, sub=1)
        ice_gem(f"Pauldron gem {tag}", (x + sign * 0.10, -0.03, 1.40), 0.024, tall=1.1,
                rot=(0, 0, math.radians(80 * sign)), outward=0.0)

    pauldron("L", 0.255)
    pauldron("R", -0.255)

    def arm(tag, x):
        sign = 1 if x > 0 else -1
        cylinder(f"Upper arm {tag}", (x, 0.02, 1.24), 0.05, 0.26, cloth, bevel=0.012, sub=2)
        torus(f"Bicep gold {tag}", (x, 0.02, 1.13), 0.056, 0.011, gold)
        cylinder(f"Forearm {tag}", (x, 0.015, 0.97), 0.04, 0.28, glove, bevel=0.01, sub=2)
        torus(f"Wrist gold {tag}", (x, 0.015, 0.845), 0.046, 0.01, gold)
        cube(f"Palm {tag}", (x, 0.0, 0.775), (0.065, 0.042, 0.09), glove, bevel=0.01, sub=2)
        for i, offset in enumerate((-0.022, -0.007, 0.008, 0.022)):
            cylinder(f"Finger {tag} {i}", (x + offset, -0.008, 0.705), 0.0085, 0.07, glove, verts=10, bevel=0.002, sub=1)
        cylinder(f"Thumb {tag}", (x + sign * 0.038, -0.018, 0.75), 0.01, 0.05, glove, verts=10, bevel=0.002, sub=1,
                 rot=(0.55, 0, sign * 0.75))

    arm("L", 0.22)
    arm("R", -0.22)

    for tag, x in (("L", 0.085), ("R", -0.085)):
        cylinder(f"Thigh {tag}", (x, 0.02, 0.70), 0.062, 0.38, pants, bevel=0.012, sub=2)
        cylinder(f"Shin {tag}", (x, 0.025, 0.46), 0.05, 0.22, pants, bevel=0.01, sub=2)
        cylinder(f"Boot shaft {tag}", (x, 0.03, 0.24), 0.056, 0.32, leather, bevel=0.012, sub=2)
        torus(f"Boot cuff {tag}", (x, 0.03, 0.39), 0.06, 0.011, gold)
        cube(f"Boot foot {tag}", (x, -0.03, 0.055), (0.095, 0.20, 0.08), leather, bevel=0.018, sub=2)
        cube(f"Boot toe {tag}", (x, -0.11, 0.048), (0.08, 0.07, 0.055), leather, bevel=0.014, sub=2)
        cube(f"Boot heel {tag}", (x, 0.065, 0.035), (0.078, 0.055, 0.045), leather_dark, bevel=0.008, sub=1)
        cube(f"Boot sole {tag}", (x, -0.02, 0.016), (0.10, 0.22, 0.022), leather_dark, bevel=0.006, sub=1)
        ice_gem(f"Boot gem {tag}", (x + (0.062 if x > 0 else -0.062), 0.01, 0.27), 0.018, tall=1.15, outward=0.0)

    # --- Cape stays on the back / sides --------------------------------------
    def cape_point(u, v, inflate=0.0, width_add=0.0):
        phi = (u - 0.5) * (2.15 + 1.15 * (1 - v))
        radius = 0.20 + 0.34 * (1 - v) + width_add + 0.04 * abs(u - 0.5) * (1 - v)
        x = radius * math.sin(phi)
        y = radius * math.cos(phi) + inflate
        z = 0.22 + 1.20 * v - 0.05 * math.cos(phi) * (1 - v)
        z += 0.05 * v * math.cos(phi)
        return x, y, z

    def make_cape(name, material, inflate=0.0, width_add=0.0):
        cols, rows = 19, 15
        verts = []
        faces = []
        for j in range(rows):
            v = j / (rows - 1)
            for i in range(cols):
                u = i / (cols - 1)
                verts.append(cape_point(u, v, inflate, width_add))
        for j in range(rows - 1):
            for i in range(cols - 1):
                a = j * cols + i
                faces.append((a, a + 1, a + cols + 1, a + cols))
        obj = mesh_obj(name, verts, faces, material)
        return subsurf(obj, 2, 0.0, 55)

    make_cape("Cape", cloth, inflate=0.02)
    make_cape("Cape lining", cloth_dark, inflate=0.004, width_add=-0.015)

    def strip_from_uv(name, uv_points, radius=0.009):
        points = [cape_point(u, v, inflate=0.028) for u, v in uv_points]
        verts = []
        faces = []
        ring = 6
        for index, (x, y, z) in enumerate(points):
            tangent = Vector(points[min(index + 1, len(points) - 1)]) - Vector(points[max(index - 1, 0)])
            if tangent.length < 1e-6:
                tangent = Vector((0, 0, 1))
            tangent.normalize()
            up = Vector((0, 0, 1) if abs(tangent.z) < 0.9 else (1, 0, 0))
            binormal = tangent.cross(up).normalized()
            normal = binormal.cross(tangent).normalized()
            for k in range(ring):
                angle = math.tau * k / ring
                offset = (binormal * math.cos(angle) + normal * math.sin(angle)) * radius
                verts.append((x + offset.x, y + offset.y, z + offset.z))
        for index in range(len(points) - 1):
            for k in range(ring):
                a = index * ring + k
                b = index * ring + (k + 1) % ring
                c = (index + 1) * ring + (k + 1) % ring
                d = (index + 1) * ring + k
                faces.append((a, b, c, d))
        obj = mesh_obj(name, verts, faces, gold)
        return subsurf(obj, 1, 0.0)

    left_uv = [(0.0, j / 12) for j in range(13)]
    right_uv = [(1.0, j / 12) for j in range(13)]
    hem_uv = [(i / 16, 0.0) for i in range(17)]
    strip_from_uv("Cape gold L", left_uv)
    strip_from_uv("Cape gold R", right_uv)
    strip_from_uv("Cape gold hem", hem_uv, 0.011)

    back_pt = cape_point(0.5, 0.12, inflate=0.018)
    diamond_plate("Cape center gold", (back_pt[0], back_pt[1], back_pt[2] + 0.01), 0.18, 0.24, 0.014, gold)
    ice_gem("Cape center gem", (back_pt[0], back_pt[1], back_pt[2] + 0.02), 0.038, tall=1.15, outward=-0.012)
    for tag, u, tilt in (("L", 0.32, 0.55), ("R", 0.68, -0.55)):
        pt = cape_point(u, 0.10, inflate=0.018)
        cube(f"Chevron {tag} A", (pt[0], pt[1], pt[2] + 0.01), (0.014, 0.012, 0.12), gold,
             bevel=0.003, sub=1, rot=(0.2, tilt, 0))
        cube(f"Chevron {tag} B", (pt[0] + (0.04 if tag == "L" else -0.04), pt[1], pt[2] + 0.01),
             (0.014, 0.012, 0.12), gold, bevel=0.003, sub=1, rot=(0.2, -tilt, 0))
    for tag, u in (("L", 0.10), ("R", 0.90)):
        pt = cape_point(u, 0.16, inflate=0.018)
        diamond_plate(f"Cape side motif {tag}", (pt[0], pt[1], pt[2]), 0.055, 0.10, 0.012, gold,
                      rot=(0.25, 0.5 if tag == "L" else -0.5, 0.9 if tag == "L" else -0.9))

    # --- Staff ---------------------------------------------------------------
    staff = bpy.data.objects.new("Staff", None)
    link(staff, root)
    staff.empty_display_type = "PLAIN_AXES"
    sx, sy = -0.46, -0.02
    cylinder("Staff shaft", (sx, sy, 0.95), 0.016, 1.58, wood, parent=staff, verts=20, bevel=0.003, sub=1)
    for z in (1.60, 1.28, 0.38):
        torus(f"Staff band {z}", (sx, sy, z), 0.02, 0.006, gold, parent=staff)
    cube("Staff socket", (sx, sy, 1.72), (0.05, 0.05, 0.07), gold, parent=staff, bevel=0.008, sub=1)
    octahedron("Staff crystal top", (sx, sy, 1.92), 0.042, 0.042, 0.17, crystal, staff, 1)
    octahedron("Staff crystal bottom", (sx, sy, 0.12), 0.028, 0.028, 0.10, crystal, staff, 1)
    cube("Staff ferrule", (sx, sy, 0.24), (0.036, 0.036, 0.045), gold, parent=staff, bevel=0.006, sub=1)
    for i in range(4):
        angle = i * math.pi / 2 + math.pi / 4
        loc = (sx + math.cos(angle) * 0.028, sy + math.sin(angle) * 0.028, 1.82)
        cone(f"Staff fin {i}", loc, 0.022, 0.16, gold, staff, radius2=0.001,
             rot=(0.85, 0, angle + math.pi / 2), verts=5)

    # --- Studio --------------------------------------------------------------
    world = scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (*srgb(0.62, 0.64, 0.66), 1)
    background.inputs["Strength"].default_value = 1.0
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.display_settings.display_device = "sRGB"

    bpy.ops.mesh.primitive_plane_add(size=24, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Shadow catcher"
    link(ground, None, extras)
    ground_mat = mat("Studio floor", srgb(0.62, 0.64, 0.66), roughness=1.0, spec=0.05)
    ground.data.materials.append(ground_mat)
    ground.is_shadow_catcher = True

    def light(name, location, energy, size, color, target=(0, 0, 1.05)):
        bpy.ops.object.light_add(type="AREA", location=location)
        obj = bpy.context.object
        obj.name = name
        obj.data.energy = energy
        obj.data.color = color
        obj.data.shape = "DISK"
        obj.data.size = size
        direction = Vector(target) - Vector(location)
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        link(obj, None, extras)
        return obj

    light("Key", (-1.8, -2.6, 3.2), 650, 2.6, (1.0, 0.97, 0.93))
    light("Fill", (2.2, -1.5, 1.7), 220, 3.2, (0.78, 0.86, 1.0))
    light("Rim", (0.4, 2.4, 2.4), 300, 2.0, (0.72, 0.88, 1.0))
    light("Hair", (-0.1, -0.3, 3.4), 140, 1.2, (1.0, 0.96, 0.9), (0, 0, 1.7))

    def camera(name, location, target, ortho_scale):
        bpy.ops.object.camera_add(location=location)
        obj = bpy.context.object
        obj.name = name
        direction = Vector(target) - Vector(location)
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        obj.data.type = "ORTHO"
        obj.data.ortho_scale = ortho_scale
        obj.data.clip_start = 0.05
        obj.data.clip_end = 40
        link(obj, None, extras)
        return obj

    cam_front = camera("Cam front", (0.0, -4.4, 0.94), (0.0, 0, 0.94), 2.12)
    cam_left = camera("Cam left", (4.4, 0.0, 0.94), (0, 0, 0.94), 2.12)
    cam_back = camera("Cam back", (0.0, 4.4, 0.94), (0, 0, 0.94), 2.12)
    cam_top = camera("Cam top", (0.0, -0.08, 4.5), (0.0, 0.02, 1.0), 1.45)
    ground.hide_render = True
    cam_beauty = camera("Cam beauty", (2.0, -3.6, 1.35), (0.0, 0, 0.92), 2.0)
    cam_beauty.data.type = "PERSP"
    cam_beauty.data.lens = 85

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 48
    if hasattr(scene.eevee, "use_shadows"):
        scene.eevee.use_shadows = True

    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.use_file_extension = True

    blend_path = ART / "protagonist.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    def render_still(cam, path, res):
        scene.camera = cam
        scene.render.resolution_x, scene.render.resolution_y = res
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        if not path.is_file():
            raise RuntimeError(f"Render missing: {path}")

    def set_staff_visible(visible):
        def walk(obj):
            obj.hide_render = not visible
            for child in obj.children:
                walk(child)
        walk(staff)

    set_staff_visible(True)
    render_still(cam_front, OUTPUT / "protagonist_front.png", (720, 1080))
    set_staff_visible(False)
    render_still(cam_left, OUTPUT / "protagonist_left.png", (720, 1080))
    set_staff_visible(True)
    render_still(cam_back, OUTPUT / "protagonist_back.png", (720, 1080))
    render_still(cam_top, OUTPUT / "protagonist_top.png", (720, 720))
    render_still(cam_beauty, OUTPUT / "protagonist_beauty.png", (1080, 1350))

    glb_path = OUTPUT / "protagonist.glb"
    bpy.ops.object.select_all(action="DESELECT")
    for obj in col.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
        export_extras=False,
    )

    stitch_turnaround()
    provenance = {
        "source": "Original procedural Blender character assembly",
        "script": "tools/build_protagonist.py",
        "blend": "art/protagonist.blend",
        "reference_images": ["art/references/protagonist_concept.png"],
        "reference_use": "Silhouette, costume blocking, gem layout and gold trim; no pixels copied",
        "external_assets": [],
        "imagegen": False,
        "units": "metres",
        "runtime_use": "Presentation character mesh and turnaround renders",
        "visual_review": "pending",
        "outputs": {
            "glb": "client/assets/characters/protagonist.glb",
            "turnaround": "client/assets/characters/protagonist_turnaround.png",
            "beauty": "client/assets/characters/protagonist_beauty.png",
            "views": [
                "client/assets/characters/protagonist_front.png",
                "client/assets/characters/protagonist_left.png",
                "client/assets/characters/protagonist_back.png",
                "client/assets/characters/protagonist_top.png",
            ],
        },
        "object_count": len(col.objects),
    }
    (OUTPUT / "protagonist.provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))


def stitch_turnaround():
    from PIL import Image, ImageDraw, ImageFont

    def crop_content(image, pad=16):
        bg = image.getpixel((2, 2))
        pixels = image.load()
        width, height = image.size
        min_x, min_y, max_x, max_y = width, height, 0, 0
        for y in range(0, height, 2):
            for x in range(0, width, 2):
                pixel = pixels[x, y]
                if any(abs(pixel[i] - bg[i]) > 14 for i in range(3)):
                    min_x, min_y = min(min_x, x), min(min_y, y)
                    max_x, max_y = max(max_x, x), max(max_y, y)
        if max_x <= min_x:
            return image
        min_x = max(0, min_x - pad)
        min_y = max(0, min_y - pad)
        max_x = min(width, max_x + pad)
        max_y = min(height, max_y + pad)
        return image.crop((min_x, min_y, max_x, max_y))

    front = Image.open(OUTPUT / "protagonist_front.png").convert("RGB")
    left = Image.open(OUTPUT / "protagonist_left.png").convert("RGB")
    back = Image.open(OUTPUT / "protagonist_back.png").convert("RGB")
    top = crop_content(Image.open(OUTPUT / "protagonist_top.png").convert("RGB"))
    canvas = Image.new("RGB", (1920, 1080), (158, 163, 168))
    front_r = front.resize((430, 860), Image.Resampling.LANCZOS)
    left_r = left.resize((430, 860), Image.Resampling.LANCZOS)
    back_r = back.resize((430, 860), Image.Resampling.LANCZOS)
    top_r = top.resize((420, int(420 * top.size[1] / top.size[0])), Image.Resampling.LANCZOS)
    y = 70
    canvas.paste(front_r, (70, y))
    canvas.paste(left_r, (520, y))
    canvas.paste(back_r, (970, y))
    canvas.paste(top_r, (1440, 280))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    gray = (90, 94, 98)
    for text, x in (("FRONT", 285), ("LEFT SIDE", 735), ("BACK", 1185), ("TOP", 1645)):
        draw.text((x, 980), text, fill=gray, font=font, anchor="mm")
    canvas.save(OUTPUT / "protagonist_turnaround.png")


if __name__ == "__main__":
    if "--stitch-only" in sys.argv:
        stitch_turnaround()
    else:
        try:
            main()
        except Exception:
            import traceback
            traceback.print_exc()
            raise SystemExit(1)
