---
name: upgrade-spring-app
description: Upgrade a Spring / Maven application with the Application Advisor MCP. Shows the upgrade plan, applies only its first step once, fixes the compilation errors that step causes, then splits each fix into atomic edits and turns every mechanical edit into a locally installed OpenRewrite recipe (the default), keeping a locally installed advisor skill only for what a recipe cannot express, binds both to the advisor mapping of the upgraded project, and reports the environment the user must configure. Use when the user asks to upgrade, migrate, or modernize an application (e.g. "upgrade this app to Spring Boot 4", "run the advisor upgrade").
---

# Upgrade a Spring application with Application Advisor

Goal: every upgrade is cheaper than the last. A fix found while upgrading one app becomes a recipe or a skill that the advisor applies the next time, in this app or another. Everything is local: Maven `install` into `~/.m2`, never `deploy`.

Use the advisor MCP tools (`advisorUpgradePlanGet`, `advisorUpgradePlanApply`, `advisorMappingSearch`, `advisorRecipeShow`) for advisor operations, with `pathToSourceCode` set to the repository root. Use `./mvnw`, not a system `mvn`.

## How this skill avoids improvisation

Mechanical work is done by scripts and templates shipped in this skill. Do not re-implement it by hand and do not invent names, paths or file formats.

| Need | Use |
|---|---|
| Names, coordinates, paths | `scripts/scaffold.py <slug>` prints them. Use them verbatim. |
| Maven projects for recipes and skills | created by `scaffold.py` from `templates/` |
| Edit the mapping and register the artifacts | `scripts/bind.py` |

Your judgment is needed only for: fixing compile errors, splitting a fix into atoms and classifying each, writing recipe code and its test, writing the skill text.

**Recipes are the default.** A recipe applies a fix with no model involved, so it is always preferred to a skill. A skill is the exception: it needs a written reason (section 4) and `bind.py` refuses it without one.

In the commands below, `SK=.claude/skills/upgrade-spring-app/scripts`. Run scripts from the repository root (the directory with `pom.xml`).

## Facts the scripts rely on (verified against the advisor source, do not "fix" them)

- The advisor loads custom mappings only from `SPRING_ADVISOR_MAPPING_CUSTOM_<n>_*` environment variables. It never reads `.advisor/mappings/` or `.advisor/config.json` by itself. **The user configures these variables** on the advisor MCP server. This skill never sets them, never wraps the advisor, and never starts it with a different environment. It only reports the exact values (section 6).
- `.advisor/config.json` is the **registry**: `rewriteArtifacts` (recipe jars) and `skillArtifacts` (skill zips), plus `"projects": []` (the schema requires `projects` or `initRecipes`). It is the first custom source (index 0) and uses the default merge strategy, which unions the lists.
- `.advisor/mappings/<slug>.json` is a custom source with merge strategy `override`. For a version entry, `override` **replaces** the built-in `recipes` and `skills` lists, so `bind.py` appends to the existing list instead of writing a new one.
- A mapping entry is keyed by the version the project is upgraded **from**. "Upgrade spring-security from 6.5.x to 7.0.x" means the entry `rewrite["6.5.x"]`.
- A skill reference in a mapping is `groupId:artifactId:skillName`. The version is not in the reference. It comes from `skillArtifacts`.
- The advisor unpacks skills of the first plan step into `.claude/skills/` after the recipes run. It rejects two skills with the same name, so names carry the application folder and the slug.
- A skill artifact is a zip (`type zip`) that holds `<skillName>/SKILL.md` at its root.

## 0. Preconditions

1. `advisor` is on the PATH (the MCP server runs `advisor mcp`).
2. `./mvnw -v` works. Building or running recipes under Java 25 fails (`NoClassDefFoundError: com.sun.tools.javac.code.Type$UnknownType` in the OpenRewrite Java 17 parser), so **find a JDK 17 or 21 now** and remember it as `RECIPE_JAVA_HOME`. Look with `/usr/libexec/java_home -V` (macOS), `sdk list java` or `ls ~/.sdkman/candidates/java`. Prefix every recipe build and every recipe run (section 5a) with `JAVA_HOME=$RECIPE_JAVA_HOME`. If none is installed, tell the user in this step and ask whether to install one. A missing JDK is never a reason to choose a skill over a recipe.
3. Run `git status`. If tracked files are modified, tell the user and ask before continuing. Untracked files do not matter.
4. Do **not** create `.advisor/config.json`, `.advisor/recipes/` or `.advisor/skills/` now. They are created in sections 5 and 6, only when there is something to put in them.
5. Never rename, move or rewrite recipes or skills created by an earlier run. Only add to them.

