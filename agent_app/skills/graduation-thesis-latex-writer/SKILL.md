---
name: graduation-thesis-latex-writer
description: "当用户希望在毕业论文或设计报告中使用学校模板，进行稳定、分阶段的写作时，包括大纲规划、页数规划、受控章节起草、保守回退、目录格式化以及受限的图表/表格支持，请使用此技能。最适合处理如“先搭三级标题”、“先定页数”、“只写第一章”、“按已确认目录继续写”、“正文控制在80页”或“只改目录格式”等请求。此技能以论文为先：图表支持可用但受限，必须服务于论点而非主导论点。"
---

# Graduation Thesis LaTeX Writer

## What this skill is for

This skill is a stable thesis-writing skill, not a one-shot thesis generator.

Its primary job is to help with:

- three-level outline planning
- page-count planning
- writing one chapter or one section at a time
- expanding only inside a confirmed directory
- compressing or rolling back an overgrown thesis
- adjusting TOC formatting without rewriting the thesis body
- embedding figures and tables into thesis prose in a controlled way

It is thesis-first. Figures and tables are secondary and must support the argument chain.

By default, this skill supports only these figure behaviors:

- `LaTeX-native`
- `placeholder`
- `external-source with citation`

When the user provides a real webpage URL and wants a citable image inserted into the thesis, treat that as a constrained `external-source with citation` task. Use the bundled script `scripts/web_figure_capture.py` to capture a real image asset, save source metadata, and prepare a LaTeX insertion snippet.

For webpage capture, prefer a two-step flow whenever the page may contain logos, banners, social cards, or multiple plausible images:

- first list ranked candidates
- then let the user confirm the target candidate, or bias selection with a pattern

If only low-confidence webpage candidates remain, do not silently auto-download a logo, icon, or social-card image.

When the current task actually involves external-source figures or tables, confirm whether the user has source materials first. Supported source-material routes are:

- webpage URL
- open PDF URL
- local PDF
- local DOCX
- local image

Legacy `.doc` files are not a stable first-class path here. Ask the user to convert them to `.docx` or PDF first.

Internal rules are written in English for stability. When the thesis itself is Chinese, headings, chapter text, captions, in-text figure/table references, and TOC suggestions should remain Chinese unless the user asks otherwise.

## Non-negotiable rules

### 1. Work in phases

Always decide which phase the user is actually asking for:

- outline only
- page-count planning only
- directory optimization only
- TOC formatting only
- single chapter or subsection writing
- writing inside a confirmed directory
- compression or rollback
- explicit full-draft continuation

If the phase is unclear, stay conservative and do not auto-jump ahead.

### 2. Confirm body page count before writing the thesis body

Before writing thesis body text, confirm:

- body page count or page range
- whether appendices count as body pages
- whether references count as body pages
- whether acknowledgements count as body pages

If this is not clear, stop at:

- outline
- page plan
- chapter responsibility
- structure advice

Do not start body expansion before page count is confirmed.

This hard gate applies to chapter drafting and body expansion. It does not block local proofreading, sentence polishing, or paragraph-level revision of user-provided text.

### 3. Freeze the directory once the user confirms it

Once the user confirms the `chapter / section / subsection` structure, treat it as frozen.

Allowed by default:

- fill in body text inside existing headings
- tighten wording inside existing headings
- remove unnecessary content
- fold useful content back into the original structure

Not allowed by default:

- adding same-level headings on your own
- creating `3.5+ / 4.5+ / 5.5+ / 6.3+` sections
- expanding the conclusion into many extra subsections

### 4. Page count is a constraint, not permission to expand the structure

When the user gives a page target:

- add depth only inside the confirmed directory
- prioritize technical detail, testing detail, and argument quality
- do not add new directory-level sections just to hit the page target

### 5. The latest user correction overrides older assumptions

If the user says things such as:

- "the first directory version was better"
- "the later additions are unnecessary"
- "the body should stay around 80 pages"
- "do not indent the TOC"
- "only change the TOC format"

then those instructions immediately override older structure assumptions, older page goals, and older expansion habits.

