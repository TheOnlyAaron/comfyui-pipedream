# 01 — Tokens

How tokens turn shot details into text. Runs as is: no model, no images, nothing written.

- **PD Project Context** holds `project`, `sequence`, `shot`, `version` and `user` (`demo` / `sq010` / `sh010` / `v001` / `jsmith`). Each becomes a token: `{project}`, `{shot}`, ...
- **PD Custom Context** adds tokens of your own on top: `task` = `comp`, `client` = `acme`.
- **PD Tokens To String** fills a template. Press **preview** on one to see the result in its panel without running anything else:
  - `{shot} {task} {version} by {user} for {client}` → `sh010 comp v001 by jsmith for acme`
  - `{project}/{sequence}/{shot}/{task}/{shot}_{task}_{version}.{frame}` → `demo/sq010/sh010/comp/sh010_comp_v001.####`
  - `Rendered {date} at {time}` uses the automatic tokens and needs no context.

The same templates name files in PD Save and find them in PD Load (see 02). Try `auto_increment_version` on PD Project Context, or rename a token in PD Custom Context and preview again: unknown tokens stay as `{name}` in the text.

**Nodes:** PD Project Context, PD Custom Context, PD Tokens To String (×3)
