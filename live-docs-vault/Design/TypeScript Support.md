---
type: design
status: draft
authority: specifies
summary: "Draft v0.1: livedocs for TypeScript, JavaScript, Astro and JSON config keys — tree-sitter parsing, drift where it can fingerprint, member hashes everywhere, module paths binding only their default export (P26–P31). Built in 0.2.0; measured in [[TS Run 1]]."
created: 2026-10-23
updated: 2026-10-23
reviewed: 2026-10-23
tags: [live-docs, design, typescript]
---

# TypeScript Support

> **Status: draft v0.1, 2026-10-23.** Requested by the user through the personal-website session (the user's new Astro site will use livedocs as its development framework). Everything here is built (branch `ts-support`, 0.2.0). The design choices are agent proposals P26–P31 in [[Decision Log]] until the user accepts them; measurements are in [[TS Run 1]].
> **Provenance:** drift facts were probed by the agent on 2026-10-23 with drift v0.10.1 (scratch repo, results below). Testbench facts come from detached clones of the user's gravity-works and scheduler-dojo repositories (`testbench/`, gitignored).

## 1. Why livedocs has to parse TypeScript itself

drift fingerprints TypeScript with tree-sitter, but what it can bind is narrow (probed 2026-10-23, drift v0.10.1):

| Target | drift |
|---|---|
| `.ts`, `.js` top-level function, arrow const, interface, type, class, enum, const | binds |
| `.tsx` symbol in a file **with JSX** | "cannot compute fingerprint" (a plain function in a JSX-free `.tsx` binds: it parses `.tsx` without JSX) |
| `.jsx`, `.mjs`, `.cjs`, `.mts` symbols | nothing |
| `.astro` | whole file only |
| methods (`Box.area`), `default`, object keys | never |
| any file | binds as a whole file |

drift's TS symbol fingerprint also changes on a comment or reformat inside the symbol.

So a React/Preact/Astro component can never be anchored by drift, and the 0.1 gate on a TypeScript repo had only whole-file anchors from path mentions. On gravity-works that meant **766 hand acks and zero mechanical ones**: a whole-file anchor can never be proven benign. The ack reasons read "boot.ts change is the beatLineage ghostMode term only; framing/camera claims unmoved".

## 2. What is built

- **Parser (P26).** tree-sitter (`tree-sitter`, `tree-sitter-typescript`, about 4 MB of wheels) as a dependency, imported only when a repository has TS-family files. The TS grammar is used for `.ts/.mts/.cts` and Astro frontmatter, TSX for `.tsx/.js/.jsx/.mjs/.cjs` (JS may contain JSX). It parsed all 370 TS/JS files of both testbenches with zero errors in about 0.2 s.
- **Symbols** (`ts.py`): top-level functions, arrow-function and function-expression consts, classes (methods, fields, accessors, constructor parameter properties), interfaces and object type aliases (their members), enums (members), namespaces, constants; keys of top-level object literals to depth 4, through `as`/`satisfies` and through the first argument of a call (`defineConfig({…})`, `z.object({…}).strict()`, `defineCollection({…})`); closures declared directly in a top-level function (`bootHouse.probeStep`); `module.exports = {…}`.
- **Names.** `export { a as b }`; a default export by its file's name (`Footer.tsx` → `Footer`, `components/index.ts` → `components`); renaming re-exports through barrels (`export { default as Header } from './Header'`), followed to the definition. Same-name re-exports need nothing: the barrel is never a candidate.
- **Mentions** (`mentions.py`): `<ProjectCard />` (a component: TS/Astro functions, classes and constants only); `useStore<T>()` and `foo(a): Promise<T>` stripped to the name; TS extensions as paths (`porch01.level.ts` was misread as a dotted name); tsconfig alias paths with a leading `@` (`@/lib/x`, `@components/Card`). Bare home paths (`~/…`) are deliberately not paths.
- **Resolution** (`symbols.py`): tsconfig/jsconfig `paths` (through `baseUrl` and relative `extends`); extensionless and `index` module paths; dotted alias heads (`siteConfig.theme.color`); key paths below a constant (`theme.color` → `config.theme.color`); module notes cover folders (`# Modules/world` prefers `src/world/*`). A bare key name or closure name binds only within the note's own module (the Python rule for short attribute names); qualified it binds anywhere.
- **Targets (P27).** drift fingerprints the top-level symbol where it can (`.ts`, `.js`); everywhere else the file is bound and the member hashes decide. If drift refuses a symbol at stamp time (JSX in a `.js` file), the binding falls back to the file. If drift later reports a TS symbol missing that livedocs still parses, that is a change to compare, not `broken`.
- **Member hashes and classification.** A canonical token-and-structure form that ignores comments, whitespace, quote style, optional semicolons, trailing commas, redundant parentheses and JSX comments, but keeps grouping (`(a + b) * c` ≠ `a + b * c`). A class mention hashes its shell (head, decorators, fields, method names and modifiers) and a method mention the method, as in Python. Kinds: signature (parameters, return type, type parameters, async/generator, heritage; an Astro component's `Props`), decorator, body, comment-only. Comment-only edits, pure moves (a renamed component file) and changes to unmentioned members are acked mechanically at commit, as for Python.
- **Astro.** Frontmatter is parsed as TS (its declarations bind: `Props`, `getStaticPaths`); the component is `default`, aliased by its file name, hashed over frontmatter plus a normalised template (HTML and JSX comments removed, whitespace collapsed, `<script>` bodies as TS tokens, CSS comments dropped from `<style>`). A template edit flags every note that names the component; a comment edit does not.
- **JSON config keys (P30).** `package.json`, `tsconfig*.json`, `wrangler.json(c)`, `*.config.json`, any `.jsonc`: key paths (`wrangler.jsonc#assets.directory`, `compilerOptions.paths`) bind the file with the value's hash. Data files and lock files are not indexed. Comments and sibling keys never flag.
- **Mixed repositories (P28).** In a repository with Python and TypeScript, a note resolves in the language it is about first: the language of the module it is named after, else that of at least three quarters (and three) of its unambiguous mentions; it falls back to both. On scheduler-dojo it cut the Python-bound mentions whose binding changed from 0.1.4 from 61 to 23, all remaining ones in concept notes that genuinely span both languages.
- **Module paths (P29).** A backtick path to a code module binds that module's default export and nothing else; a module without one binds nothing by path (the rule `.py` paths have followed since run 1). `"file_anchors": true` in config restores whole-file binding. Paths to non-code files still bind the file.
- **Upgrade (P31).** Stamping now unlinks the note's bindings it no longer makes (orphans cost drift time and listed notes in `affected` for nothing). `livedocs rebind` acks every unedited note under the current rules.
- **Exclusions for JS/TS only** (Python indexing is unchanged): `__tests__`, `__mocks__`, `e2e`, `coverage`, `public`, `vendor`, `tmp`, `temp`, `scratch`, Playwright output; `*.test.*`, `*.spec.*`, `*.stories.*`; scratch files named `tmp-*` (gravity-works' root `tmp-find-eq2.mjs` defined names like `build`).
- **Hash schemes (P32).** Every member hash now carries its scheme in the stamp: `py2:` (Python, a dump that omits empty fields), `ts1:`, `json1:`. 0.1's Python hash used `ast.dump`, whose output differs between CPython 3.12 and 3.13, so a stamp made on one read as changed on the other (scheduler-dojo's agent re-stamped "under Python 3.12 so member hashes match CI"). `py2` hashes are identical on 3.12, 3.13 and 3.14 (checked); stored 0.1 hashes are still compared with the 0.1 function, so nothing needs re-stamping. The TS canonical form includes the grammar's node types, so `tree-sitter-typescript` is pinned exactly; a grammar upgrade must be a new scheme (`ts2`).
- **Fixes found on the way, all present in 0.1.4:** the gate blocked the first commit of a repository (no `HEAD`; the peer reported only the Stop hook); a note bound to an image crashed `check` and the gate when the image changed; the gate rebuilt the symbol index for every note it stamped.

## 3. Python is unchanged

Every mention in hpc-bridge's 61 live notes resolves and binds exactly as under 0.1.4: 0 changed resolutions, the same 1,669 binding mentions. The 3 newly extracted mentions are npm package names and a `.js` file, all unresolved. The exclusions, hints and resolution rules for `.py` paths are the old ones. Two deliberate changes are visible on Python repositories:
- `coverage` now counts what stamping binds, so its totals move: path mentions of `.py` files no longer count as anchored, and constants do.
- Move detection also covers whole-file anchors that carry members (Python constants): when a file is deleted and the constants a note mentions exist elsewhere with identical hashes, the anchor reads `moved` (benign) instead of `broken`.
- Stamping drops the note's orphaned bindings (P31), so `drift.lock` holds only what notes mention now.

## 4. Writing code and notes that stay cheap to anchor

Sent to the personal-website session on 2026-10-23 (provisional) and adopted there as conventions:
- Name symbols, not files: `getProjects()`, `projectSchema.title`, `<ProjectCard />`. A module path binds only its default export.
- Give exported symbols names unique across the repository; a bare name defined in every `src/modules/*/loader.ts` binds all of them.
- Title module notes with the path (`# src/modules/projects/schema.ts`).
- One default-exported component per file, named after the file.
- Keep logic in plain `.ts` (finest triggers); keep Astro frontmatter thin.

## 5. Limits

- Module resolution reads tsconfig/jsconfig `paths`, not bundler aliases (Vite `resolve.alias`, webpack).
- An Astro template is compared as normalised text, not parsed; a `<script>` that is not TS compares as text.
- YAML and TOML files bind only as whole files (no key anchors).
- A file with any syntax error has no member hashes (fail closed, as for Python): its notes read `unknown` for that binding.
- Gate cost scales with drift's per-binding work: about 3 s for gravity-works' 1,559 bindings (0.8 s for 0.1.4's 505). `drift check --changed` filters the output, not the work.
- Vue and Svelte are not supported.

## 6. Open

- Report the drift gaps upstream: JSX in `.tsx` files, `.mjs/.jsx/.cjs/.mts`, comment-sensitive TS fingerprints, and per-file caching in `check`.
- YAML key anchors (Quartz was the other stack candidate; not needed for Astro).

## Changelog

- **v0.1 (2026-10-23):** first draft, written with the 0.2.0 build.
