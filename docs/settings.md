# Facility / user defaults

Studios can set defaults (templates, network roots, formats, frame numbering, token delimiters, OCIO config...) in TOML, layered lowest to highest:

1. Built-in defaults.
2. **User:** `pipedream.toml` in the pack folder (ignored by git).
3. **Facility:** one shared file, found as described in [Finding the facility file](#finding-the-facility-file).

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

New nodes start with these values (saved workflows keep theirs), and inputs missing from an API prompt use them. Delimiters, date/time formats, extra tokens and the frame separator apply wherever tokens resolve (see [tokens](tokens.md)). The token panel and sidecar name the settings files in use, and how the facility file was found.

The `[output]` table applies to [PD Save](../web/docs/PDSave.md) (the setting names keep `output`).

## Finding the facility file

The facility file is named by a pointer file, `pipedream_facility.txt`. The first of these that names a file is used:

1. `pipedream_facility.txt` in ComfyUI's user folder (`ComfyUI/user/`, or the folder given with `--user-directory`).
2. `pipedream_facility.txt` in the pack folder.

Pipedream doesn't read environment variables: the Comfy Registry's security scan flags them, and a file in a known place is easier to inspect and deploy. See [Pipeline integration](pipeline.md) for the rest of the pipeline picture.

A pointer file is plain text holding just the path of the facility TOML:

```text
# Pipedream facility settings
\\server\pipeline\comfyui\pipedream.toml
```

Blank lines and `#` comments are skipped, quotes around the path are fine, and a relative path is relative to the pointer file's folder. A pointer file that names no path is skipped with a warning; a facility file that cannot be found warns and is ignored.

Why these places:

- **ComfyUI's user folder** is the recommended place. ComfyUI-Manager replaces the pack folder when it reinstalls or updates the pack, but leaves `ComfyUI/user/` alone, so the pointer survives updates. It sits at the same place in every install, so a deployment script or Group Policy can copy one small file there without knowing anything about the pack.
- **The pack folder** works for a single machine or a portable install, but an update can delete it. It is git-ignored, like the user `pipedream.toml`.
- There is no `facility_path` key in the user `pipedream.toml`: that file also lives in the pack folder, so it has the same update problem, and the location of the facility file is machine setup rather than a setting.

## Deploying on Windows

Put the shared `pipedream.toml` on the network, then give each workstation and render node a pointer file. With Group Policy Preferences, add a **Files** item that copies `\\server\pipeline\comfyui\pipedream_facility.txt` to `<ComfyUI>\user\pipedream_facility.txt`; from a deployment script:

```bat
copy /Y "\\server\pipeline\comfyui\pipedream_facility.txt" "C:\ComfyUI\user\pipedream_facility.txt"
```

Restart ComfyUI afterwards. To move the facility file later, edit the one pointer file on the share and push it again (or point every pointer at a path that does not change).

The startup line and the token panel say which file was used, e.g. `settings: facility \\server\pipeline\comfyui\pipedream.toml (from pointer C:\ComfyUI\user\pipedream_facility.txt), user (none)`.

### Moving from the environment variable

Before 0.3.0 the facility file was named by the `PIPEDREAM_COMFYUI_CONFIG` environment variable. 0.3.0 no longer reads it, so a machine that only has the variable starts with no facility settings (the startup line says `facility (none)`). Deploy the pointer file as above, then remove the variable:

```bat
reg delete "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PIPEDREAM_COMFYUI_CONFIG /f
```

## For maintainers

`core/settings.py` is the single source for validation and the example file. After changing it, run `python -m core.settings > pipedream.example.toml` and `python -m unittest discover -s tests`.
