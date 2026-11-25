# Tokens

Templates use `{name}` placeholders. They resolve in [PD Save](../web/docs/PDSave.md)'s `template`, [PD Load](../web/docs/PDLoad.md)'s `file` and [PD Tokens To String](../web/docs/PDTokensToString.md). Delimiters, date/time formats and fixed extra tokens are configurable (see [settings](settings.md)).

| Token | From |
|-------|------|
| `{project}` `{sequence}` `{shot}` `{version}` `{user}` | [PD Project Context](../web/docs/PDProjectContext.md) |
| `{<custom>}` | [PD Custom Context](../web/docs/PDCustomContext.md) |
| `{date}` `{time}` | Automatic (`YYYYMMDD`, `HHMMSS`) |
| `{frame}` | Frame number in PD Save sequences; `####` in PD Tokens To String; sequence frames in PD Load |
| `{<token>}` `{<token>_idx}` | [PD Wedge](../web/docs/PDWedge.md) row text and position (`000`, `001`...) |
| `{wedge_idx}` `{wedge_total}` | PD Wedge job number and job count |
| `{<extra>}` | `[tokens.extra]` settings (context values win) |

## Chaining

Contexts accept an incoming context: non-empty widgets override it, empty ones pass it through. Set up a base and override per shot:

```
PD Project Context (project=DITC, sequence=sq010)
  → PD Project Context (shot=sh010)
    → PD Custom Context (task=comp)
      → PD Save
```

## Versioning

`version` is a prefix plus a number (`v001`, `take_0042`); padding is kept (`v009` → `v010`). With `auto_increment_version`, each queued prompt uses the current version and the widget then advances, like a seed's `control_after_generate` (batch count 5 from `v001` runs `v001`–`v005`). **reset version** returns the node to its first version (`v017` → `v001`); **reset all versions in graph** (also in the canvas menu as *Pipedream: reset all versions*) resets every PD Project Context, subgraphs included.

## Related

- [Wedges](wedges.md) add `{<token>}`, `{<token>_idx}`, `{wedge_idx}` and `{wedge_total}`.
- [EXR metadata](exr-metadata.md): context tokens also come out as EXR attributes.
