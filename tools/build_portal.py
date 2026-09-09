"""Original stylized rigid environment, executed only in Blender's bpy interpreter."""
from pathlib import Path
import math
import json


def main():
    import bpy
    from mathutils import Vector

    root = Path(__file__).resolve().parents[1]
    output = root / "client/assets"
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    def material(name, color, emission=0):
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*color, 1)
        shader.inputs["Roughness"].default_value = 0.8
        if emission:
            shader.inputs["Emission Color"].default_value = (*color, 1)
            shader.inputs["Emission Strength"].default_value = emission
        return mat

    stone = material("Moss stone", (0.19, 0.32, 0.33))
    edge = material("Cut sandstone", (0.42, 0.51, 0.46))
    gold = material("Old brass", (0.63, 0.41, 0.15))
    glow = material("Portal jade", (0.05, 0.65, 0.53), 2)
    ground = material("Ground", (0.09, 0.17, 0.18))

    def cube(name, location, scale, mat, bevel=0.08):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(mat)
        if bevel:
            modifier = obj.modifiers.new("Soft chipped edges", "BEVEL")
            modifier.width = bevel
            modifier.segments = 2
            obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        return obj

    cube("Ground", (0, 0, -0.25), (40, 35, 0.5), ground)
    cube("Lower plinth", (2, 0, 0.15), (7, 4, 0.3), stone)
    cube("Upper plinth", (2, 0, 0.48), (6.2, 3.4, 0.36), edge)
    for side in (-1, 1):
        for step in range(4):
            cube(f"Pillar {side} {step}", (2 + side * 2.35, 0, 1.02 + step * 0.84), (0.96, 1.1, 0.77), stone)
        cube(f"Capital {side}", (2 + side * 2.35, 0, 4.08), (1.15, 1.3, 0.28), gold)
    for index in range(9):
        angle = math.pi * index / 8
        obj = cube(f"Arch stone {index}", (2 + 2.35 * math.cos(angle), 0, 3.65 + 2.1 * math.sin(angle)), (0.78, 1.16, 0.68), edge)
        obj.rotation_euler.y = -angle
    for index in range(18):
        angle = math.tau * index / 18
        obj = cube(f"Jade rune {index}", (2 + 1.73 * math.cos(angle), -0.08, 3.02 + 2.0 * math.sin(angle)), (0.13, 0.16, 0.31), glow, 0.025)
        obj.rotation_euler.y = angle
    for x, y, size in [(-4, 1, 0.8), (6, 3, 0.65), (-5, -3, 0.45), (7, -2, 0.9), (-1, 4, 0.55)]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=size, location=(x, y, size * 0.5))
        bpy.context.object.scale = (1.4, 1, 0.8)
        bpy.context.object.data.materials.append(stone)
    for side in (-1, 1):
        cube(f"Lantern base {side}", (2 + side * 3.3, -1.7, 0.3), (0.7, 0.7, 0.6), stone)
        cube(f"Lantern cap {side}", (2 + side * 3.3, -1.7, 0.7), (0.5, 0.5, 0.25), gold)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.3, location=(2 + side * 3.3, -1.7, 1.05))
        bpy.context.object.scale.z = 1.8
        bpy.context.object.data.materials.append(glow)

    bpy.ops.object.camera_add(location=(12, -19, 11))
    camera = bpy.context.object
    direction = Vector((0, 0, 2.3)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 17
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.world.color = (0.18, 0.23, 0.25)
    for position, energy, color, size in [((1, -6, 10), 1900, (1, 0.86, 0.62), 8), ((5, 3, 7), 1300, (0.2, 0.85, 0.72), 6)]:
        bpy.ops.object.light_add(type="AREA", location=position)
        light = bpy.context.object
        light.data.energy = energy
        light.data.color = color
        light.data.shape = "DISK"
        light.data.size = size
        light.rotation_euler = (Vector((2, 0, 2)) - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output / "portal.png")
    (root / "art").mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(root / "art/portal.blend"))
    bpy.ops.export_scene.gltf(filepath=str(output / "portal.glb"), export_format="GLB", export_cameras=False, export_lights=False)
    bpy.ops.render.render(write_still=True)
    assert (output / "portal.png").is_file()
    (output / "portal.provenance.json").write_text(json.dumps({"source": "Original procedural Blender assembly", "script": "tools/build_portal.py", "units": "metres", "runtime_use": "rendered environment backdrop", "external_assets": [], "imagegen": False, "visual_review": "pending"}, indent=2))


if __name__ == "__main__":
    main()
