---
name: Serene
description: A survey sheet for a family's questions, with a sage hellebore blooming out of it.
colors:
  warm-paper: "#e0dfd8"
  paper-raised: "#eae9e3"
  paper-sunken: "#d5d4cc"
  deep-olive: "#2e3d28"
  ink: "#1d2718"
  olive-muted: "#3b4734"
  olive-faint: "#4d5945"
  sage-green: "#a9b887"
  sage-deep: "#66784a"
  leaf-deep: "#7c8e58"
  rule: "#c7c7bc"
  rule-strong: "#9da58c"
  selection: "#cbd5ae"
typography:
  display:
    fontFamily: "Montserrat, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "min(6rem, 52cqi / (title length x 0.8))"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.02em"
  headline:
    fontFamily: "Montserrat, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "1.4375rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Montserrat, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    letterSpacing: "0.22em"
rounded:
  sm: "6px"
  tile: "7px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
  "7": "48px"
  "8": "64px"
components:
  button:
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0 24px"
    height: "44px"
  button-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.warm-paper}"
  sheet:
    backgroundColor: "{colors.paper-raised}"
    padding: "48px"
  nav-link:
    textColor: "{colors.olive-muted}"
    typography: "{typography.label}"
    height: "44px"
  nav-link-current:
    textColor: "{colors.ink}"
---

# Design System: Serene

## Overview

**Creative North Star: "The Survey Sheet"**

Serene is drawn on ruled paper. The page is warm paper, divided into cells by
hairlines, with a dot at every intersection. That dot is the same mark Serene
uses for "not yet known", so the canvas says the product's first truth before
any content loads. On the landing page a sage bloom grows out of the sheet:
two photographic hellebores and a closed bud on long stems, behind two panes
of clear liquid glass that lightly frost whatever lies behind them, the ruled
lines included. Entering Serene flies the main flower into the logo; the
surfaces themselves are drawn on the bare sheet.

The system is calm and botanical, but it is a working tool. Type does the
structural work: wide geometric capitals name things, and a hyperlegible face
carries everything a parent has to read. Colour comes from three swatches
only. Depth comes from frost and paper, never from shadows.

**Key Characteristics:**
- Ruled grid with dotted intersections, fixed under the page (6rem cells, 4rem on phones).
- The landing page is the only place the bloom grows. Every surface opens on a plate: a centred title in wide capitals on the bare sheet, with notes in both margins.
- Tracked uppercase labels with short 2rem hairline rules.
- The certainty notation (dotted, dashed, solid, struck) is the product's own visual language.
- The hellebore is the logo, the favicon and the first-load moment: one photographic petal builds every flower.

## Colors

Three swatches (Warm Paper, Sage Green and Deep Olive), with tints derived from them only.

