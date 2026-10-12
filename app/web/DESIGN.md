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
  paper-lifted: "#f1f0eb"
  paper-wash: "#e8ebdf"
  on-olive: "#eceee4"
  on-olive-strong: "#f4f5ee"
  on-olive-muted: "#c9d3b1"
  safe-green: "#4a6430"
  safe-green-tint: "#e3e8d3"
  safe-amber: "#865611"
  safe-amber-tint: "#f0e3c8"
  safe-red: "#8e2f22"
  safe-red-tint: "#f1dcd4"
  on-red: "#fbf3f0"
typography:
  display:
    fontFamily: "Montserrat, Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "clamp(2.125rem, 1.4rem + 2.6vw, 3.5rem)"
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
  reference:
    fontFamily: "ui-monospace, monospace"
    fontSize: "0.6875rem"
rounded:
  rung: "2px"
  sm: "6px"
  md: "10px"
  lg: "16px"
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
    backgroundColor: "{colors.paper-lifted}"
    rounded: "{rounded.lg}"
    padding: "24px"
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
surfaces themselves are working sheets laid on the same ruled paper.

The system is calm and botanical, but it is a working tool. Type does the
structural work: wide geometric capitals name things, and a hyperlegible face
carries everything a parent has to read. Colour comes from three swatches
only. Depth comes from frost and paper, never from shadows.

**Key Characteristics:**
- Ruled grid with dotted intersections, fixed under the page (6rem cells, 4rem on phones).
- The landing page is the only place the bloom grows. Every surface opens on a short title block: its name in wide capitals, the one question it answers, what it holds, and the record legend; then straight into the work.
- One thing leads each surface (Today's current investigation, the experiment waiting for a decision, the selected link's explanation); the rest recede in size, weight and lift.
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