### 6. Figures and tables are secondary, not the core of this skill

When a figure or table appears in the workflow, use only one of these figure options:

- `LaTeX-native`
- `placeholder`
- `external-source with citation`

Default figure selection:

- use `LaTeX-native` for deterministic technical diagrams with many labels or later edit needs
- use `placeholder` for real photos, screenshots, equipment images, and anything the author must collect personally
- use `external-source with citation` only when the source is real, stable, and citable

If the user explicitly asks to capture an image from a webpage, only do so from a real page URL and keep the page URL, image URL, local asset path, and citation note together. Do not treat web capture as permission to invent a source.

If the current task really involves external-source figures or tables, first ask whether they want to include:

- PDF files or open PDF links
- DOCX files
- existing images
- webpage links

If the answer is no, skip this intake step and stay with normal writing or webpage capture only.

Do not silently switch this skill into a full academic image-generation router.

Never invent a figure source, URL, paper, or citation. If no real citable source is available, fall back to `placeholder` or ask the user to provide the source.

## Chapter-type function checklists

Before writing any body text, first determine what the current chapter or subsection is supposed to do. Do not write until the function is clear.

### Abstract / 摘要

It should answer:

- what is the research object
- what problem is being addressed
- what was actually done
- what key results were obtained
- what conclusion can be safely claimed

It should not:

- become a mini introduction
- pile up background without results
- exaggerate novelty beyond the real work boundary

### Introduction / 绪论

It should answer:

- why this topic matters
- why the problem is difficult
- what prior work has done
- what remains insufficient
- what this thesis specifically does

It should not:

- duplicate large chunks of theory that belong in later chapters
- expand every related topic just to look complete
- turn into a literature dump without a clear conclusion

### Theory / Background / 原理基础

It should answer:

- what concepts, models, mechanisms, or structures are needed
- which relations are necessary for later analysis or design
- what assumptions or limits apply

It should not:

- repeat introduction-level motivation at length
- introduce unrelated side topics
- explain the same choice repeatedly across chapters

### Platform / Method / Test setup / 平台与方法

It should answer:

- what platform or method was used
- what conditions were controlled
- what parameters were measured or extracted
- what the workflow and data path were

It should not:

- imply the author built everything if they relied on an existing platform
- hide measurement conditions
- overstate operational work as methodological innovation

### Results / Analysis / 结果与分析

It should answer:

- what was measured or simulated
- what the data shows
- how the result should be interpreted
- what boundary, trend, or design implication follows

It should not:

- restate the method instead of analyzing the result
- report numbers without interpretation
- interpret beyond what the data supports

### Design chapter / 电路设计

It should answer:

- what input constraints the design must satisfy
- how the architecture was selected
- how key parameters were determined
- how the design decisions map to the problem boundary

It should not:

- read like a pure implementation log
- repeat generic architecture praise
- detach the design from measured or assumed input conditions

### Conclusion / 总结与展望

It should answer:

- what was actually completed
- what the main findings are
- what limitations remain
- what future work is reasonable

It should not:

- introduce new technical content
- inflate the contribution
- split into too many extra subsections by default

## Hard rule: argument chain comes first

The skill must prioritize the argument chain over local sentence polish.

Always prefer:

- a clear problem chain
- a clear cause-and-effect chain
- a clear result-to-design or result-to-conclusion chain
- one explanation stated once in the right chapter instead of repeated everywhere

When writing or revising, ask:

- what question this section must answer
- what evidence, mechanism, data, or design action supports that answer
- what conclusion this paragraph or section should naturally close with
- whether the current paragraph advances the thesis or only expands it

If the thesis involves both testing and design, strongly prioritize the transmission chain:

- test result
- parameter extraction
- design constraint
- circuit or system decision
- verification result

Do not flatten this into “did testing and also did design.” Preserve the directional relationship whenever it is real and supportable.

## Hard rule: reduce AI-like writing through concrete prohibitions

Do not treat “de-AI” as cosmetic synonym swapping. Enforce the following prohibitions.

### Prohibited patterns

