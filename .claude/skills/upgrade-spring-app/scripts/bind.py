#!/usr/bin/env python3
"""Bind locally installed recipes and skills to an advisor mapping, and register their Maven artifacts.

Usage (from the repository root):
    python3 -I .claude/skills/upgrade-spring-app/scripts/bind.py --slug spring-security --from-version 6.5.x \
        [--recipe <recipe FQN> ...] [--skill <skill name> ... --why-not-recipe "<reason>"]

Recipes are the default. A skill is accepted only with --why-not-recipe (the specific decision a recipe cannot
express) and only if its SKILL.md has a non-empty "## Why not a recipe" section.

What it edits:
  .advisor/mappings/<slug>.json   rewrite["<from-version>"].recipes / .skills     (mapping must already exist)
  .advisor/config.json            rewriteArtifacts / skillArtifacts registry      (created here, only when needed)

--from-version is the version the project is upgraded FROM in the plan step that broke ("Upgrade spring-security
from 6.5.x to 7.0.x" -> 6.5.x). The advisor keys a mapping entry by its source version.

Existing entries are kept and new ones appended: with merge strategy "override" the advisor REPLACES the built-in
recipes/skills list of that version, so dropping the built-in entries would silently remove upgrade recipes.
Idempotent: running it twice changes nothing the second time.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from names import _pkg, names, repo_root  # noqa: E402


def is_ours(mapping: dict, group_id: str, folder: str) -> bool:
    """True if a mapping binds a recipe or skill generated for this application (by naming rule)."""
    recipe_prefix = f"{group_id}.advisor.{_pkg(folder)}."
    skill_prefix = f"{group_id}:{folder}-"
    for entry in mapping.get("rewrite", {}).values():
        if any(r.get("name", "").startswith(recipe_prefix) for r in entry.get("recipes") or []):
            return True
        if any(s.startswith(skill_prefix) for s in entry.get("skills") or []):
            return True
    return False


def environment(root: Path, n: dict) -> list:
    """The variables the advisor needs. The registry goes first (default strategy), mappings after it (override)."""
    sources = [(root / n["registryFile"], None)]
    for path in sorted((root / ".advisor/mappings").glob("*.json")):
        if is_ours(load(path), n["groupId"], n["folder"]):
            sources.append((path, "override"))
    lines = []
    for index, (path, strategy) in enumerate(sources):
        lines.append(f"SPRING_ADVISOR_MAPPING_CUSTOM_{index}_FILEPATH={path}")
        if strategy:
            lines.append(f"SPRING_ADVISOR_MAPPING_CUSTOM_{index}_MERGE_STRATEGY={strategy}")
    return lines


def why_not_recipe_section(skill_md: Path) -> str:
    """Text of the '## Why not a recipe' section of a SKILL.md ('' if the section is missing or empty)."""
    lines = skill_md.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == "## why not a recipe":
            body = []
            for following in lines[i + 1:]:
                if following.startswith("## "):
                    break
                body.append(following)
            return "\n".join(body).strip()
    return ""


def load(path: Path):
    return json.loads(path.read_text())


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def upsert_artifact(registry: dict, key: str, coordinates: str, extra: dict) -> str:
    """One entry per groupId:artifactId (the advisor takes the version from the registry)."""
    ga = coordinates.rsplit(":", 1)[0]
    items = registry.setdefault(key, [])
    for item in items:
        if item["coordinates"].rsplit(":", 1)[0] == ga:
            if item["coordinates"] == coordinates:
                return "already registered"
            item["coordinates"] = coordinates
            return "version updated"
    items.append({"coordinates": coordinates, **extra})
    return "registered"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--from-version", required=True, help="e.g. 6.5.x")
    parser.add_argument("--recipe", action="append", default=[], help="fully qualified recipe name")
    parser.add_argument("--skill", action="append", default=[], help="skill name (folder name in the skills zip)")
    parser.add_argument(
        "--why-not-recipe",
        help="required with --skill: the specific decision or information a recipe lacks, "
        "and why a // TODO marker or a skip rule does not cover it",
    )
    args = parser.parse_args()
    if not args.recipe and not args.skill:
        raise SystemExit("error: nothing to bind. Pass --recipe and/or --skill.")
    if args.skill:
        reason = (args.why_not_recipe or "").strip()
        if len(reason) < 40:
            raise SystemExit(
                "error: --skill needs --why-not-recipe with a real reason (at least 40 characters): the specific "
                "decision or information a recipe lacks. Recipes are the default; split the fix into atoms "
                "(SKILL.md section 4) and put every mechanical atom in a recipe."
            )

    root = repo_root()
    n = names(root, args.slug)
    report = []

    mapping_path = root / n["mappingFile"]
    if not mapping_path.is_file():
        raise SystemExit(
            f"error: {n['mappingFile']} does not exist. Download it first:\n"
            f"  call the advisorMappingSearch MCP tool with slug '{args.slug}' and this repository's path"
        )
    mapping = load(mapping_path)
    rewrite = mapping.get("rewrite", {})
    if args.from_version not in rewrite:
        raise SystemExit(f"error: no '{args.from_version}' entry in {n['mappingFile']}. Available: {sorted(rewrite)}")
    entry = rewrite[args.from_version]

    for fqn in args.recipe:
        if not fqn.startswith(n["recipePackage"] + "."):
            raise SystemExit(f"error: recipe '{fqn}' must live in package {n['recipePackage']}")
        recipes = entry.setdefault("recipes", [])
        if any(r.get("name") == fqn for r in recipes):
            report.append(f"recipe {fqn}: already bound")
        else:
            recipes.append({"name": fqn})
            report.append(f"recipe {fqn}: bound to {args.slug} {args.from_version}")

    for skill in args.skill:
        if not skill.startswith(n["skillNamePrefix"]):
            raise SystemExit(f"error: skill '{skill}' must start with '{n['skillNamePrefix']}'")
        skill_md = root / n["skillsDir"] / "skills" / skill / "SKILL.md"
        if not skill_md.is_file():
            raise SystemExit(f"error: {skill_md.relative_to(root)} does not exist")
        if not why_not_recipe_section(skill_md):
            raise SystemExit(
                f"error: {skill_md.relative_to(root)} has no non-empty '## Why not a recipe' section. "
                "Add it (see SKILL.md section 5b) before binding the skill."
            )
        report.append(f"skill {skill}: why not a recipe: {args.why_not_recipe.strip()}")
        reference = f"{n['groupId']}:{n['skillsArtifactId']}:{skill}"
        skills = entry.setdefault("skills", [])
        if reference in skills:
            report.append(f"skill {reference}: already bound")
        else:
            skills.append(reference)
            report.append(f"skill {reference}: bound to {args.slug} {args.from_version}")

    save(mapping_path, mapping)

    registry_path = root / n["registryFile"]
    registry = load(registry_path) if registry_path.is_file() else {"rewriteArtifacts": [], "skillArtifacts": []}
    if args.recipe:
        status = upsert_artifact(
            registry, "rewriteArtifacts", n["recipesCoordinates"], {"minimalJavaVersion": n["minimalJavaVersion"]}
        )
        report.append(f"rewriteArtifact {n['recipesCoordinates']}: {status}")
    if args.skill:
        status = upsert_artifact(registry, "skillArtifacts", n["skillsCoordinates"], {})
        report.append(f"skillArtifact {n['skillsCoordinates']}: {status}")
    # The advisor's coordinates schema requires "projects" or "initRecipes"; an empty list satisfies it.
    registry.setdefault("projects", [])
    save(registry_path, registry)

    print("\n".join(report))
    print(
        "\nThe advisor loads local mappings only from these environment variables. "
        "The user configures them on the advisor MCP server and restarts it:"
    )
    print("\n".join(environment(root, n)))


if __name__ == "__main__":
    main()
