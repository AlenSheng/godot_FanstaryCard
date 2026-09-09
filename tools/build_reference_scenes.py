"""Rebuild clean reference-inspired backgrounds inside Blender's bpy interpreter.

Run Blender --background --factory-startup --python this_file.py.
Set FANTASYCARD_SCENE_SCALE=50 for preview renders; the default is 1920 x 1080.
"""

from pathlib import Path
import json
import math
import os
import random
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "client/assets/scenes"


def validate_layout():
    sys.path.insert(0, str(ROOT / "GameFactory-3A"))
    from operators.gen_3d_scene.funcs import terrain_code_edit as te

    checks = {}
    for name in ("dungeon_battle", "camp_hall"):
        props = te.place("rear-columns", "box", [(-10, 7), (-6, 9), (6, 9), (10, 7)],
                         size=(1.6, 8, 1.6), group="masonry")
        props += te.place("side-braziers", "cylinder", [(-7, 4), (7, 4)],
                          size=(0.9, 2.0, 0.9))
        greybox = te.Scene(name, terrain=te.flat(60), props=props)
        problems = te.check_scene(greybox)
        if problems:
            raise RuntimeError("Scene layout rejected: " + "; ".join(problems))
        checks[name] = {"layout_issues": problems, "ground_metres": 60,
                        "clear_character_staging_metres": [-6, 6, -3, 3]}
    return checks


