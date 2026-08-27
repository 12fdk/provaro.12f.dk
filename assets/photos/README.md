# Job photos

These are not stock. They are cut out of the App Store screenshots in
`../screens/`, so the photo on the website is the same photo the app shipped —
including the red arrow, which was drawn by the app's own mark-up tool and is
not a redraw.

| File | Cut from | Region |
|---|---|---|
| `job-strip-out.webp` | `screens/iphone/markup.png` | the full-bleed photo band on the mark-up canvas, rows 661–1565 |
| `job-shower-marked.jpg` | `screens/iphone/document-preview.png` | the upper photo in the PDF preview, `(248, 852)` → `(957, 1360)` |

`job-strip-out` is the one the page serves, so it is WebP like the rest of the
served set (#17). `job-shower-marked` is not on the page — it is here as the
record of a cut — so it stays as it was.

The bands were found by looking for the contiguous run of non-black rows in the
mark-up screenshot rather than by eye, so a re-cut after new screenshots is a
matter of re-running the same crop rather than nudging numbers.

## Why there is no clean plate

An earlier pass tried to inpaint the arrow out of `job-strip-out.jpg` so the
site could draw its own arrow onto a bare photo and animate it. Both attempts —
Telea/Navier–Stokes inpainting, and a texture transplant from a shifted copy of
the same wall — left a visible diagonal seam wider than any arrow that would
plausibly cover it. The site uses the real marked-up photo instead, and the
drawn-annotation idea lives in the report callouts on `#report`, where the
target is HTML we control rather than a photograph.
