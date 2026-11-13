# rpau-advisor-skills

Application Advisor skills for demos.

## `upgrade-spring-app`

A Claude Code skill that upgrades a Spring / Maven application with the
[Application Advisor](https://techdocs.broadcom.com/tnz-spring-app-advisor) MCP, and
**makes the next upgrade cheaper than this one**.

Run it with `/upgrade-spring-app` from the root of the application you want to upgrade.

### The idea: continuous improvement

The advisor covers many upgrade changes, but never all of them. Some code still fails to
compile after a step is applied, and someone has to fix it by hand. Without this skill that
fix is lost, and the next person fixes the same thing again.

The skill turns each hand fix into something the advisor applies on its own next time:

1. **Plan and confirm.** Gets the upgrade plan from the advisor, summarizes it, and waits for
   your confirmation.
2. **Apply one step.** Applies only the first step of the plan, once, then builds.
3. **Fix compile errors.** Reuses known skills first, otherwise fixes the code by hand with
   minimal changes. Each manually edited file is saved before and after the fix.
4. **Split and classify.** Breaks each fix into atomic edits and classifies each one as
   deterministic or not. Deterministic is the default.
5. **Create a recipe.** Every deterministic edit becomes an OpenRewrite recipe, written
   test-first, installed locally, and checked by re-running it on the original code to confirm
   it reproduces the hand fix.
6. **Create a skill only if needed.** An edit that a recipe cannot express (for example, it
   needs a design decision) becomes an advisor skill with a written reason. Recipes are always
   preferred, because they apply a fix with no model involved.
7. **Bind.** Adds the recipes and skills to the advisor mapping for the upgraded project, keyed
   by the version being upgraded from.
8. **Report.** Final build, the table of fixes and verdicts, and the environment variables you
   must configure.

### Example

Upgrading a small Spring Boot starter (Boot 3.5 → 4.0, Spring Security 6.5 → 7.0) with step 1 of
the plan:

- The advisor changed the Boot and Framework imports, but the build still failed because Spring
  Security 7 removed `AntPathRequestMatcher` and the classic `HttpSecurity` DSL
  (`http.csrf().disable().and()...`).
- The skill fixed both by hand, split the fix into five atomic edits, and judged all of them
  deterministic.
- It generated a recipe, `SpringSecurity7SourceFixes`, with 10 passing tests. Run on the original
  file, it matched the hand fix apart from one line wrap.
- It bound the recipe to the `spring-security` mapping under `6.5.x`. The next application on
  Spring Security 6.5 gets this fix applied by the advisor with no manual work.

### What the skill never does

- Apply more than one plan step per run.
- Publish anything. Maven `install` goes to `~/.m2` only, never `deploy`.
- Set or wrap the advisor's environment. It reports the variables for you to configure.
- Delete or weaken tests to get a green build.
- Commit, push, or open a PR unless you ask.

### Requirements

- `advisor` on the `PATH`, with its MCP server configured in Claude Code.
- `./mvnw` in the application.
- A JDK 17 or 21 for building and running recipes. Java 25 fails in the OpenRewrite Java 17
  parser.
- Python 3 for the helper scripts.

### Setup after a run

The advisor loads custom mappings only from environment variables on its MCP server. After a
run, the skill prints a block like this. Add it to the advisor MCP server configuration and
restart the server:

```
SPRING_ADVISOR_MAPPING_CUSTOM_0_FILEPATH=<repo>/.advisor/config.json
SPRING_ADVISOR_MAPPING_CUSTOM_1_FILEPATH=<repo>/.advisor/mappings/<slug>.json
SPRING_ADVISOR_MAPPING_CUSTOM_1_MERGE_STRATEGY=override
```

To check the binding, call `advisorUpgradePlanGet` on a checkout of the base commit. The new
recipe should appear in the recipe list of the step you bound it to.

### Layout

```
.claude/skills/upgrade-spring-app/
  SKILL.md      the skill instructions
  scripts/      scaffold.py (names and project scaffolding), bind.py (mapping and registry)
  templates/    Maven projects for recipes and skills
```

Copy `.claude/skills/upgrade-spring-app/` into the `.claude/skills/` folder of the application
you want to upgrade.
