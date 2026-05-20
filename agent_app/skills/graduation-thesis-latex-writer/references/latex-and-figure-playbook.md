# LaTeX and Figure Playbook

## Core principle

This skill is thesis-first. Figure handling is secondary.

Default figure modes:

- `LaTeX-native`
- `placeholder`
- `external-source with citation`

Do not treat stylized academic image generation as the default behavior of this skill.

## Source-material intake rule

Before doing any external-source figure work, first check whether the user already has source materials.

Do not ask about source materials during pure outline, page-planning, TOC-only, or body-only drafting tasks that do not currently involve external figures or tables.

Supported intake types:

- webpage URL
- open PDF URL
- local PDF
- local DOCX
- local image

If the user has no source materials, skip this intake step and continue with the normal figure decision.

If the user does provide source materials, normalize them first and only then decide which asset should be inserted into the thesis.

Legacy `.doc` files are not a stable first-class path here. Ask the user to convert them to `.docx` or PDF first.

## When to use `LaTeX-native`

Prefer `LaTeX-native` when the figure is deterministic, technical, and likely to be edited later, such as:

- flowcharts
- structure diagrams
- architecture block diagrams
- timing diagrams
- state diagrams
- relation diagrams
- parameter trend plots based on real data

Typical tools:

- `TikZ`
- `pgfplots`
- `circuitikz`
- `tikz-cd`

Use LaTeX-native output especially when:

- the figure has many labels
- the text must stay exact
- the user says they will edit the text later
- the figure should go directly into the thesis source

## When to use `placeholder`

Prefer placeholders for:

- equipment photos
- experiment photos
- screenshots of real systems
- third-party UI pages
- any image the author must capture or verify personally

A good placeholder should include:

- a meaningful caption
- a unique `label`
- a clear note about what the final image should contain
- one context-specific sentence or short paragraph that explains why this image is needed here

## When to use `external-source with citation`

Use this route only when the source is:

- real
- stable
- citable

Prefer:

- papers
- theses
- standards
- official documentation
- official institutional pages

If an external figure is inserted or redrawn from a source, cite that source properly and keep it inside the same bibliography system as the rest of the thesis.

Never invent a figure source, URL, paper, or citation. If no real citable source is available, fall back to a placeholder or ask the user to provide the source.

## Webpage image capture workflow

When the user provides a real webpage URL and wants an image inserted into the thesis, keep the task inside `external-source with citation`.

Use the bundled script:

- `scripts/web_figure_capture.py`

The purpose of this script is to:

- fetch a real webpage
- extract candidate image URLs from the page
- rank candidates while demoting likely `logo / icon / social-card / hero / banner / cover` assets
- download one real image asset locally
- save a metadata sidecar containing the page URL, image URL, caption hint, label hint, and LaTeX snippet
- optionally list ranked candidates first without downloading when selection is still needed

If only low-confidence candidates remain after ranking, do not auto-insert a webpage asset silently. List candidates first or ask the user to refine the page, pattern, or explicit candidate choice.

Preferred workflow for non-trivial pages:

- run candidate listing first
- inspect whether the top items are real content images or only logos, banners, and social cards
- add a pattern or choose a candidate explicitly before download when needed

If the ranked webpage candidates are all low-confidence, do not auto-download the default first item. Ask for a more specific page, use candidate listing, or constrain the selection.

Use this route when all of the following are true:

- the user wants a real image from a webpage, not a schematic redrawing
- the page is real and reachable
- the source is appropriate to cite in the thesis

Do not use this route when:

- the user really needs a deterministic technical diagram
- the page source is unstable, unclear, or uncitable
- the user only wants a placeholder

Minimum deliverables after a successful capture:

1. the downloaded local asset path
2. the source page URL
3. the captured image URL
4. the suggested figure caption
5. `integration_mode`
6. one draft integration sentence or short paragraph for local adaptation
7. the suggested LaTeX figure snippet
8. a citation note telling the author to add a real bibliography entry

## Source-material intake workflow

When the user provides source materials and wants an image inserted into the thesis, use the bundled script:

- `scripts/source_figure_intake.py`

This route should normalize several source types into one consistent output package:

- webpage URL
- open PDF URL
- local PDF
- local DOCX
- local image

What the script should do:

- detect the source type
- download the source when the input is an open URL to a PDF or direct image
- delegate webpage capture to the webpage workflow when the input is an HTML page
- extract embedded images from PDF via `pdfimages`
- fall back to rendered PDF page images via `pdftoppm` when no embedded image can be extracted cleanly
- extract embedded images from DOCX via `word/media`
- copy direct image sources into a thesis-ready asset directory
- write a metadata sidecar with source information and a LaTeX snippet
- support candidate listing before final selection when the source contains multiple plausible assets
- support page-limited PDF fallback when the user knows the target page
- support more precise PDF extraction with:
  - `--page`
  - `--crop`
  - `--figure-number`
  - `--caption-pattern`
- avoid silently falling back to whole-document extraction when the user asked for figure-number or caption-guided narrowing and no page match was found
- require either an explicit page or a matched page hint before region-based PDF cropping
- support figure-number or caption-text hints to narrow PDF page candidates before extraction
- support crop-based extraction from a rendered PDF page when the user can identify the target region

Preferred precision order for PDF sources:

1. explicit target page
2. figure-number hint
3. caption keyword or regex hint
4. crop region on a rendered page
5. broad candidate listing only when no narrower hint is available

Minimum deliverables after a successful intake:

1. the selected local asset path
2. the original source input
3. the source type
4. the suggested figure caption
5. `integration_mode`
6. one draft integration sentence or short paragraph for local adaptation
7. the suggested LaTeX figure snippet
8. a citation note telling the author to add the real source entry

## Things not to do

- Do not invent data plots without real data.
- Do not turn real photos into fake schematic drawings just to avoid placeholders.
- Do not insert unverified internet images into the thesis.
- Do not default to complex image-generation routing inside this skill.

## Table handling

Default table modes:

- `native LaTeX table`
- `table skeleton`
- `external data with citation`

Use `native LaTeX table` when the table should be fully authored and maintained in the thesis source.

Use `table skeleton` when the structure is clear but final values, rows, or measurements still need to be filled in by the author.

Use `external data with citation` only when the data comes from a real, citable source.

When providing a table, always provide:

1. the caption
2. the table body
3. one supporting sentence or short paragraph before or after it that is specific to the current section

If the table data comes from an external source, include the source and citation.

Never invent table data, literature comparisons, or citation metadata.

## Anti-template integration rule

Keep the delivery structure stable, but do not standardize the prose around figures and tables into one repeated sentence pattern.

The surrounding explanation must change according to the local function:

- structure introduction
- workflow clarification
- result interpretation
- comparison emphasis
- design justification
- limitation statement

Avoid repetitive sentence shells such as:

- “As shown in the figure, ...”
- “The figure clearly shows that ...”
- “From the table above, it can be seen that ...”

If many figures are used in one chapter, vary both:

- whether the explanation is placed before or after
- whether it focuses on composition, relation, contrast, or implication

## Four integration modes

Before writing the explanation block for a figure or table, select one primary mode.

Do not default to a vague hybrid paragraph.

### 1. `structure-introduction`

Use when the visual mainly introduces composition, hierarchy, modules, or relations.

Best for:

- system architecture figures
- module breakdown figures
- block diagrams
- relation maps

Focus on:

- what parts the figure contains
- how they connect
- what part the reader should anchor on first

### 2. `workflow-bridge`

Use when the visual mainly supports a process or sequence.

Best for:

- method pipelines
- control flows
- test procedures
- data-processing chains

Focus on:

- the entry point
- the key transition steps
- the output or downstream consequence

### 3. `design-justification`

Use when the visual mainly supports why a design or arrangement was chosen.

Best for:

- architecture choice tables
- interface allocation figures
- module partitioning figures
- design tradeoff tables

Focus on:

- what constraint drove the choice
- why this arrangement is defensible
- what local engineering benefit it brings

### 4. `result-interpretation`

Use when the visual mainly supports reading a result, trend, or contrast.

Best for:

- comparison tables
- result plots
- before/after figures
- performance summaries

Focus on:

- what trend or contrast should be read
- what conclusion is justified
- what boundary or limitation still applies

## Default mode mapping

Use this default mapping when the local role is not ambiguous:

- theory or architecture sections -> `structure-introduction`
- platform, method, and test setup sections -> `workflow-bridge`
- design and implementation sections -> `design-justification`
- results and analysis sections -> `result-interpretation`

If the local figure function conflicts with the chapter default, follow the local figure function.

## Cross-reference rules

- Do not hand-type chapter, figure, table, or equation numbers.
- Prefer `\label` and `\ref{}` or the template's equivalent.
- Keep labels unique and stable.