def main():
    import bpy
    from mathutils import Vector

    layout_checks = validate_layout()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "art").mkdir(exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    rng = random.Random(5809)

    def material(name, color, emission=0, metallic=0, stone=False):
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        shader = nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*color, 1)
        shader.inputs["Roughness"].default_value = .82 if stone else .55
        shader.inputs["Metallic"].default_value = metallic
        if emission:
            shader.inputs["Emission Color"].default_value = (*color, 1)
            shader.inputs["Emission Strength"].default_value = emission
        if stone:
            coords = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 6
            noise.inputs["Detail"].default_value = 4
            noise.inputs["Roughness"].default_value = .75
            mat.node_tree.links.new(coords.outputs["Object"], noise.inputs["Vector"])
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = .15
            ramp.color_ramp.elements[0].color = (*[v * .45 for v in color], 1)
            ramp.color_ramp.elements[1].position = .85
            ramp.color_ramp.elements[1].color = (*[min(1, v * 1.28) for v in color], 1)
            mat.node_tree.links.new(noise.outputs["Fac"], ramp.inputs[0])
            mat.node_tree.links.new(ramp.outputs[0], shader.inputs["Base Color"])
            bump = nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = .35
            bump.inputs["Distance"].default_value = .13
            mat.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
            mat.node_tree.links.new(bump.outputs[0], shader.inputs["Normal"])
        return mat

    stones = [material("Weathered slate %02d" % i,
                       (.15 + i * .008, .205 + i * .009, .205 + i * .009), stone=True)
              for i in range(8)]
    pale = material("Chipped limestone edges", (.30, .34, .31), stone=True)
    dark = material("Deep stone cracks", (.025, .045, .05), stone=True)
    brass = material("Oxidised warm bronze", (.25, .155, .06), metallic=.72)
    iron = material("Black forged iron", (.045, .065, .07), metallic=.7)
    wood = material("Dark oak", (.105, .06, .032), stone=True)
    blue = material("Cyan crystal light", (.01, .54, .8), emission=5)
    flame = material("Amber fire core", (1, .21, .018), emission=7)

    def finish(obj, name, mat, bevel=0):
        obj.name = name
        obj.data.materials.append(mat)
        if bevel:
            mod = obj.modifiers.new("Worn edges", "BEVEL")
            mod.width = bevel
            mod.segments = 2
            obj.modifiers.new("Stone face normals", "WEIGHTED_NORMAL")
        return obj

    def cube(name, pos, size, mat=None, bevel=.055):
        bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
        obj = bpy.context.object
        obj.scale = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return finish(obj, name, mat or rng.choice(stones), bevel)

    def cylinder(name, pos, radius, depth, mat, vertices=16):
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                          depth=depth, location=pos)
        return finish(bpy.context.object, name, mat, .035)

    def curve(name, points, radius, mat, cyclic=False):
        data = bpy.data.curves.new(name, "CURVE")
        data.dimensions = "3D"
        data.bevel_depth = radius
        data.bevel_resolution = 1
        spline = data.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for p, value in zip(spline.points, points):
            p.co = (*value, 1)
        spline.use_cyclic_u = cyclic
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        data.materials.append(mat)
        return obj

    def wedge(name, inner, outer, a, b, z, height, centre=(0, 1)):
        verts = [(centre[0] + r * math.cos(t), centre[1] + r * math.sin(t), level)
                 for level in (z - height, z)
                 for r, t in ((inner, a), (outer, a), (outer, b), (inner, b))]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                 (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        return finish(obj, name, rng.choice(stones), .04)

    def floor():
        cube("Continuous dark foundation", (0, 4, -.38), (60, 60, .5), dark)
        # Radial paving is shallow, so the centre remains usable for character sprites.
        for ring in range(16):
            inner = .1 + ring * .83
            outer = inner + .795
            segments = max(9, int(math.tau * outer / 1.1))
            offset = .11 * (ring % 2)
            for segment in range(segments):
                a = offset + math.tau * segment / segments + .006
                b = offset + math.tau * (segment + 1) / segments - .006
                wedge("Ring %02d stone %02d" % (ring, segment), inner, outer,
                      a, b, rng.uniform(-.035, .018), .23)
        for row in range(11):
            for col in range(24):
                x, y = -18 + col * 1.55 + (row % 2) * .775, 8.5 + row * 1.25
                if math.hypot(x, y - 1) < 13.8:
                    continue
                cube("Far flagstone", (x, y, -.08), (1.50, 1.19, .22), bevel=.045)

    def pillar(x, y, height=8, ruined=False):
        cube("Column foundation", (x, y, .21), (2.0, 2.0, .42), pale)
        cube("Column lower bevel", (x, y, .60), (1.65, 1.65, .36))
        layers = int((height - .8) / .78)
        for index in range(layers):
            pos = (x + rng.uniform(-.035, .035), y, 1 + index * .78)
            cube("Column stacked block", pos, (1.34, 1.34, .75))
            if index % 3 == 2:
                cube("Column horizontal collar", (x, y, pos[2] + .36),
                     (1.50, 1.50, .16), pale)
        top = .70 + layers * .78
        if not ruined:
            cube("Column capital", (x, y, top), (1.85, 1.85, .40), pale)
        for edge in (-1, 1):
            cube("Fluted pilaster edge", (x + edge * .45, y - .715, top * .51),
                 (.14, .12, top * .78), dark, .015)

    def arch(x, y, radius=3.0, spring=3.5, thickness=.68, broken=False):
        for side in (-1, 1):
            for i in range(int(spring / .62)):
                cube("Arch upright stone", (x + side * (radius + thickness * .5), y,
                     .31 + i * .62), (thickness, 1.6, .59))
        count = 17
        for i in range(count):
            if broken and i in (6, 7, 8, 9):
                continue
            a = math.pi * i / count + .012
            b = math.pi * (i + 1) / count - .012
            coords = [(x + r * math.cos(t), yy, spring + r * math.sin(t))
                      for yy in (y - .81, y + .81)
                      for r, t in ((radius, a), (radius + thickness, a),
                                   (radius + thickness, b), (radius, b))]
            mesh = bpy.data.meshes.new("Arch voussoir")
            mesh.from_pydata(coords, [], [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
                                         (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)])
            obj = bpy.data.objects.new("Arch voussoir", mesh)
            bpy.context.collection.objects.link(obj)
            finish(obj, "Arch voussoir", pale if i == 8 else rng.choice(stones), .055)

    def rock(pos, size, spire=False):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1, location=pos)
        obj = bpy.context.object
        obj.scale = size
        obj.rotation_euler = (rng.uniform(-.3, .3), rng.uniform(-.25, .25), rng.random() * math.tau)
        return finish(obj, "Cavern spire" if spire else "Fallen masonry", rng.choice(stones))

    def light(name, pos, color, energy, size=1, target=None):
        bpy.ops.object.light_add(type="AREA" if target else "POINT", location=pos)
        obj = bpy.context.object
        obj.name = name
        obj.data.energy = energy
        obj.data.color = color
        if target:
            obj.data.shape = "DISK"
            obj.data.size = size
            obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
        else:
            obj.data.shadow_soft_size = size
        return obj

    def brazier(x, y, cyan=False):
        cylinder("Brazier stone foot", (x, y, .18), .48, .36, pale)
        cylinder("Brazier stem", (x, y, .82), .11, 1.14, iron)
        cylinder("Brazier bowl rim", (x, y, 1.46), .40, .14, brass)
        for i in range(7):
            angle = i * math.tau / 7
            curve("Brazier ribs", [(x + math.cos(angle) * r, y + math.sin(angle) * r, z)
                  for r, z in ((.13, 1.08), (.35, 1.40), (.39, 1.60))], .033, iron)
        for i in range(4):
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=.22,
                location=(x + rng.uniform(-.14, .14), y + rng.uniform(-.14, .14), 1.72 + i * .12))
            bpy.context.object.scale = (.75, .75, 2.0 + i * .35)
            finish(bpy.context.object, "Arcane crystal" if cyan else "Faceted flame", blue if cyan else flame)
        light("Cyan brazier" if cyan else "Warm brazier", (x, y, 2.0),
              (.025, .58, 1) if cyan else (1, .31, .07), 150 if cyan else 220, .65)

    def debris():
        for side in (-1, 1):
            for i in range(30):
                x, y = side * rng.uniform(8.5, 14), rng.uniform(1.5, 16)
                scale = rng.uniform(.25, .8)
                rock((x, y, scale * .43), (scale * 1.25, scale, scale * .85))

    def configure(scene, camera_position, camera_target):
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 24
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 5
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = int(os.environ.get("FANTASYCARD_SCENE_SCALE", "100"))
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.film_transparent = False
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
        scene.view_settings.exposure = -.35
        world = bpy.data.worlds.new(scene.name + " atmosphere")
        scene.world = world
        world.use_nodes = True
        world.node_tree.nodes.get("Background").inputs[0].default_value = (.035, .07, .09, 1)
        world.node_tree.nodes.get("Background").inputs[1].default_value = .24
        bpy.ops.object.camera_add(location=camera_position)
        camera = bpy.context.object
        camera.name = "UI composition camera"
        camera.rotation_euler = (Vector(camera_target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = 36
        scene.camera = camera
        light("Broad cool cavern bounce", (0, 2, 10), (.20, .43, .51), 1500, 12, (0, 3, 0))
        light("Soft foreground fill", (0, -8, 6), (.43, .56, .59), 1100, 14, (0, 4, 1))
        light("Warm staging light", (-1, 1, 7), (1, .59, .26), 1100, 7, (0, 1, 0))

    def build(name):
        scene = bpy.data.scenes.new(name)
        bpy.context.window.scene = scene
        floor()
        if name == "dungeon_battle":
            configure(scene, (0, -19, 8.5), (0, 4.3, 2.3))
            for x, y, height in [(-10, 5, 8), (10, 5, 8), (-6.7, 11, 9), (6.7, 11, 9)]:
                pillar(x, y, height, ruined=True)
            arch(0, 14, 4.5, 3.5, .92, broken=True)
            arch(-12, 10, 3, 3, .7, broken=True)
            arch(12, 10, 3, 3, .7, broken=True)
            for i in range(24):
                x = rng.uniform(-22, 22)
                y = rng.uniform(18, 29)
                height = rng.uniform(5, 13)
                rock((x, y, height * .42), (rng.uniform(1.2, 2.4), 2, height * .65), True)
            for x in (-11, 11):
                for y in (9, 17):
                    light("Cavern blue depth", (x, y, 5), (.02, .50, .65), 750, 4)
            brazier(-8, 6)
            brazier(8, 6, True)
        else:
            configure(scene, (0, -20, 9), (0, 5.0, 2.7))
            # A right-offset gate leaves the left half available for a hero portrait.
            gate_x, gate_y = 5.0, 11.0
            for row in range(12):
                for col in range(23):
                    x = -18 + col * 1.60 + (row % 2) * .8
                    z = .38 + row * .76
                    if abs(x - gate_x) < 3.0 and z < 4.0 + math.sqrt(max(0, 3.0**2 - (x - gate_x)**2)):
                        continue
                    cube("Hall ashlar block", (x, gate_y + .70, z), (1.55, 1.15, .70))
            arch(gate_x, gate_y, 2.65, 3.7, .70)
            for x in (-11, -5, 10.3):
                pillar(x, 9.2, 9)
            for step in range(4):
                cube("Gate stair", (gate_x, 8.9 + step * .60, .09 + step * .18),
                     (5.65, 2.8 - step * .50, .18 + step * .18), pale)
            for distance in (15, 20, 25):
                arch(gate_x, distance, 2.7, 3.7, .58)
            cube("Distant gate shade", (gate_x, 29, 4.4), (6, 1, 9), dark)
            light("Gate blue mist", (gate_x, 17, 4), (.02, .55, 1), 1600, 3)
            light("Gate threshold spill", (gate_x, 9, 3), (.02, .45, .72), 420, 2)
            brazier(-8, 7)
            brazier(9, 7)
            brazier(-2.3, 9, True)
            for x, y in ((-11.8, 6.5), (-12, 8.1), (-9.7, 8.9)):
                cube("Supply chest", (x, y, .65), (1.4, 1.2, 1.3), wood)
                for side in (-1, 1):
                    cube("Chest iron band", (x + side * .49, y - .62, .66), (.10, .04, 1.29), iron, .01)
            for x in (-13, 12):
                light("Side wall blue bounce", (x, 5, 5), (.12, .37, .43), 500, 4)
        debris()
        scene.render.filepath = str((OUTPUT / (name + ".png")).resolve())
        return scene

    scenes = [build("dungeon_battle"), build("camp_hall")]
    bpy.context.window.scene = scenes[0]
    bpy.ops.wm.save_as_mainfile(filepath=str((ROOT / "art/reference_scenes.blend").resolve()))
    manifests = {}
    for scene in scenes:
        bpy.context.window.scene = scene
        bpy.ops.render.render(write_still=True)
        output = OUTPUT / (scene.name + ".png")
        if not output.is_file():
            raise RuntimeError("Render missing: " + str(output))
        bpy.ops.export_scene.gltf(filepath=str((OUTPUT / (scene.name + ".glb")).resolve()),
            export_format="GLB", use_active_scene=True, export_cameras=True, export_lights=True)
        manifests[scene.name] = {
            "image": str(output.relative_to(ROOT)).replace("\\", "/"),
            "objects": len(scene.objects),
            "resolution": [scene.render.resolution_x * scene.render.resolution_percentage // 100,
                           scene.render.resolution_y * scene.render.resolution_percentage // 100],
            **layout_checks[scene.name],
        }
    provenance = {
        "source": "Original procedural Blender geometry and materials",
        "script": "tools/build_reference_scenes.py",
        "blend": "art/reference_scenes.blend",
        "reference_images": ["ui_mockups_v058/ui_hall_1920x1080.png", "ui_mockups_v058/ui_pve_1920x1080.png",
                             "ui_mockups_v058/ui_action_1920x1080.png", "ui_mockups_v058/ui_gear_1920x1080.png"],
        "reference_use": "Palette, stone architecture and free foreground composition; no pixels copied",
        "external_assets": [], "imagegen": False, "contains_text_or_characters": False,
        "units": "metres", "runtime_use": "Opaque UI background render; original 3D remains editable",
        "materials_in_glb": "Base colors and geometry export; procedural noise is visible in PNG and blend only",
        "visual_review": "pending", "scenes": manifests,
    }
    (OUTPUT / "reference_scenes.provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