- template-style “supplementary discussion” paragraphs with little new information
- topic-word substitution paragraphs that reuse the same sentence skeleton
- generic claims such as “has important engineering significance” without naming the actual coupled factors
- repeated large-paragraph explanations of the same idea across Introduction, Theory, and Design
- abstract praise not tied to data, formulas, constraints, or design actions
- fake fullness created by stacking adjacent sentences with nearly identical meaning
- vague summary sentences that only sound formal but do not add a testable conclusion

### Mandatory cleanup actions

- delete or compress paragraphs with no new information gain
- replace generic statements with explicit coupled items, variables, or constraints
- keep one chapter responsible for one major explanation whenever possible
- let paragraph endings carry the conclusion, instead of repeating transitional phrases mechanically
- keep only background that serves the next chapter’s actual need

### Style preference

Prefer:

- concrete constraints over generic praise
- named variables, mechanisms, and actions over vague abstractions
- one precise concluding sentence over two or three padded summary sentences
- progression over repetition

## Real work boundary check

Before writing any claim about contribution, method, platform, experiment, or design, verify the real work boundary.

Always distinguish among:

- what the student personally designed or simulated
- what was measured using an existing laboratory platform
- what was inherited from senior students, collaborators, or prior work
- what was only analyzed, not newly built
- what was only pre-simulated, not fabricated or fully validated

By default:

- do not imply the author built an existing platform
- do not imply the author proposed a complete new test methodology if they mainly collected and analyzed data on an existing setup
- do not imply full-chip or full-system realization if the work is only single-pixel or front-end level
- do not imply full experimental verification if only pre-simulation was completed
- do not inflate repetitive engineering work into strong originality claims

When in doubt, use safer wording such as:

- relied on an existing laboratory platform
- carried out parameter measurement and analysis
- completed front-end design and pre-simulation
- provided reference, basis, or preliminary verification

Do not use stronger wording unless the evidence clearly supports it.

## Figure and table delivery rules

Figures and tables must serve the thesis prose, not sit outside it as vague suggestions.

### Required integration style

When a figure or table is needed:

- embed the figure title or table title directly into the body text
- include exactly one explanation block, either before or after the figure/table
- choose whichever placement is more natural in context
- do not explain the same figure or table both before and after

The structure may be fixed, but the explanation sentence or paragraph must not be templated.

Do not reuse near-identical explanation patterns such as:

- “As shown in the figure, ...”
- “It can be seen from the figure that ...”
- “The figure intuitively shows that ...”
- “From the table above, we can conclude that ...”

Instead, make the explanation block depend on what the figure or table is doing in that section:

- introduce a structure
- clarify a workflow
- highlight a comparison
- justify a design choice
- summarize a result trend
- point out a boundary or limitation

The explanation should read like part of the argument chain, not like a generic caption expansion.

### Figure-text integration modes

Before writing the explanation block for a figure or table, choose one primary mode.

Do not mix several modes loosely in one short paragraph unless the user explicitly asks for a longer composite explanation.

Use these four modes:

- `structure-introduction`
- `workflow-bridge`
- `design-justification`
- `result-interpretation`

#### Mode 1: `structure-introduction`

Use this mode when the figure mainly introduces:

- module composition
- hierarchy
- signal paths
- system blocks
- physical or logical layout

The explanation should answer:

- what the figure is made of
- how the main parts relate to each other
- which part the reader should notice first

It should not:

- drift into result interpretation
- over-explain implementation details that belong later

#### Mode 2: `workflow-bridge`

Use this mode when the figure mainly supports:

- a method pipeline
- a task sequence
- a test flow
- a data path
- an interaction or control chain

The explanation should answer:

- what enters the workflow
- what key steps happen in sequence
- what leaves the workflow

It should not:

- become a generic structure description
- retell every step if the body already listed them clearly

#### Mode 3: `design-justification`

Use this mode when the figure mainly supports:

- architecture selection
- parameter tradeoffs
- constraint satisfaction
- interface decisions
- module splitting for engineering reasons

The explanation should answer:

- why this arrangement or table structure was chosen
- what constraint or design pressure it responds to
- what benefit the chosen design gives in this context

It should not:

- sound like generic praise for the architecture
- claim optimization effects that have not been verified

#### Mode 4: `result-interpretation`

Use this mode when the figure or table mainly supports:

- trend reading
- comparison
- before/after contrast
- performance analysis
- boundary or limitation statements

The explanation should answer:

- what trend, contrast, or phenomenon the reader should read from it
- what conclusion is supported
- what conclusion is not supported beyond the shown evidence

It should not:

- turn back into a method description
- restate raw numbers without interpretation

#### Default mapping

When the chapter context is clear, prefer this mapping:

- method / platform / test setup chapters -> `workflow-bridge`
- theory / system overview / architecture chapters -> `structure-introduction`
- design / implementation chapters -> `design-justification`
- results / analysis chapters -> `result-interpretation`

If the figure plays a different role from the chapter default, follow the local figure function instead of the chapter label.

### Figure behavior

Use figures when:

- a structure, mechanism, signal path, workflow, timing relation, or test chain is easier to understand visually
- a real photo or screenshot increases credibility in a platform or method chapter
- a technical diagram will likely need later label edits by the author

When suggesting a figure, the deliverable must include:

- a figure title ready to place in the thesis
- one in-text lead-in or follow-up block that is specific to the section context
- a concrete drawing brief at the end of the section:
  - how many blocks or regions the figure should contain
  - what each part should say
  - how arrows or links should connect
  - what should be emphasized visually

The lead-in or follow-up block should vary by function. For example:

- in a method chapter, it may explain the workflow or data path
- in a design chapter, it may explain why the structure supports a constraint
- in a results chapter, it may explain what trend or contrast should be read from the figure

Choose one of the four integration modes above before writing this block.

### Table behavior

Use tables when:

- the user needs structured comparison, parameter lists, workflow items, or literature summaries
- prose would become too dense without tabulation

When suggesting a table, the deliverable must include:

- a table title ready to place in the thesis
- one in-text lead-in or follow-up block that is specific to the section context
- the actual table content or at least the full header and row plan, not a vague suggestion

Do not use one fixed “table explanation” sentence pattern across the thesis. The explanation must depend on whether the table is serving comparison, parameter definition, literature summary, or workflow organization.

Choose one of the same four integration modes before writing the surrounding table explanation.

### Figure routing inside this skill

- `LaTeX-native`: use for architecture diagrams, signal flow, timing logic, mechanism sketches, and other deterministic technical graphics
- `placeholder`: use for laboratory equipment photos, screenshots, setup photos, real device images, or any author-collected visuals
- `external-source with citation`: use only when a stable, citable figure source actually exists and is appropriate

### Table routing inside this skill

- `native LaTeX table`: use when the table can be authored directly and should be maintained in the thesis source
- `table skeleton`: use when the structure is clear but the user still needs to fill in final values or collect the missing rows
- `external data with citation`: use only when the table data comes from a real, citable source

## Terminology and abbreviation rules

Terminology control must happen during drafting, not only at final cleanup.

### First appearance rules

- the first appearance in the main body counts as the first appearance
- if a term with a standard abbreviation first appears in body text, introduce it in full there
- do not assume that earlier appearance in notes, prompts, or hidden planning already defines it
- once a term has been formally introduced in the body, do not redefine it again later without reason

### Expansion rules

Expand only when all of the following are true:

- the term has a conventional abbreviation or acronym
- the abbreviation will likely reappear later
- the full expansion improves clarity

Do not force English expansions for every technical noun. If there is no meaningful recurring abbreviation, keep the expression natural and concise.

### Consistency rules

Always check:

- whether the Chinese name and abbreviation match the same object throughout
- whether a term has been introduced already in the current body text
- whether units, symbols, and naming remain stable across chapters
- whether the same concept is being referred to by multiple inconsistent labels

## Default output contract

Unless the user explicitly asks for a different format, use the following default structure for subsection-level or chapter-level revision tasks.

### For revision tasks

Output in this order:

1. `Structure judgment`
   - what function this section should serve
   - whether the current structure is basically valid

2. `Paragraph-by-paragraph comments`
   For each paragraph, include:
   - strengths
   - problems
   - revision direction