## 1. Get the plan and confirm

1. Call `advisorUpgradePlanGet`.
2. Summarize for the user: the steps, each project's `from -> to` version, and the recipes per step.
3. Ask for confirmation before applying. This is the stop point.

Keep the `from` version of every project in step 1. Section 6 needs it.

## 2. Apply the first step, once

1. Call `advisorUpgradePlanApply` exactly once.
2. Build: `./mvnw -B -q test-compile`.
3. If the only error is `Cannot load from object array because "this.hashes" is null`, that is javac failing while source errors exist. It hides the real errors. Run `./mvnw -B -q -Dmaven.compiler.fork=true test-compile` to see them, and use that flag for the fix loop. Finish with a build without the flag.
4. Do not apply further steps. List them in the final report.

## 3. Resolve compilation errors

Collect errors: `./mvnw -B -Dmaven.compiler.fork=true test-compile 2>&1 | grep -E "ERROR.*\.java|error:|cannot find symbol|does not exist"`.

1. **Reuse what is known.** Read every `SKILL.md` under `.claude/skills/` (skip `upgrade-spring-app`) and `.advisor/skills/*/skills/*/` whose description matches an error, and apply it. Use `advisorRecipeShow` to inspect a recipe the plan lists.
2. **Fix what remains by hand.** Minimal, in scope. Check that a replacement API exists in the new jar (`javap -cp <jar> <class>`) before using it. Never change tests to make them pass and never suppress errors. Say in the report if a test expectation had to change.
   Before you edit a source file by hand, copy it unchanged to `<scratchpad>/fix-before/<same relative path>`. After the fix compiles, copy it to `<scratchpad>/fix-after/<same relative path>`. Section 5a uses both.
3. A chain of calls stops being checked at its first error, so new errors can appear after a fix. Rebuild after each batch. After 3 failed rounds on the same error, stop and report it.
4. Keep a list of hand fixes. Each entry: the exact compiler message, the change, why it worked, the **project slug** whose upgrade caused it, and that project's **from version** from the plan. Fixes made by the advisor or by an unpacked skill are not listed.

## 4. Split and classify: recipe first

If nothing was fixed by hand, skip to section 8.

### 4.1 Split each fix into atoms

Never classify a whole fix. Split it into **atoms**: one edit per code shape, such as one class or method replaced, one call-chain link rewritten, one annotation or property key changed. A fix that changes a matcher class, renames a method and flattens a chain is three atoms.

### 4.2 Classify each atom: deterministic is the default

An atom is **deterministic** if you can write a `before`/`after` pair that holds for every shape of it you saw, even if the pair needs a rule for the arguments (pass them through, or map them). All of these are deterministic:

- renamed or moved class, method, annotation or property key
- removed API with a one-to-one replacement, with arguments passed through unchanged
- a call chain rewritten by fixed rules (for example classic DSL to lambda DSL: each link maps to a lambda, `.and()` is dropped)
- a replacement whose runtime behavior can differ for some inputs. The recipe still rewrites it and adds a `// TODO` marker where it cannot prove the inputs equivalent. Risk alone does not make an atom non-deterministic.
- a constructor or call form you cannot map cleanly. The recipe skips that form and leaves the compiler error, and the skill (if any) covers it.

An atom is **non-deterministic** only if a recipe cannot express the fix even with a marker or a skip rule. Typical reasons: the right replacement depends on information outside the code being rewritten (a design decision, a behavior the application must keep, several valid replacements with no way to choose), or the target shape depends on what the surrounding code does.

"Restructuring a call chain", "it behaves differently" and "it is hard to write" are **not** reasons.

### 4.3 Write the table, then act on it

Before section 5, write this table in your reply to the user, one row per atom:

| # | Compiler message | Before → after | Verdict | Reason |
|---|---|---|---|---|

For a non-deterministic row, the Reason column must name the specific decision or information a recipe lacks, and why a marker or a skip rule does not cover it. Use that text in section 5b and in `--why-not-recipe`.

- Every deterministic atom becomes a recipe (section 5a), even when the same fix also needs a skill.
- A skill covers only the atoms (or call forms) the recipe does not. If every atom is deterministic, create no skill.

## 5. Scaffold, name and install

For each distinct project slug in the list, run:

```
python3 -I $SK/scaffold.py <slug>
```

It creates what is missing (never overwrites) and prints these values. Use them verbatim:

| Value | Rule | Example |
|---|---|---|
| groupId | groupId of this application's `pom.xml` | `com.acme` |
| version | always `1.0.0-SNAPSHOT` | |
| recipes artifact | `<groupId>:<folder>-<slug>-recipes:<version>` | `com.acme:acme-security-starter-spring-security-recipes:1.0.0-SNAPSHOT` |
| skills artifact | `<groupId>:<folder>-<slug>-skills:<version>` | `com.acme:acme-security-starter-spring-security-skills:1.0.0-SNAPSHOT` |
| skill name | `<folder>-<slug>-<problem>` | `acme-security-starter-spring-security-classic-dsl-to-lambda` |
| recipe package | `<groupId>.advisor.<folder>.<slug>` (lowercase letters and digits only in the last two parts) | `com.acme.advisor.acmesecuritystarter.springsecurity` |
| recipes project | `.advisor/recipes/<slug>/` | |
| skills project | `.advisor/skills/<slug>/` | |

`<folder>` is the name of the repository root directory.

### 5a. Deterministic atoms: add a recipe

In `.advisor/recipes/<slug>/`. All Maven commands here run with `JAVA_HOME=$RECIPE_JAVA_HOME` (section 0).

1. **Write the test first.** In `src/test/java/<package path>/`, using `RewriteTest`: one `before`/`after` per shape you saw in the fix (take them from `<scratchpad>/fix-before` and `fix-after`), one case that must not change, and one case for each form the recipe skips or marks with `// TODO`. If you cannot write the `before`/`after` pair, the atom is not deterministic: go back to section 4.2.
2. A recipe class in `src/main/java/<package path>/`, extending `Recipe`, with display name and description. Make the test pass.
3. If the recipe emits or rewrites library types, add the real library as a **test-scope** dependency in the pom. A `JavaTemplate` cannot attribute a type it cannot see. If a type no longer exists in the new version, declare a small stub class as an extra `java(...)` source in the test.
4. Verify and install: `./mvnw -B -f .advisor/recipes/<slug>/pom.xml clean install`. It compiles, runs the tests and installs to `~/.m2`. It must succeed. Never run `deploy`.
5. **Prove it reproduces the hand fix.** For every file in `<scratchpad>/fix-before`:
   1. copy it over the working-tree file;
   2. run the recipe on the project: `JAVA_HOME=$RECIPE_JAVA_HOME ./mvnw -B org.openrewrite.maven:rewrite-maven-plugin:6.44.0:run -Drewrite.recipeArtifactCoordinates=<recipes coordinates> -Drewrite.activeRecipes=<recipe FQN>`;
   3. diff the file against `<scratchpad>/fix-after`. Differences caused by formatting only are accepted. Anything else means the recipe does not cover that atom: fix the recipe, or move the atom to the skill with a reason;
   4. copy `fix-after` back so the working tree holds the hand fix, and build with `./mvnw -B -q test-compile`.
   Do not skip this step. It is what shows the atom is deterministic.

### 5b. Atoms a recipe cannot express: add a skill

Only for rows of the section 4.3 table marked non-deterministic, or for call forms the recipe skips. If there are none, skip this section.

Create `.advisor/skills/<slug>/skills/<skill name>/SKILL.md`. The folder name and the frontmatter `name` are the skill name. Use this layout:

```markdown
---
name: <skill name>
description: <one line: the symptom and the upgrade it appears in>
---

## Problem
What breaks, with the exact compiler or runtime message.

## When it applies
The code shape or configuration that triggers it.

## Why not a recipe
The specific decision or information a recipe lacks, and why a `// TODO` marker or a skip rule does not cover it.
Name the recipe that handles the mechanical part of the same fix, if there is one.

