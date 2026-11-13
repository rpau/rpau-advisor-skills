#!/usr/bin/env python3
"""Idempotently scaffold the local recipes and skills Maven projects for ONE mapping slug.

Usage (from the repository root):
    python3 -I .claude/skills/upgrade-spring-app/scripts/scaffold.py <slug>

Creates only what is missing and never overwrites. Prints every derived name as JSON; use those names verbatim.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from names import names, repo_root  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def render(template: Path, target: Path, values: dict) -> bool:
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    text = template.read_text()
    for token, value in values.items():
        text = text.replace(token, value)
    target.write_text(text)
    return True


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    root = repo_root()
    n = names(root, sys.argv[1])
    created = []

    common = {"@GROUP_ID@": n["groupId"], "@VERSION@": n["version"], "@SLUG@": n["slug"], "@FOLDER@": n["folder"]}

    recipes = root / n["recipesDir"]
    if render(TEMPLATES / "recipes/pom.xml", recipes / "pom.xml", {**common, "@ARTIFACT_ID@": n["recipesArtifactId"]}):
        created.append(f'{n["recipesDir"]}/pom.xml')
    package_path = n["recipePackage"].replace(".", "/")
    for source_set in ("main", "test"):
        (recipes / f"src/{source_set}/java/{package_path}").mkdir(parents=True, exist_ok=True)

    skills = root / n["skillsDir"]
    if render(TEMPLATES / "skills/pom.xml", skills / "pom.xml", {**common, "@ARTIFACT_ID@": n["skillsArtifactId"]}):
        created.append(f'{n["skillsDir"]}/pom.xml')
    if render(TEMPLATES / "skills/src/assembly/skills.xml", skills / "src/assembly/skills.xml", common):
        created.append(f'{n["skillsDir"]}/src/assembly/skills.xml')
    (skills / "skills").mkdir(parents=True, exist_ok=True)

    if render(TEMPLATES / "advisor.gitignore", root / ".advisor/.gitignore", common):
        created.append(".advisor/.gitignore")

    print(json.dumps({**n, "created": created}, indent=2))


if __name__ == "__main__":
    main()