3. `Polished replacement version`
   - provide a version that can be directly inserted into the thesis

4. `Figure or table integration`
   - if needed, embed the figure/table title directly into the replacement text
   - include exactly one explanation block before or after the figure/table

5. `Figure drawing brief or table content`
   - if a figure is suggested, specify how the author should draw it
   - if a table is suggested, provide the table header and content plan, or the full table when appropriate

6. `Why this revision works`
   - briefly explain the writing logic behind the revision

If the user asks only for a direct rewrite, polished replacement, or smoother wording, output the polished replacement first and keep diagnosis brief unless the user explicitly asks for detailed comments.

### For outline tasks

Output only:

- the full three-level outline
- the responsibility of each chapter and section
- any necessary warnings about scope, overlap, or page pressure

### For page-planning tasks

Output only:

- page allocation
- heavy chapters
- light chapters
- which sections must stay short
- what counts toward body pages if known

### For TOC-formatting tasks

Output only:

- the TOC formatting adjustment
- indentation or style rules
- no body rewriting

## Phased workflow

### Step 1. Read the constraints first

Confirm:

- school template or current LaTeX template path
- thesis title and thesis type
- task book, draft, or chapter samples
- existing directory
- page target
- whether the current task actually needs external source materials for figures or tables
- whether the current task is writing, compressing, TOC formatting, or figure/table handling

If the user provides a TOC screenshot or formatting example, extract:

- directory depth
- indentation rules
- TOC centering rules
- chapter responsibility patterns

If the current task involves external-source figures or tables and the user provides source materials, classify them first:

- webpage URL
- open PDF URL
- local PDF
- local DOCX
- local image

If the current task does not involve external-source figures or tables, skip source intake and continue normally.

### Step 2. Detect the phase

This skill should never assume that every request means “continue writing the whole thesis.”

If the user says:

- `先搭三级标题`
  only build the outline
- `先按学校规范安排页数`
  only do the page plan
- `写第一章`
  write only Chapter 1, and only after page count is confirmed
- `正文控制在 80 页，按第一版目录改`
  compress and merge back into the original structure
- `只改目录格式，不要缩进`
  treat it as a TOC task only

Only allow explicit full-draft continuation when both conditions are already satisfied:

- the body page count is confirmed
- the chapter / section / subsection directory is confirmed

Otherwise, downgrade to outline planning, page planning, or the requested chapter only.

### Step 3. Determine chapter function before prose

Before drafting any subsection, identify:

- what chapter type it is
- what that chapter type must accomplish
- what belongs here
- what should be postponed to later chapters

Use the chapter-type function checklists above. If the current draft exceeds the chapter’s function, compress before expanding.

### Step 4. Build the three-level outline

When the task is outline planning:

- build to `chapter / section / subsection`
- define the responsibility of each chapter and section
- solve structure before prose

Read `references/outline-and-writing-sequence.md` for chapter sequencing and chapter roles.

### Step 5. Lock page count and structure boundaries

Before body writing:

- confirm the body page target
- identify the heavy chapters
- confirm whether the conclusion should stay short
- confirm what counts toward body pages
- confirm whether the directory is frozen after approval

Read `references/scope-and-guardrails.md` for page-count control, rollback order, and TOC-only tasks.

### Step 6. Check the argument chain before line editing

Before polishing sentences, inspect:

- whether the section has a clear question
- whether each paragraph has a distinct role
- whether the conclusion of one paragraph leads naturally to the next
- whether testing, theory, design, and verification are linked in a defensible order
- whether any explanation is being repeated across chapters

Only after the argument chain is sound should sentence-level polishing begin.

### Step 7. Check the real work boundary

Before making claims about novelty, method, platform, or results, verify:

- who built the platform
- who produced the device under test
- whether the task is measurement, analysis, design, simulation, fabrication, or system integration
- what level of verification was actually completed

If the boundary is narrow, write within that boundary.

### Step 8. Write only the requested range

Write only the chapter or section the user actually asked for.

When writing a chapter, keep answering:

- what question this chapter should answer
- how it connects to the previous and next chapter
- what is real technical content
- what is only background and should stay short
- what conclusion the reader should carry forward

Do not auto-continue into the next chapter unless the user explicitly asks for that.

### Step 9. Handle figures and tables conservatively

If the thesis needs figures or tables:

- choose only one route when a figure is needed
- choose only one route when a table is needed
- embed figure/table titles directly in the text
- include exactly one explanation block before or after
- provide a usable drawing brief or table content at the end when appropriate

If the task is “capture an image from a webpage and insert it into the thesis,” keep it inside `external-source with citation`. Prefer the bundled script `scripts/web_figure_capture.py` so the output includes the downloaded asset, metadata sidecar, and a paste-ready LaTeX snippet.

When webpage capture stays low-confidence after ranking, do not auto-pick a likely logo, icon, banner, cover, or social-card asset. Switch to candidate listing first, ask for a more specific page, or add a pattern constraint.

If the task is “pick an image from provided source materials and insert it into the thesis,” prefer the bundled script `scripts/source_figure_intake.py`. Use it to normalize webpage links, open PDF links, local PDFs, local DOCX files, and local images into one consistent output package.

For PDF sources, prefer the most precise narrowing information available:

- explicit page number
- figure-number hint
- caption keyword or regex hint
- crop region on the rendered target page

Do not keep scanning broad PDF ranges when the user already gave a specific page, figure-number clue, or crop region.

For script-backed external-source figure work, the output package should also include:

- `integration_mode`
- `integration_note_zh`

Treat this note as a draft for local adaptation, not as a final paragraph to paste unchanged everywhere.

Read `references/latex-and-figure-playbook.md` for the detailed figure and table policy.

### Step 10. Manage citations and cross-references

Always check:

- whether cited sources are real and verifiable
- whether the bibliography contains only cited items
- whether figure and table sources are properly documented
- whether `\\label` and `\\ref` usage is stable and unique

### Step 11. Run anti-template cleanup

Do not merely swap synonyms. Instead:

- delete empty “formal-sounding” padding
- remove repeated explanation blocks
- replace generic claims with explicit variables, mechanisms, or constraints
- keep real reasoning
- compress repetition
- let the sentence itself carry the conclusion

Read `references/style-derived-rules.md` for prose control.

### Step 12. Run a final thesis check

When the deliverable is a full chapter or more:

- check structure and continuity
- check terminology and abbreviation control
- check figure/table/equation references
- check bibliography closure
- remove `TODO`, demo text, and stale placeholders
- remove claims that exceed the real work boundary
- remove paragraphs that do not improve the argument chain

Read `references/final-quality-checklist.md` for final cleanup.

## When to load which reference

- `references/outline-and-writing-sequence.md`
  Use for chapter skeletons, chapter ordering, and chapter responsibilities.

- `references/scope-and-guardrails.md`
  Use for page-count control, directory compression, rollback, and TOC-only tasks.

- `references/style-derived-rules.md`
  Use for anti-template cleanup, boundary honesty, and de-AI writing control.

- `references/latex-and-figure-playbook.md`
  Use for LaTeX-native figures, placeholders, external figure sourcing, and embedded figure/table delivery.

- `references/final-quality-checklist.md`
  Use for full-thesis cleanup and final consistency checks.

- `references/regression-test-prompts.md`
  Use only for maintainer-side regression checks after changing the skill. Do not load it during normal thesis drafting unless the task is specifically to validate skill behavior.

## Example trigger phrases

- `先搭三级标题骨架，不要展开正文`
- `先按学校规范安排页数，等我确认后再写`
- `只写第一章`
- `按已确认目录继续写第二章`
- `正文控制在 80 页，按第一版目录改`
- `只改目录格式，不要缩进`
- `帮我画系统结构图，后面我要自己改字`
- `这里先留设备照片占位`
- `这张图来自论文，要帮我放进正文并处理引用`
- `先做结构判断，再逐段点评，然后给我可直接替换稿`
- `注意不要超出我的真实工作边界`
- `图前图后只保留一次说明`
- `正文第一次出现才算首次定义`
