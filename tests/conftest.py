"""A tiny git repo with a Python package and two notes, rebuilt per test session."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

FILES = {
    "src/pkg/__init__.py": "",
    "src/pkg/a.py": '''\
CONST = 1
TEMPLATE = """\\
engine:
  type: x
"""

def baz(x):
    return x

@dataclass
class Foo:
    level: int = 0

    def bar(self, y: int) -> int:
        return y

    def shared(self):
        return 1

    def unmentioned(self):
        return 0
''',
    "src/pkg/sub/__init__.py": "",
    "src/pkg/sub/b.py": '''\
def baz(x):
    return -x

class Qux:
    def shared(self):
        return 2

    def only_here(self):
        return 3
''',
    "src/pkg/thing.py": "def go():\n    pass\n",
    "tests/test_x.py": "def baz():\n    pass\n",
    "vault/Modules/a.md": "---\ntags: [x]\n---\n# a.py\n\n`Foo` is a dataclass; `Foo.bar` calls `baz` and `shared`; `CONST` is `1`; `TEMPLATE` has two keys. See `sub/b.py:3` and `only_here()`.\n",
    "vault/Concepts/idea.md": "# An idea\n\nUses `baz`, `Qux`, `nothing_here`, `visible_to: public`, `$HOME`, `id`.\n",
    "vault/Reference/Review 2026-01-01.md": "# Review 2026-01-01\n\nAt this date `baz` returned x and `Foo.bar` had one arg.\n",
    "vault/Sessions/log.md": "---\nlivedocs: snapshot\n---\n# Log\n\nWe changed `baz` today.\n",
    ".livedocs/config.json": '{"vault": "vault", "snapshot_globs": ["Reference/Review *"]}\n',
}


@pytest.fixture  # per test: the stamp/check tests mutate the repo
def mini_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("mini")
    for rel, content in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    return root


TS_FILES = {
    "tsconfig.json": '{\n  // Astro-style config\n  "extends": "astro/tsconfigs/strict",\n  "compilerOptions": { "baseUrl": ".", "paths": { "@/*": ["src/*"], }, },\n}\n',
    "wrangler.jsonc": '{\n  "name": "site", // the worker\n  "compatibility_date": "2026-10-01",\n  "assets": { "directory": "./dist", "not_found_handling": "404-page" },\n}\n',
    "astro.config.mjs": 'import { defineConfig } from "astro/config";\n\nexport default defineConfig({\n  site: "https://ellerm.com",\n  trailingSlash: "never",\n});\n',
    "src/lib/util.ts": '''\
// Helpers.
export function add(a: number, b: number): number {
  return a + b;
}

export const mul = (a: number, b: number) => a * b;

export interface Props {
  title: string;
  onClick?(e: MouseEvent): void;
}

export type Id = string | number;

export class Box {
  static count = 0;
  constructor(public w: number) {}
  area(): number {
    return this.w * this.w;
  }
  other(): number {
    return 1;
  }
}

export enum Color { Red, Green }

const config = { title: "site", theme: { color: "red", font: "serif" } } as const;
export { config as siteConfig };
''',
    "src/modules/projects/schema.ts": 'import { z } from "zod";\n\nexport const projectSchema = z.object({\n  title: z.string(),\n  tags: z.array(z.string()),\n}).strict();\n',
    "src/components/Header.tsx": '''\
import { add } from "../lib/util";

export default function Header({ title }: { title: string }) {
  return <h1 className="x">{title} don't // not a comment</h1>;
}
''',
    "src/components/Footer.tsx": 'export default () => <footer>bye</footer>;\n',
    "src/components/index.ts": 'export { default as Header } from "./Header";\nexport { default as SiteFooter } from "./Footer";\n',
    "src/components/ProjectCard.astro": '''\
---
import Header from "./Header.tsx";
interface Props {
  title: string;
}
const { title } = Astro.props;
---
<!-- a card -->
<article class="card">
  <Header title={title} />
</article>
''',
    "tests/util.test.ts": 'import { add } from "../src/lib/util";\nexport function add() { return 0 }\n',
    "vault/Modules/util.md": "# src/lib/util.ts\n\n`add(a, b)` sums; `mul` multiplies. `Box.area()` squares `Box.w`. `siteConfig.theme.color` is red; `Props.title` is required.\n",
    "vault/Modules/components.md": "# components\n\n`<Header />` renders the title; `@/components/Footer` is a footer; `<ProjectCard />` wraps a `Header`.\n",
    "vault/Concepts/deploy.md": "# Deploy\n\nAssets come from `wrangler.jsonc#assets.directory`; the site URL is `site` in `astro.config.mjs`; `projectSchema.title` is a string.\n",
    ".livedocs/config.json": '{"vault": "vault"}\n',
}


@pytest.fixture
def ts_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("tsmini")
    for rel, content in TS_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    return root