- **Paper Lifted** (#f1f0eb): working sheets, panels and cards laid on the grid. **Paper Wash** (#e8ebdf): a sage-washed paper for the one item a surface leads with.
- **Deep Olive as a ground**: the one action a surface leads with ("What Serene will do next") is set in deep olive with On Olive text (#eceee4, #f4f5ee; #c9d3b1 for its label).

### Safety
Safety is the one state that needed hue, because the kernel names its classes after colours. Each class is always its name, its mark and its word together, never hue alone:
- **GREEN** (#4a6430 on #e3e8d3): a small leaf, not a tick. Low risk is not Serene saying yes.
- **AMBER** (#865611 on #f0e3c8): an hourglass, a dashed border. Take time to decide.
- **RED** (#8e2f22, filled; #f1dcd4 tint): a barred circle, hatched like a struck line. It is closed: no control to approve exists.

### Named Rules
**The Three Swatch Rule.** Every colour is one of the three swatches or a tint of one, with one exception: the three safety hues above, used only for safety. The bloom's photography is chosen to sit inside the same sage-to-olive range.

**The Sage Is Not Ink Rule.** Sage never carries text on the light ground.

## Typography

**Display Font:** Montserrat (variable, self-hosted), falling back to Atkinson Hyperlegible Next
**Body Font:** Atkinson Hyperlegible Next (variable, self-hosted)

**Character:** Wide geometric capitals for naming, and a face built for legibility under stress for reading.

### Hierarchy
- **Display** (600, 2.125rem to 3.5rem fluid, line-height 1, uppercase): surface titles in the title block.
- **Question** (Montserrat 500, 1.4375rem): the one question a surface answers, under its title.
- **Headline** (600, 1.4375rem, 1.2): section titles inside content sheets.
- **Body** (400, 1rem, 1.55, max 64ch): everything a parent reads.
- **Label** (600, 0.6875rem, 0.22em tracking, uppercase): navigation, the wordmark, legends, the record status title and buttons.
- **Reference** (system monospace, 0.6875rem, olive faint): record ids and reason codes only, always beside their words.

### Named Rules
**The No Kicker Rule.** A title stands alone. Nothing small and tracked sits above it.

## Layout

The grid is fixed to the viewport and aligned to the page gutter (1rem, 2rem from 45rem, 4rem from 64rem) and to the bottom of the top bar. The landing plate is three columns from 64rem: the lead in the left margin behind a 1px ink rule, the name SERENE (under a tracked kicker) centred over the bloom, the tagline in the right margin, and the Enter Serene button bottom-centre; on the landing page the top bar is held empty. Surfaces are at most 78rem wide (48rem for reading pages such as sign-in, 96rem for the Causal Twin map). Each opens on its title block (from 56rem the record legend sits to the right of the title), then its work: Today and Investigations put a narrower rail beside the main column, Experiments puts the decision beside the facts, the Causal Twin puts the explanation beside the map. Below those widths every surface stacks with what leads first (the next action, the decision). The tagline closes every surface as a colophon. The top bar, frosted over the sheet with a hairline under it, shows inline links from 60rem; below that a menu sheet lists each surface with its icon and the question it answers.

## Elevation & Depth

Mostly flat paper. Depth comes from three materials: the lifted sheet (a tonal step, a 1px rule and a soft radius); one olive-tinted lift with a real offset (`--lift`, `--lift-strong`) for what leads a surface or waits for the parent; and the bloom's liquid glass, which the top bar borrows as a light frost over the ruled sheet. No other shadows.

## Shapes

Hairlines everywhere (1px). Soft geometry: petals, not boxes. Tiles and reasons 6px, panels 10px, sheets 16px, pills for buttons, chips and status. Pill buttons with 1px ink outlines; the one leading action is filled.

## Components

- **Button:** a transparent pill with a 1px ink border and label type. It fills with ink on hover, on devices that can hover.
- **Navigation link:** label type in olive muted. Hover draws a dotted line underneath (a possibility); the current surface gets a solid 2px line that settles in from the left.
- **Menu sheet:** a full-height panel of plain warm paper. Each surface is listed in large tracked capitals with its summary underneath, separated by rules; the current one is marked with a short solid line.
- **Landing (Landing):** the page at `/`: bloom, kicker and name, lead, tagline and the Enter Serene button.
- **Hellebore:** five copies of one photographic petal (`public/brand/bloom/petal.webp`), each pivoting at its base, around a cluster of stamens. Sized by `--petal-w`, `--petal-h` and `--centre`.
- **Bloom (BloomArt):** a square scene in percentages and container units: three grained stems, a back and a main hellebore, the bud (`bud.webp`), and two glass panes. Decorative and hidden from assistive technology.
- **Causal Twin map:** a raised sheet dotted like the page, with a hairline toolbar (zoom in, zoom out, fit to view) above it rather than over it. Variables are square paper tiles in ink; links are drawn in the certainty notation with an arrowhead, and each carries a paper label naming its kind in tracked capitals over its statement (narrow screens show the kind only). Refuted links stay on the map, struck through with cross-ticks and their words struck; replaced links are drawn hollow. The selected link fills its label with ink and lays a selection-tint halo under its line. Layout is deterministic: causes before effects, left to right or top to bottom, whichever shows the whole map larger, and no label covers another label or a variable.
- **Logo (BloomMark):** the hellebore seen from above, alone, with a hairline of shade so pale petals hold their edge on paper. The favicon and icons are exported from it (`npm run brand:export`); only the iOS home-screen icon lies on warm paper.
- **Title block (Page):** name, question, lead and the record legend (`RecordControl`), closed by a rule with survey ticks at each end.
- **Stage track (StageTrack):** where something is in its life, in the certainty notation: passed solid, current ringed with a sage halo, ahead dotted, stopped struck. Investigations, experiments and Dream runs use it. It moves only when the projection does.
- **Evidence ladder (LevelLadder):** six rungs from raw evidence to contextual learning, the recorded level filled. Never a score.
- **Safety badge (SafetyBadge):** class name, mark and word, as above.
- **Sync pill (ProjectionStatus):** a ring beside words: solid while live, dashed while reconnecting, dotted before connecting, struck on error.
- **Empty state:** a closed bud on a dotted stem (not yet known), or a barred ring for a stopped state, with words and a way out.
- **Investigation workspace:** incident and stage track across the top; the next action (deep olive) and what Serene doesn't know in a rail; explanations side by side with what each predicts for the open question; evidence missing, then evidence checked.
- **Experiment card:** safety badge and stage, the change, the lifecycle (proposed, safety review, your approval, running, outcome, promotion decision), four key facts, then the record beside the decision panel. A decision is two steps and shows only the kernel's answer.
- **Memory:** each memory a specimen with its label (kind, status, ladder, scope chips, dates) above its provenance (why it is kept, sources, evidence against, a trail drawn as a stem down to raw evidence). Dream runs read as a pipeline ending in kept, refused and awaiting review.
- **Causal Twin:** map and explanation side by side from 64rem (the explanation sticky and scrollable, with a jump bar); the legend doubles as filters; selecting a link draws its two ends in ink and lets everything else recede.

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
- **Don't** add shadows beyond the two lifts, or cards inside cards.
- **Don't** imply a state before the record holds it: no optimistic stages, no scores, no confidence percentages.
