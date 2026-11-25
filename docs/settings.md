# Facility / user defaults

Studios can set defaults (templates, network roots, formats, frame numbering, token delimiters, OCIO config...) in TOML, layered lowest to highest:

1. Built-in defaults.
2. **User:** `pipedream.toml` in the pack folder (ignored by git).
3. **Facility:** the file in the `PIPEDREAM_COMFYUI_CONFIG` environment variable.

A key applies when present and valid; invalid values, unknown keys and syntax errors print one `[Pipedream] Settings warning:` and are ignored. Files are read at startup. [`pipedream.example.toml`](../pipedream.example.toml) lists every key with its default and description; copy it and uncomment what you need:

```toml
[output]
path_mode = "absolute"
base_path = '\\server\shows'          # single quotes keep backslashes
template = "{project}/{shot}/comp/{shot}_{version}"
format = "exr"

[tokens.extra]
facility = "FacilityName"

[ocio]
config = "custom file"
config_path = '\\server\pipeline\ocio\config.ocio'
```

| Table | Keys |
|-------|------|
| `[output]` | `template`, `path_mode`, `base_path`, `format`, `fps`, `crf`, `create_dirs`, `overwrite`, `save_metadata`, `prores_profile` |
| `[load]` | `file`, `path_mode`, `base_path` |
| `[exr]` | `precision`, `compression`, `colorspace`, `metadata_prefix` |
| `[sequence]` | `frame_padding`, `start_frame`, `frame_separator` |
| `[tokens]` | `open`, `close`, `date_format`, `time_format` |
| `[tokens.extra]` | Any fixed tokens (`frame` is reserved) |
| `[tokens_to_string]` | `template` |
| `[project]` | `version`, `auto_increment_version` |
| `[ocio]` | `config`, `config_path`, `in_colorspace`, `out_colorspace`, `display`, `view` |
| `[sound]` | `sound`, `volume`, `play_when` |
| `[profiler]` | `enabled`, `vram_gb`, `ram_gb`, `vram_per_node`, `export_sidecar` |

New nodes start with these values (saved workflows keep theirs), and inputs missing from an API prompt use them. Delimiters, date/time formats, extra tokens and the frame separator apply wherever tokens resolve (see [tokens](tokens.md)). The token panel and sidecar name the settings files in use.

The `[output]` table applies to [PD Save](../web/docs/PDSave.md) (the setting names keep `output`).

## Deploying on Windows

Set the variable machine-wide (Group Policy Preferences or a script), then restart ComfyUI:

```bat
setx PIPEDREAM_COMFYUI_CONFIG "\\server\pipeline\comfyui\pipedream.toml" /M
```

## For maintainers

`core/settings.py` is the single source for validation and the example file. After changing it, run `python -m core.settings > pipedream.example.toml` and `python -m unittest discover -s tests`.
