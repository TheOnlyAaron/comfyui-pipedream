# Installation

Restart ComfyUI after installing; the nodes appear under **Pipedream**. Install it one way only: a registry install and a git clone in `custom_nodes` at the same time register every node twice.

The only extra dependency is [OpenColorIO](https://opencolorio.org) (`opencolorio`, BSD-3), for the OCIO nodes. Everything else works without it. Video and EXR use PyAV, which ComfyUI already ships.

## ComfyUI Manager (recommended)

Open the **Nodes Manager** (Manager → Custom Nodes Manager), search for **PipeDream** and click **Install**. Manager installs the dependencies and handles updates.

- **Versions:** numbered versions (`0.2.0`, ...) are the stable releases published to the [Comfy Registry](https://registry.comfy.org/publishers/theonlyaaron/nodes/PipeDream). **nightly** is the newest commit on `main`. Minor versions (`0.3.0`, ...) also get a [GitHub release](https://github.com/theonlyaaron/comfyui-pipedream/releases) with their changelog notes.
- A version published in the last few hours may not be in Manager's cached list yet ("Cannot resolve install target 'PipeDream@latest'"): pick **nightly** from the version list, or restart ComfyUI later.

## comfy-cli

With [comfy-cli](https://docs.comfy.org/comfy-cli/getting-started) installed (`pip install comfy-cli`), in the Python environment ComfyUI runs with:

```bash
comfy node install PipeDream
```

`comfy node update PipeDream` updates it. When comfy-cli doesn't know which install to use, name it: `comfy --workspace "<path to ComfyUI>" node install PipeDream`.

## Git clone

For development, or to follow `main` without Manager. The commands use full paths, so they work from any folder.

### ComfyUI Desktop (Windows)

Desktop keeps each instance in `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\<instance name>`. Open the instance's **Terminal** tab (its Python is already active) and paste:

```powershell
$instance = "ComfyUI"   # the instance name shown in Desktop's instance list
$nodes = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\$instance\ComfyUI\custom_nodes"
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$nodes\comfyui-pipedream"
python -m pip install -r "$nodes\comfyui-pipedream\requirements.txt"
```

If `git clone` says the path does not exist, check the instance folder name with `dir "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs"`.

> Older Desktop versions (before instances) use `$nodes = "$env:USERPROFILE\Documents\ComfyUI\custom_nodes"` with the same last two lines.

### ComfyUI portable (Windows)

```powershell
$portable = "C:\ComfyUI_windows_portable"   # the folder holding run_nvidia_gpu.bat
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$portable\ComfyUI\custom_nodes\comfyui-pipedream"
& "$portable\python_embeded\python.exe" -m pip install -r "$portable\ComfyUI\custom_nodes\comfyui-pipedream\requirements.txt"
```

### Manual install (Linux, macOS, Windows)

Activate the Python environment ComfyUI runs with, then:

```bash
COMFY=~/ComfyUI   # the folder holding main.py
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$COMFY/custom_nodes/comfyui-pipedream"
python -m pip install -r "$COMFY/custom_nodes/comfyui-pipedream/requirements.txt"
```

## Updating, or trying a branch

Point `$pack` (PowerShell) or `pack` (bash) at the installed folder, e.g.:

```powershell
$pack = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\comfyui-pipedream"
```

```bash
pack=~/ComfyUI/custom_nodes/comfyui-pipedream
```

Then update (or switch to a branch such as `wedges`, and back with `checkout main`). These lines work in both shells:

```bash
git -C "$pack" pull
```

```bash
git -C "$pack" fetch origin
git -C "$pack" checkout wedges
```

Restart ComfyUI and refresh the browser afterwards. At startup the console lists `comfyui-pipedream` under "Import times for custom nodes" (or `IMPORT FAILED` with the reason). Keep one copy of the pack per ComfyUI: a stale copy in another `custom_nodes` folder or Desktop instance is the usual reason changes don't show up.
