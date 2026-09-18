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

`img/poster.webp` and `img/poster-ipad.webp` are single frames pulled from
those films — the report editor, a few seconds in, rather than frame zero,
which on the iPad is the empty "Pick a report" state and sells nothing.

The bezels the films play behind, `img/device-frame*.webp`, are written by
`tools/frame-screens.py`; see `screens/README.md`.

`og/og-image.png` is the Open Graph card — the image that travels when the link
is pasted into a message or a post. It is drawn by `tools/make-og-card.py`
(#18); before that it was a committed PNG with nothing that rebuilt it, which
is how it came to be iPhone-only, off-palette, and carrying a logo badge on top
of its own headline. The generator asserts that nothing overlaps the headline,
so that particular bug cannot ship twice. Note that every scraper caches: a
redraw will not change a link somebody has already shared.

## `provaro-sample-report.pdf`

The document `#report` hands over, and the only piece of evidence on the page
that a reader can judge for themselves. **It is an export, not a facsimile.**
It came out of the shipping renderer on a simulator and was never touched
afterwards — `pdfinfo` still reports `Creator: Provaro`, and the red arrow on
page 2 is the app's own mark-up drawn as a vector at export resolution.

Reproduce it from the app repo (`~/Git/provaro`):

    xcrun simctl install <udid> build/dev/Build/Products/Debug-iphonesimulator/provaro.app
    xcrun simctl launch <udid> 12f.provaro \
        --reset --skip-welcome --seed-business --seed-pro on \
        --seed-trade bathroom --seed-report 4 \
        -AppleLanguages "(en)" -AppleLocale en_GB

then walk to `preview-and-export` and copy the PDF out of the app's container
(`xcrun simctl get_app_container <udid> 12f.provaro data`, then `tmp/`). Verify
it with the app repo's own gate before committing it here:

    Scripts/verify-pdf.sh assets/provaro-sample-report.pdf

`--seed-trade bathroom --seed-report 4` is deliberate: it is the same seed the
App Store screenshots use, so the sample and `screens/iphone/document-preview.png`
are the same three pages — 528 kB, A4, cover plus two sheets of two-up.

**Everything in it is provably fictional**, which is `DemoIdentity`'s job and
not ours: `.example` domains cannot be registered by anyone, `GB 123 4567 89`
fails the VAT mod-97 check, and `+44 20 7946 0958` is inside Ofcom's drama
range. Nothing here can accidentally be a real tradesperson.

**The cover stamps the day it was rendered.** A regenerated sample carries a
new date, which is the one thing about the file that ages; regenerate it when
the renderer changes, not on a schedule.

**Everything the page serves is WebP, apart from the logo and the App Store
badge** (#17). These are photographs, and the framed shots are photographs
behind a transparent silhouette, which is the case PNG is worst at: the served
image set went from 3.4 MB to 499 KB on the same pixels. Apple's badge stays
SVG because it is Apple's artwork and not ours to re-encode.