## Fix that worked
Steps with before/after code. Why this fix and not the alternatives.

## Verification
The build command or test that confirms it.

## Source
Project, date, upgrade step.
```

Then package and install: `./mvnw -B -f .advisor/skills/<slug>/pom.xml clean install`. Check the zip: `unzip -l .advisor/skills/<slug>/target/*.zip` must list `<skill name>/SKILL.md`.

Never create a recipe or skill for a fix you have not verified with a build.

## 6. Bind to the mapping

For each slug, using the `from` version recorded in section 3:

1. If `.advisor/mappings/<slug>.json` is missing, call `advisorMappingSearch` with `pathToSourceCode` and `slug`. It saves the file there.
2. Run:

```
python3 -I $SK/bind.py --slug <slug> --from-version <from> \
    --recipe <recipe FQN> [--recipe ...] \
    --skill <skill name> [--skill ...] --why-not-recipe "<reason from the section 4.3 table>"
```

This appends the recipes and skills to `rewrite["<from>"]` in the mapping, creates `.advisor/config.json` if it does not exist, and registers the recipes and skills artifacts in it. It is idempotent. If it refuses (wrong package, wrong skill prefix, unknown version, `--skill` without `--why-not-recipe`, a skill whose `SKILL.md` has no `## Why not a recipe` section), fix your input. Do not edit the JSON by hand.

`--why-not-recipe` is required whenever `--skill` is given, and it is printed in the bind output so it reaches the report. A run that created only recipes passes no `--skill` and no `--why-not-recipe`.

If a fix touches several projects, bind it under each, but write the recipe or skill only once.

`bind.py` ends by printing the environment variables the advisor needs. Copy that block into the final report unchanged.

## 7. What is and is not verified

This run cannot see its own binding, because the advisor reads the mappings only through the environment variables the user configures. So:

- Verified in this run: the recipes build, pass their tests and install, and reproduce the hand fix on the original code (section 5a, step 5); the skills zip is built, installed and contains `<skill name>/SKILL.md`; `bind.py` accepted the entries.
- Not verified: that the advisor loads the mapping and applies the recipe, and that it unpacks the skill. Tell the user how to check, after they configure the environment and restart the advisor MCP server: call `advisorUpgradePlanGet` on a checkout of the base commit. The recipe FQN must appear in the recipe list of the step whose `from` version was bound, and `advisorUpgradePlanApply` unpacks the skills into `.claude/skills/`.

## 8. Final build and report

1. Run `./mvnw -B verify`. Report the result exactly, including `No tests to run`. A project without tests cannot show that behavior is unchanged. Say so.
2. For each recipe project: the `install` result and test count.
3. Report:
   - the plan step applied, and the remaining steps, which need another run of this skill
   - every compile error fixed, with a one-line cause
   - the section 4.3 table: every atom, its verdict and its reason
   - recipes created: project path, recipe FQN, coordinates, result, and whether the reproduction check (5a step 5) matched the hand fix
   - skills created: project path, skill names, coordinates, and the `--why-not-recipe` reason for each. If a skill was created for a fix that also has a recipe, say which atoms the skill covers.
   - mapping files changed and the entries added (slug, from version)
   - `.advisor/config.json`: created or updated, and what it now registers
   - the environment variables the user must configure (the block printed by `bind.py`)
   - what was left undone, or not verified, and why
4. Do not commit, push, publish, or open a PR unless the user asks.

## Rules

- Confirm before applying. Apply one step per run.
- Use the advisor MCP tools for advisor operations. Do not wrap, replace, or relaunch the advisor, and do not set its environment.
- Use the names the scripts print. Do not hand-edit mapping or registry JSON.
- Install locally only (`install`). Never `deploy` and never publish.
- Recipe first. Classify per atom (section 4). A skill needs a written reason, and "restructuring a call chain", "behaves differently" or "no JDK 17/21" are not reasons.
- Never delete or weaken tests to get a green build.
- Never change recipes or skills from earlier runs except by adding to them.
- Keep recipes and skills generic. No secrets, tokens or personal data in them.
