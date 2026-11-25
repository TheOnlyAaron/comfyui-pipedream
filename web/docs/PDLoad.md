# PD Load

Loads an image, an image sequence or a video from any local or network path, and reads back what PD Save wrote: its tokens, its sequence and its EXR metadata. Use it for plates and renders that live outside ComfyUI's input folder.

![PD Load](media/PDLoad.png)

## Typical use
1. Paste a file's full path into `file` (Explorer: shift+right click, *Copy as path*), or drop files on the node's drop zone.
2. Check the panel and preview after it loads. **load** runs just this node.
3. Connect `images` (and `mask`) downstream. To read a PD Save output back, link PD Save's `path` into `file`.

[02 Load and save](https://github.com/theonlyaaron/comfyui-pipedream/tree/main/workflows/02_load_and_save) loads a file, writes a sequence and reads it back with `sequence_mode`. [03 Video frames](https://github.com/theonlyaaron/comfyui-pipedream/tree/main/workflows/03_video_frames) reads an mp4 back as a clip.

![PD Load to PD Save to read back](media/group_load_save.png)

<!-- media: clip, 10 s: dropping a sequence on PD Load's drop zone -->

## How it works

### Getting a file in
- **Paste a path** into `file` or `base_path`. Quotes are removed, the path is split into folder and name, `path_mode` switches to `absolute` and the file loads. Network files load in place.
- **Drop files** from Explorer onto the drop zone (anywhere on the node in the classic canvas). Browsers do not reveal a dropped file's path, so the files are copied to ComfyUI's `input/pipedream` folder (overwriting same-named files) and loaded from there in `relative` mode. Drop every frame of a sequence, plus its sidecar for the tokens. For files on a share, paste the path instead.
- **Copy Path** copies the full path of the file the widgets point at, resolved from `path_mode`, `base_path` and `file`, for Explorer, Finder or Nuke.
- **load** (or the selection toolbar's run button) runs just this node.

### Where and what
- `relative` reads from ComfyUI's input folder; `absolute` from `base_path`. A full path in `file` (such as PD Save's `path`) is used as is and ignores `base_path`.
- `file` may include the extension or leave it to `format`. `auto` tries every type and stops if more than one matches.
- Images: exr, png, jpg, webp, tif, dpx, bmp. Video: mp4, mov, webm, mkv, avi, m4v.

### Sequences
- Mark the frame with `####`, `%04d` or `{frame}`. PD Save's `name.1001.png` is found without a mark.
- `start_frame` (a frame number; 0 means the first on disk), `frame_count` (0 means all) and `every_nth` pick frames. Gaps are skipped and listed. `fps` is divided by `every_nth`.
- `sequence_mode` decides what a single numbered file loads (`shot.1002.exr` with `shot.1001.exr` beside it):
  - **auto** (default) loads the whole sequence unless it finds evidence of a single image: PD Save's sidecar (a single image's own `name.json` has no `sequence`; a sequence's names its pattern), frames of different sizes, or unpadded numbers of different lengths (`seed_1` ... `seed_10`, typical of wedges). Otherwise it guesses a sequence. The panel says what it decided and why.
  - **single file** loads just that file.
  - **sequence** loads every file named like it.
- A frame mark always loads a sequence.
- Workflows saved with the old `sequence_from_file` switch convert on load (on to auto, off to single file).

### Video
- `start_frame` is a frame index. `fps_from_file` (on) uses the video's rate; off, `fps` overrides it. Images always use `fps`.
- `video` is the file itself with default settings, otherwise the loaded frames as an in-memory VIDEO with matching audio.

### Colour, precision and alpha
- 16-bit PNG/TIFF and float EXR keep their precision.
- Alpha comes out as `mask` (1.0 = opaque); full opacity when the files have none. EXR is un-premultiplied. See [Alpha](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/docs/alpha.md).
- `exr_colorspace` **linear to sRGB** reverses PD Save's **sRGB to linear**. **as is** leaves values unchanged.

### Tokens and sidecar
- `file` accepts tokens (`{shot}_{version}`) from `context` and `wedge`, so a wedge can load a different file per job.
- A sidecar next to the media fills the `context` output. Incoming non-empty values win.
- Pipe `context` into [PD Tokens To String](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/web/docs/PDTokensToString.md) or back into PD Save to carry shot details along.

### EXR metadata
- For EXR, `exr_metadata` carries each frame's header attributes (structural ones are left out), for PD Save or [PD EXR Metadata Get](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/web/docs/PDExrMetadataGet.md). See [EXR metadata](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/docs/exr-metadata.md).

### Preview and panel
- One frame shows as an image; several as a playable clip. The panel lists the pattern, frames, size, alpha, fps and sidecar.

### What is hidden when
- `base_path` in relative mode; `sequence_mode` for video formats; `fps_from_file` for image formats; `exr_colorspace` unless exr or auto.
- The `audio` output for image formats other than exr; the `exr_metadata` output unless exr or auto.

### Changes on disk
- Changes are picked up on the next queue; unchanged files stay cached.
- With `context` or `wedge` linked, the first queue after opening a workflow re-reads once.

## Tips
- Outputs: `first_frame` is the first frame number of a sequence, or a video's start index (0 for one image). `path` is the first file loaded.
- If `auto` stops with several matches, give `file` an extension or set `format`.
- Defaults for `file`, `path_mode` and `base_path` come from the `[load]` settings table. See [Settings](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/docs/settings.md).
- Outside ComfyUI's input folder, paste the path rather than dropping, to avoid copying large sequences.

## See also
- [PD Save](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/web/docs/PDSave.md), [PD EXR Metadata Get](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/web/docs/PDExrMetadataGet.md), [PD Video To Images](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/web/docs/PDVideoToImages.md)
- Topic pages: [Tokens](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/docs/tokens.md), [EXR metadata](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/docs/exr-metadata.md), [Alpha](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/docs/alpha.md), [Settings](https://github.com/theonlyaaron/comfyui-pipedream/blob/main/docs/settings.md)

## Inputs and outputs
<!-- reference:start -->
<!-- reference:end -->
