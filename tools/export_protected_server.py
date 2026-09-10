"""Publish and obfuscate project-owned server assemblies in an isolated folder."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from release_protection import PRIVATE, ROOT, sha256


SERVER = ROOT / "server"
ASSEMBLIES = ["FantasyCard.Contracts", "FantasyCard.Domain", "FantasyCard.Server"]
SUITES = ["FantasyCard.Domain.Tests", "FantasyCard.Server.Tests"]
TOOL_VERSION = "2.2.50"


def configuration(input_dir, output_dir, log_path, test_dirs=()):
    root = ET.parse(SERVER / "protection/obfuscar.xml").getroot()
    paths = {"InPath": str(input_dir), "OutPath": str(output_dir), "LogFile": str(log_path)}
    for variable in root.findall("Var"):
        if variable.get("name") in paths:
            variable.set("value", paths[variable.get("name")])
    for search in root.findall("AssemblySearchPath"):
        root.remove(search)
    runtimes = subprocess.check_output(["dotnet", "--list-runtimes"], text=True)
    for framework in ("Microsoft.NETCore.App", "Microsoft.AspNetCore.App"):
        matches = re.findall(re.escape(framework) + r" (10\.\d+\.\d+) \[([^\]]+)\]", runtimes)
        if not matches:
            raise ValueError("Required .NET 10 runtime is not installed: " + framework)
        version, parent = max(matches, key=lambda item: tuple(map(int, item[0].split("."))))
        ET.SubElement(root, "AssemblySearchPath", path=str(Path(parent) / version))
    for test_dir in test_dirs:
        ET.SubElement(root, "AssemblySearchPath", path=str(test_dir))
        suite = test_dir.parent.name
        module = ET.SubElement(root, "Module", file=str(test_dir / (suite + ".dll")))
        # Preserve test definitions, but let Obfuscar repair their internal-type references.
        ET.SubElement(module, "SkipType", name="*", skipMethods="true", skipFields="true",
                      skipProperties="true", skipEvents="true", skipStringHiding="true")
    return ET.ElementTree(root)


def export_server():
    tool = PRIVATE / "dotnet-tools/obfuscar.console.exe"
    if not tool.is_file():
        subprocess.run(["dotnet", "tool", "install", "Obfuscar.GlobalTool", "--version", TOOL_VERSION,
                        "--tool-path", str(tool.parent)], cwd=SERVER, check=True)
    version = subprocess.check_output([str(tool), "--version"], text=True)
    if TOOL_VERSION not in version:
        raise ValueError("Unexpected Obfuscar version; install " + TOOL_VERSION + " in the private tool directory.")
    # Unique staging prevents failed/repeated exports from reusing old binaries.
    import tempfile
    working = Path(tempfile.mkdtemp(prefix="server-", dir=PRIVATE))
    publish = working / "publish"
    protected = working / "obfuscated"
    test_build = SERVER / "artifacts/release-protection" / working.name
    subprocess.run(["dotnet", "build", "FantasyCard.Server.slnx", "-c", "Release",
                    "--artifacts-path", str(test_build)], cwd=SERVER, check=True)
    test_dirs = [test_build / "bin" / suite / "release" for suite in SUITES]
    subprocess.run(["dotnet", "publish", "src/FantasyCard.Server/FantasyCard.Server.csproj",
                    "-c", "Release", "--artifacts-path", str(PRIVATE / "server-build"),
                    "-p:DebugType=None", "-p:DebugSymbols=false", "-p:UseAppHost=false",
                    "-o", str(publish)], cwd=SERVER, check=True)
    config = working / "obfuscar.xml"
    configuration(publish, protected, working / "mapping.xml", test_dirs).write(config, encoding="utf-8", xml_declaration=True)
    subprocess.run([str(tool), str(config)], cwd=SERVER, check=True)
    packages = {}
    for assembly in ASSEMBLIES:
        name = assembly + ".dll"
        source, result = publish / name, protected / name
        if not result.is_file() or sha256(source) == sha256(result):
            raise ValueError("Obfuscation did not change " + name)
        packages[name] = {"original_sha256": sha256(source), "protected_sha256": sha256(result)}
        shutil.copy2(result, source)
    for test_dir in test_dirs:
        suite = test_dir.parent.name
        shutil.copy2(protected / (suite + ".dll"), test_dir / (suite + ".dll"))
        for assembly in ASSEMBLIES:
            name = assembly + ".dll"
            if (test_dir / name).is_file():
                shutil.copy2(publish / name, test_dir / name)
    for item in publish.rglob("*"):
        if item.is_file() and (item.suffix.lower() in {".cs", ".pdb", ".key", ".dpapi", ".xml"}
                               or item.name == "appsettings.Development.json"):
            item.unlink()
    destination = ROOT / "builds/server-protected" / working.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(publish, destination)
    report = {"exported": True, "tested": False, "obfuscator": "Obfuscar " + TOOL_VERSION,
              "output": str(destination), "assemblies": packages, "private_mapping": str(working / "mapping.xml"),
              "private_report": str(working / "report.json"),
              "test_assemblies": [str(test_dir / (test_dir.parent.name + ".dll")) for test_dir in test_dirs],
              "protection": ["private implementation renaming", "string hiding", "no PDB or source files"],
              "preserved": ["public API", "JSON properties", "enum fields", "constructor names"],
              "limitation": "Managed IL remains decompilable; this is obfuscation, not full assembly encryption."}
    (working / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (destination / "CANDIDATE-NOT-YET-VALIDATED.txt").write_text(
        "Run tools/validate_protected_server.py with this package's private report before deployment.\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        PRIVATE.mkdir(parents=True, exist_ok=True)
        export_server()
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"exported": False, "error": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
