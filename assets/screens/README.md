# Screenshots

Raw simulator shots, copied from the app repo's App Store set —
`provaro/fastlane/screenshots/raw/<device>/en-US`. One directory per device,
because the app is sold as iPhone *and* iPad and the page carries both:

| Here | Raw size | Device |
|---|---|---|
| `iphone/` | 1206x2622 | iPhone 16 Pro @3x |
| `ipad/` | 2064x2752 | iPad Pro 13" M4 @2x |

`<device>/framed/` holds the same shots composited into that device's frame by
`tools/frame-screens.py`, **written as `.webp`** (#17) — the raw shots in here
stay PNG because they are the input, not what the page serves. The script globs
`*.png` per device, so a rename here only needs a re-run (and a delete of the
old file in `framed/`). Run it with no
arguments for both devices, or name one — `python3 tools/frame-screens.py ipad`.

Framed output is downscaled on the way out. The frames are 1406 and 2264 pixels
wide and the page renders them between 152 and 264 CSS pixels, so full
resolution would be megabytes no display can spend.

## The iPad is not the iPhone shot made bigger

Worth knowing before swapping one for the other: the iPad runs a split view, so
`report-editor` and `document-preview` show the reports list down the left with
the open job beside it, and `report-library` shows the list with an empty detail
pane. Only `markup` is the same full-screen scene on both. The alt text in
`index.html` says so, and should keep saying so.

## They are renamed on the way in, on purpose

Upstream the files carry a number — `1-document`, `2-markup`, `3-report`,
`5-branding`, `7-reports`. **That number is the App Store slot, not a step in
the walk**, and the app repo says so in `provaroUITests/ScreenshotTests.swift`:
the capture walk has to go list → report → markup → document because that is the
only order the app can be navigated in, while the listing wants the finished
document first, so `document` is `-1-` and `reports` is `-7-`.

Read as a step order — which is what this site did until #11 — you pair "step 1,
photograph the work" with the export sheet and "step 3, hand over the report"
with the editor. Dropping the numbers removes the thing that invites the mistake.

| Here | Upstream | What it shows |
|---|---|---|
| `report-editor.png` | `3-report` | The job editor: sections, photo thumbnails, captions, "Preview & export" |
| `markup.png` | `2-markup` | The markup editor: a photo with a red arrow, tool bar |
| `document-preview.png` | `1-document` | The PDF preview/export sheet: layout picker, page count and size, Share |
| `branding.png` | `5-branding` | "Your business" — logo and company details |
| `report-library.png` | `7-reports` | The reports library |

`4-standard-texts` and `6-layouts` exist upstream but are not used here.

## There is no camera screenshot

Step 1 on the page talks about photographing the work, and no screenshot shows
the camera. That is not an oversight to be tidied up later: a simulator has no
capture device, so `CaptureView` renders its no-camera state and the scene
cannot be captured by the automated run at all (`ScreenshotTests.swift`, and
`provaro#114`). Getting one means capturing by hand on a real device. Until
then, step 1 shows the editor and its copy is written to match it.
