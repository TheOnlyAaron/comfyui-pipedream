# 05 — Colour with OCIO

Colourspace, display and LUT transforms with OpenColorIO. Runs as is once `opencolorio` is installed (see the main README).

- **PD OCIO Transform** converts the sRGB image to scene-linear `ACEScg` (built-in ACES studio config); **PD Output** writes it as `pipedream_demo/color_acescg.exr`.
- **PD OCIO Display** applies the ACES 2.0 SDR output transform for an sRGB monitor.
- **PD OCIO Apply LUT** is bypassed: set `lut_path` to a `.cube`/`.3dl`/`.spi3d` file, then un-bypass it (Ctrl+B).

Try `Linear Rec.709 (sRGB)` or `Linear Rec.2020` as `out_colorspace`, or your studio config with `config` = `custom file`.

**Nodes:** PD Load, PD OCIO Transform, PD OCIO Display, PD OCIO Apply LUT, PD Output, Preview Image
