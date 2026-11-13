"""Single source of truth for every name the upgrade-spring-app skill generates.

Nothing else may invent a name. The rules exist to prevent collisions: skill names must be unique across all skill
artifacts the advisor unpacks into .claude/skills/, and recipe class names must be unique on the OpenRewrite classpath.

  folder        basename of the repository root                         acme-security-starter
  groupId       groupId of the application's own pom.xml                com.acme
  slug          advisor mapping slug of the upgraded project            spring-security
  version       always a SNAPSHOT, installed to the local ~/.m2 only    1.0.0-SNAPSHOT

  recipes artifact   <groupId>:<folder>-<slug>-recipes:<version>
  skills  artifact   <groupId>:<folder>-<slug>-skills:<version>
  skill name         <folder>-<slug>-<problem>        (also the folder name inside the skills zip)
  recipe package     <groupId>.advisor.<folderpkg>.<slugpkg>   (folderpkg/slugpkg = lowercase, [a-z0-9] only)
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "1.0.0-SNAPSHOT"
MIN_JAVA = "17"
POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def repo_root(start: Path | None = None) -> Path:
    """The repository root is the directory that holds pom.xml. Scripts must be run from there."""
    root = (start or Path.cwd()).resolve()
    if not (root / "pom.xml").is_file():
        raise SystemExit(f"error: no pom.xml in {root}. Run this script from the repository root.")
    return root


def _text(node, path):
    found = node.find(path, POM_NS)
    return found.text.strip() if found is not None and found.text else None


def group_id(root: Path) -> str:
    pom = ET.parse(root / "pom.xml").getroot()
    return _text(pom, "m:groupId") or _text(pom, "m:parent/m:groupId") or _fail("cannot read groupId from pom.xml")


def _fail(message: str):
    raise SystemExit(f"error: {message}")


def _pkg(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]", "", value.lower())
    return f"_{cleaned}" if cleaned[:1].isdigit() else cleaned


def names(root: Path, slug: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        _fail(f"slug '{slug}' must be lowercase letters, digits and hyphens")
    folder = root.name
    gid = group_id(root)
    return {
        "folder": folder,
        "groupId": gid,
        "slug": slug,
        "version": VERSION,
        "minimalJavaVersion": MIN_JAVA,
        "recipesArtifactId": f"{folder}-{slug}-recipes",
        "skillsArtifactId": f"{folder}-{slug}-skills",
        "recipesCoordinates": f"{gid}:{folder}-{slug}-recipes:{VERSION}",
        "skillsCoordinates": f"{gid}:{folder}-{slug}-skills:{VERSION}",
        "skillNamePrefix": f"{folder}-{slug}-",
        "recipePackage": f"{gid}.advisor.{_pkg(folder)}.{_pkg(slug)}",
        "recipesDir": f".advisor/recipes/{slug}",
        "skillsDir": f".advisor/skills/{slug}",
        "mappingFile": f".advisor/mappings/{slug}.json",
        "registryFile": ".advisor/config.json",
    }
