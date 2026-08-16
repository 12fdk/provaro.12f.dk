# The core-loop films

`preview.*` (iPhone) and `preview-ipad.*` are the App Store preview videos,
copied from the app repo's `provaro/fastlane/previews/<device>/en-US.mp4` and
re-encoded for the web. Both are 30 s, both are silent — the audio track is
dropped, because the page plays them in a device frame with no sound to give.

| File | Source | Native size |
|---|---|---|
| `preview.mp4` / `.webm` | `previews/iphone/en-US.mp4` | 886x1920 |
| `preview-ipad.mp4` / `.webm` | `previews/ipad/en-US.mp4` | 1200x1600 |

The `<video>` prefers the WebM and falls back to the MP4. Re-encode with:

    ffmpeg -i in.mp4 -an -c:v libx264 -profile:v high -crf 26 -preset slow \
           -pix_fmt yuv420p -movflags +faststart out.mp4
    ffmpeg -i in.mp4 -an -c:v libvpx-vp9 -crf 34 -b:v 0 -row-mt 1 \
           -pix_fmt yuv420p out.webm

That turns 15 MB and 6.8 MB of App Store master into roughly 1 MB each.

`img/poster.png` and `img/poster-ipad.png` are single frames pulled from those
films — the report editor, a few seconds in, rather than frame zero, which on
the iPad is the empty "Pick a report" state and sells nothing.

The bezels the films play behind, `img/device-frame*.png`, are written by
`tools/frame-screens.py`; see `screens/README.md`.
