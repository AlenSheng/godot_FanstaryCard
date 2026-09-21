"""Build the Relicbound dungeon-castle lobby in Blender.

Run with Blender's embedded Python.  The resulting .blend remains the editable
source; the two PNG renders are composed for the existing 1920x1080 Godot UI.
"""
from pathlib import Path
import json
import math
import os
import random


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "client" / "assets" / "scenes"


def main():
    import bpy
    from mathutils import Vector

    rng = random.Random(91724)
    ASSETS.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    def mat(name, color, metallic=0.0, roughness=.7, emission=None):
        value = bpy.data.materials.new(name)
        value.use_nodes = True
        bsdf = value.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*color, 1)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if emission:
            bsdf.inputs["Emission Color"].default_value = (*emission[0], 1)
            bsdf.inputs["Emission Strength"].default_value = emission[1]
        return value

    slate = mat("Cold weathered slate", (.16, .23, .27), .0, .9)
    slate_light = mat("Cut slate edges", (.34, .43, .46), .0, .78)
    mortar = mat("Deep mortar", (.025, .042, .058), .0, 1.0)
    iron = mat("Forged black iron", (.025, .035, .04), .83, .32)
    brass = mat("Age-worn brass", (.32, .16, .035), .73, .34)
    ember = mat("Living ember", (1.0, .09, .006), .0, .32, ((1.0, .055, .003), 14))
    flame = mat("Golden torch flame", (1.0, .32, .015), .0, .25, ((1.0, .13, .004), 22))
    cyan = mat("Gate runes", (.005, .37, .55), .12, .26, ((.0, .48, .92), 8))
    wood = mat("Charred oak", (.06, .027, .012), .0, .86)

    def finish(obj, name, material, bevel=.04):
        obj.name = name
        obj.data.materials.append(material)
        # Hundreds of independent masonry pieces are deliberately kept as simple
        # meshes: a bevel modifier on each one makes iterative Blender previews
        # needlessly slow, while the lighting and slate variation sell the edges.
        return obj

    def cube(name, location, scale, material=slate, bevel=.04):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return finish(obj, name, material, bevel)

    def cylinder(name, location, radius, depth, material, vertices=16):
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
        return finish(bpy.context.object, name, material, .025)

    def point_light(name, location, color, power, radius):
        bpy.ops.object.light_add(type="POINT", location=location)
        lamp = bpy.context.object
        lamp.name = name
        lamp.data.color = color
        lamp.data.energy = power
        lamp.data.shadow_soft_size = radius
        return lamp

    def area_light(name, location, target, color, power, size):
        bpy.ops.object.light_add(type="AREA", location=location)
        lamp = bpy.context.object
        lamp.name = name
        lamp.data.color = color
        lamp.data.energy = power
        lamp.data.shape = "DISK"
        lamp.data.size = size
        lamp.rotation_euler = (Vector(target) - lamp.location).to_track_quat("-Z", "Y").to_euler()
        return lamp

    def arch(name, cx, y, width, rise, base, depth, material=slate_light, pieces=15):
        # Uprights plus individually named voussoirs keep the gate editable.
        for side in (-1, 1):
            for level in range(int(base / .72)):
                cube(f"{name} upright {side} {level}", (cx + side * width, y, .38 + level * .72),
                     (.57, depth, .34), material, .035)
        for i in range(pieces):
            angle = math.pi * i / pieces
            x = cx + width * math.cos(angle)
            z = base + rise * math.sin(angle)
            piece = cube(f"{name} archstone {i}", (x, y, z), (.56, depth, .42), material, .04)
            piece.rotation_euler.y = -angle

    def torch(x, y, z=2.2):
        cylinder("Torch wall bracket", (x, y, z - .72), .12, 1.25, iron)
        cylinder("Torch brazier rim", (x, y, z - .12), .31, .13, brass)
        for i in range(7):
            a = i * math.tau / 7
            cube("Torch iron spoke", (x + math.cos(a) * .22, y + math.sin(a) * .22, z - .02),
                 (.035, .035, .28), iron, .008)
        for i in range(6):
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=.24,
                location=(x + rng.uniform(-.13, .13), y + rng.uniform(-.09, .09), z + .13 + i * .13))
            fire = bpy.context.object
            fire.scale = (.62, .62, 1.15 + i * .09)
            finish(fire, "Torch flame layer", flame if i > 1 else ember, .0)
        point_light("Torch warm pool", (x, y - .15, z + .35), (1.0, .16, .018), 680, 1.55)

    # Floor: long perspective slabs, intentionally clear in the lower half for navigation cards.
    cube("Undercroft foundation", (0, 9, -.55), (35, 38, .5), mortar, 0)
    for row in range(16):
        for col in range(19):
            x = -17.0 + col * 1.88 + (row % 2) * .92
            y = -1.0 + row * 1.7
            if abs(x) > 16.7:
                continue
            cube("Hall floor flagstone", (x, y, -.13), (.9, .81, .11), slate if (row + col) % 3 else slate_light, .025)

    # Back wall, side buttresses and ribs give the entrance the feeling of a whole castle, not a panel.
    for row in range(13):
        for col in range(23):
            x = -17.6 + col * 1.6 + (row % 2) * .8
            z = .25 + row * .72
            if abs(x - 5.2) < 4.7 and z < 5.2:
                continue
            cube("Castle ashlar", (x, 18.5, z), (.76, .58, .33), slate, .025)
    for x in (-14.5, -8.2, 10.7, 15.4):
        cube("Buttress foot", (x, 13.1, .45), (1.25, 1.65, .45), slate_light)
        for level in range(10):
            cube("Buttress block", (x, 14.2, 1.02 + level * .7), (.78, .92, .32), slate)
        cube("Buttress crown", (x, 14.1, 8.0), (1.08, 1.12, .30), slate_light)
    for index, y in enumerate((8.2, 12.4, 16.4)):
        arch("Vault rib %s" % index, 0.0, y, 9.8, 4.1, 4.0, .20, slate, 19)

    # The sealed dungeon gate sits right-of-centre, matching the UI's exploration call-to-action.
    gate_x, gate_y = 5.2, 17.5
    arch("Ancient dungeon gate", gate_x, gate_y, 4.15, 4.15, 4.2, .76, slate_light, 19)
    cube("Gate darkness", (gate_x, gate_y + .16, 3.65), (3.94, .19, 3.55), mortar, 0)
    for side in (-1, 1):
        cube("Gate door leaf", (gate_x + side * 1.95, gate_y - .13, 3.35), (1.83, .12, 3.1), wood, .015)
        for z in (1.25, 2.7, 4.15):
            cube("Gate iron brace", (gate_x + side * 1.95, gate_y - .30, z), (1.75, .05, .07), iron, .01)
    for x in (-3.05, -2.25, -1.45, -.65, .65, 1.45, 2.25, 3.05):
        cylinder("Raised portcullis bar", (gate_x + x, gate_y - .52, 5.05), .075, 3.45, iron, 10)
    for z in (3.75, 5.65):
        cube("Portcullis crossbar", (gate_x, gate_y - .52, z), (3.32, .055, .07), iron, .01)
    cylinder("Gate seal", (gate_x, gate_y - .4, 4.25), 1.04, .13, brass, 32)
    # Rotate the seal to face the camera/front.
    bpy.context.object.rotation_euler.x = math.pi / 2
    for i in range(12):
        a = math.tau * i / 12
        cube("Azure seal rune", (gate_x + math.cos(a) * 1.46, gate_y - .47, 4.25 + math.sin(a) * 1.46),
             (.10, .05, .19), cyan, .01)
    point_light("Gate abyss glow", (gate_x, gate_y - .7, 4.1), (.0, .28, .8), 620, 2.8)
    point_light("Gate floor spill", (gate_x, 12.5, .8), (.0, .17, .52), 340, 3.2)

    # Props frame, rather than obscure, the playable composition.
    for x, y, height in ((-13.4, 7.8, 7.4), (-6.9, 10.5, 8.6), (12.4, 10.8, 8.0)):
        cube("Ruined column plinth", (x, y, .26), (1.35, 1.35, .28), slate_light)
        for level in range(int(height / .66)):
            cube("Ruined column shaft", (x, y, .75 + level * .66), (.72, .72, .31), slate)
        cube("Ruined column capital", (x, y, height + .32), (1.02, 1.02, .25), slate_light)
    for x, y in ((-12.5, 5.1), (-3.2, 8.6), (10.4, 7.0), (15.0, 10.6)):
        torch(x, y)
    for x, y, s in ((-16, 1.8, 1.2), (-11.2, 2.6, .75), (14.8, 2.5, .9), (16.5, 6.1, .63)):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1, location=(x, y, s * .35))
        rock = bpy.context.object
        rock.scale = (s, s * .7, s * .55)
        rock.rotation_euler = (rng.random(), rng.random(), rng.random())
        finish(rock, "Fallen castle masonry", slate, .025)

    scene = bpy.context.scene
    # Blender 5.2 exposes the Eevee Next renderer through the stable identifier.
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    # The shipped lobby art is always rendered at its authored 1920x1080 size.
    # Temporarily set FANTASYCARD_SCENE_SCALE only for local preview iterations.
    scene.render.resolution_percentage = int(os.environ.get("FANTASYCARD_SCENE_SCALE", "100"))
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = .65
    world = bpy.data.worlds.new("Moonlit dungeon atmosphere")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (.008, .016, .032, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = .45
    scene.world = world
    area_light("Cold moon shafts", (-3, -3, 13), (0, 10, 1), (0.10, .34, .62), 3600, 10.0)
    area_light("Warm foreground bounce", (-8, -6, 5), (0, 7, 1), (1.0, .23, .035), 2100, 8.0)
    area_light("Gate rim light", (8, 20, 10), (5, 11, 2), (.01, .32, 1.0), 3000, 7.0)
    area_light("Hall ambient wash", (0, 7, 12), (0, 10, 0), (.32, .52, .68), 2800, 15.0)

    def render_camera(name, location, target, output, lens):
        bpy.ops.object.camera_add(location=location)
        camera = bpy.context.object
        camera.name = name
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = lens
        scene.camera = camera
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(camera, do_unlink=True)

    blend_path = ROOT / "art" / "dungeon_castle_hall.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    render_camera("Lobby gameplay camera", (0, -21.5, 8.4), (0.7, 10.0, 2.75), ASSETS / "camp_hall.png", 36)
    scene.render.resolution_x, scene.render.resolution_y = 1500, 990
    render_camera("Dungeon gate panel camera", (5.2, -3.2, 6.0), (5.2, 17.0, 3.75), ASSETS / "dungeon_gate_panel.png", 48)
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    bpy.ops.export_scene.gltf(filepath=str(ASSETS / "dungeon_castle_hall.glb"), export_format="GLB", export_cameras=True, export_lights=True)
    provenance = {
        "source": "Original procedural Blender geometry and materials",
        "script": "tools/build_dungeon_hall.py",
        "blend": "art/dungeon_castle_hall.blend",
        "runtime_use": "Godot lobby background plus dungeon-entry panel",
        "outputs": ["client/assets/scenes/camp_hall.png", "client/assets/scenes/dungeon_gate_panel.png", "client/assets/scenes/dungeon_castle_hall.glb"],
        "external_assets": [], "imagegen": False, "units": "metres"
    }
    (ASSETS / "dungeon_castle_hall.provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