### Primary
- **Deep Olive** (#2e3d28): the logo tile. Ink for titles, body text, rules that must be seen, focus rings and filled buttons is deep olive taken nearly to black (#1d2718, 11.6:1).

### Secondary
- **Sage Green** (#a9b887): the stems and the key of the bloom's photography. At 1.59:1 on the ground it is never used for text or for indicators on the light ground.
- **Sage Deep** (#66784a): sage darkened to 3.6:1 on the ground, for marks that must be seen (empty-state lines, the accent token).

### Neutral
- **Warm Paper** (#e0dfd8): the page ground. The sheet is always light; there is no dark mode.
- **Paper Raised** (#eae9e3): content sheets that lie on the grid.
- **Olive Muted** (#3b4734, 7.4:1) and **Olive Faint** (#4d5945, 5.6:1): secondary text.
- **Rule** (#c7c7bc) and **Rule Strong** (#9da58c): dividers and sheet borders. The grid lines use deep olive at 5%, and the dots near-black olive at 22%.


### Named Rules
**The Three Swatch Rule.** Every colour is one of the three swatches or a tint of one. No fourth hue, and no state colours until a state needs one. The bloom's photography is the one exception, chosen to sit inside the same sage-to-olive range.

**The Sage Is Not Ink Rule.** Sage never carries text on the light ground.

## Typography

**Display Font:** Montserrat (variable, self-hosted), falling back to Atkinson Hyperlegible Next
**Body Font:** Atkinson Hyperlegible Next (variable, self-hosted)

**Character:** Wide geometric capitals for naming, and a face built for legibility under stress for reading.

### Hierarchy
- **Display** (600, fluid up to 6rem, line-height 1, uppercase): surface titles on the plate. Size is computed from the title's length so every title fits its column on one line (two for long, multi-word titles).
- **Headline** (600, 1.4375rem, 1.2): section titles inside content sheets.
- **Body** (400, 1rem, 1.55, max 64ch): everything a parent reads.
- **Label** (600, 0.6875rem, 0.22em tracking, uppercase): navigation, the wordmark, legends, the record status title and buttons.

### Named Rules
**The No Kicker Rule.** A title stands alone. Nothing small and tracked sits above it.

## Layout

The grid is fixed to the viewport and aligned to the page gutter (1rem, 2rem from 45rem, 4rem from 64rem) and to the bottom of the top bar. From 64rem the plate is three columns: the lead in the left margin behind a 1px ink rule; the title centred; the tagline in tracked capitals over a 2rem rule in the right margin. The record status sits bottom-left, where a survey sheet keeps its legend, and a circled arrow sits bottom-centre. A 1px vertical rule closes the sheet bottom-right. Below 64rem the plate stacks: title, lead, record status. The landing plate has the same three columns, with the name SERENE (under a tracked kicker) centred over the bloom and the Enter Serene button bottom-centre. Its scene is larger than the plate and centred just below its middle, so the stems run off the foot; stacked, the landing is centred in the first screen with the flowers above the name, sized to the screen so the Enter button is always in view. On the landing page the top bar is held empty. Content follows in a raised sheet, at most 52rem wide and centred. The top bar shows inline links from 60rem; below that a menu sheet takes over.

## Elevation & Depth

Flat paper. Depth comes from two materials: the raised sheet (a tonal step and a 1px rule), and the bloom's liquid glass (a clear, faint frost over a light backdrop blur, a bright white rim with inset highlights for its thickness, and a faint shadow beneath). No other box shadows on the page.

## Shapes

Hairlines everywhere (1px). Pill buttons and a circular onward control, both with 1px ink outlines. Content sheets have square corners. The only rounded rectangle is the logo tile (22% radius).

## Components

- **Button:** a transparent pill with a 1px ink border and label type. It fills with ink on hover, on devices that can hover.
- **Navigation link:** label type in olive muted. Hover draws a dotted line underneath (a possibility); the current surface gets a solid 2px line that settles in from the left.
- **Menu sheet:** a full-height panel of plain warm paper. Each surface is listed in large tracked capitals with its summary underneath, separated by rules; the current one is marked with a short solid line.
- **Landing (Landing):** the page at `/`: bloom, kicker and name, lead, tagline and the Enter Serene button.
- **Plate (Page):** title, lead, tagline, record status and the onward link, as described under Layout.
- **Hellebore:** five copies of one photographic petal (`public/brand/bloom/petal.webp`), each pivoting at its base, around a cluster of stamens. Sized by `--petal-w`, `--petal-h` and `--centre`.
- **Bloom (BloomArt):** a square scene in percentages and container units: three grained stems, a back and a main hellebore, the bud (`bud.webp`), and two glass panes. Decorative and hidden from assistive technology.
- **Causal Twin map:** a raised sheet dotted like the page, with a hairline toolbar (zoom in, zoom out, fit to view) above it rather than over it. Variables are square paper tiles in ink; links are drawn in the certainty notation with an arrowhead, and each carries a paper label naming its kind in tracked capitals over its statement (narrow screens show the kind only). Refuted links stay on the map, struck through with cross-ticks and their words struck; replaced links are drawn hollow. The selected link fills its label with ink and lays a selection-tint halo under its line. Layout is deterministic: causes before effects, left to right or top to bottom, whichever shows the whole map larger, and no label covers another label or a variable.
- **Logo (BloomMark):** the hellebore seen from above on a deep-olive tile. The favicon and icons are exported from it (`npm run brand:export`).

### Motion
On each fresh load of the landing page (`html[data-bloom="play"]`, set before paint): the grid fades in (900ms); the stems draw up (1100ms); as each stem arrives its flower rises as a closed cup (back at 450ms, main at 700ms) and the bud swells (600ms); each cup then unfurls petal by petal, 75ms apart, over 2600ms, and the stamens show as the petals settle; the glass frosts over at 1300ms and 1500ms; the name condenses from wide, blurred spacing at 1500ms; the margins and the Enter button arrive at 2100ms. Everything has settled by 3.8s, and any press, key, scroll or touch ends it at once.

Entering Serene: the glass, stems, bud, back flower and words fade (320ms); a copy of the main flower then flies into the logo's place over 1000ms, its horizontal and vertical motion on different curves so it travels in an arc, shrinking and turning from 16deg to the logo's 4deg. As it lands (`html[data-enter]`) the deep-olive tile darkens in under it, the name draws out of the logo, and the five surfaces arrive one after another, 70ms apart; Today opens beneath. Reduced motion replaces all of this with fades. Petals use `cubic-bezier(0.77, 0, 0.175, 1)` (slow in, slow out); everything else uses `cubic-bezier(0.16, 1, 0.3, 1)`.

## Do's and Don'ts

- **Do** draw certainty with line style: dotted, dashed, solid, struck, and hollow for a replaced belief.
- **Do** let the grid show; put long text on a raised sheet or a paper strip.
- **Do** keep every keyframe animating *from* a hidden state to the drawn default, so content is visible without scripts.
- **Don't** put numbers, dates or counts on a surface before they are recorded (enforced by e2e).
- **Don't** add section numbers or pagers (01 / 03): the sequence carries no information.
- **Don't** use sage for text on the light ground.
- **Don't** add drop shadows or cards inside cards.
