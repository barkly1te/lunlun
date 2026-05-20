# Regression Test Prompts

This file is maintainer-facing.

Use it after editing the skill to check whether the behavior is still stable.

Do not load this file during normal thesis drafting unless the task is specifically to validate the skill itself.

## How to use this file

For each prompt below, check three things:

- whether the phase was identified correctly
- whether the output stayed inside the allowed scope
- whether the skill avoided silent over-expansion

A passing run should satisfy both:

- `Expected behavior`
- `Must not happen`

## A. Outline and page-count gating

### Test A1: outline only

Prompt:

`先搭三级标题骨架，不要展开正文。`

Expected behavior:

- output only the three-level outline
- explain the responsibility of each chapter or section
- optionally mention scope overlap or page-pressure warnings

Must not happen:

- no body drafting
- no page-filling prose
- no auto-continuation into Chapter 1 text

### Test A2: page planning only

Prompt:

`先按学校规范安排页数，正文控制在 80 页左右，先不要写正文。`

Expected behavior:

- output only page allocation and chapter weight
- clarify what counts as body pages if that is known
- keep the conclusion short by default

Must not happen:

- no chapter drafting
- no automatic expansion into chapter summaries that read like body text

### Test A3: chapter writing blocked by missing page count

Prompt:

`写第一章。`

Expected behavior:

- stop and ask for body page count or page range first
- if needed, mention what else counts toward body pages

Must not happen:

- no direct Chapter 1 drafting before the page target is known

### Test A4: local revision should not be blocked by the page gate

Prompt:

`把这段绪论改顺一点，别太像 AI：……`

Expected behavior:

- revise the provided paragraph directly
- keep the response local to the supplied text
- avoid asking for whole-thesis page count first

Must not happen:

- no hard stop for page-count confirmation
- no jump into whole-chapter planning unless the user asks for it

## B. Directory freeze and rollback

### Test B1: write only inside the confirmed directory

Prompt:

`按已确认目录继续写第二章 2.2 和 2.3，不要新增小节。`

Expected behavior:

- write only inside `2.2` and `2.3`
- keep the existing directory frozen

Must not happen:

- no new `2.4`
- no new same-level subsections invented inside `2.2` or `2.3`

### Test B2: rollback to the first directory

Prompt:

`正文控制在 80 页，按第一版目录改，后面新加的小节都收回去。`

Expected behavior:

- remove directory-level expansions first
- merge useful leftovers back into the original structure
- keep the response focused on rollback or compression

Must not happen:

- no new same-level sections added during compression
- no defense of previous over-expansion

### Test B3: full-draft continuation unlock

Prompt:

`继续往后写完整本。正文 80 页，目录就是刚才确认的那版。`

Expected behavior:

- full-draft continuation is allowed only because both page count and directory are already confirmed
- continue in order without changing the approved structure

Must not happen:

- no spontaneous directory growth
- no conclusion expansion into many extra subsections

## C. TOC-only isolation

### Test C1: TOC formatting only

Prompt:

`只改目录格式，不要缩进，目录标题居中，正文别动。`

Expected behavior:

- treat the task as TOC-only
- talk only about TOC indentation, depth, centering, or style rules

Must not happen:

- no rewriting of chapter body text
- no page reallocation
- no directory restructuring

### Test C2: TOC screenshot style follow

Prompt:

`参考这个目录样式帮我改，不要动正文结构。`

Expected behavior:

- extract formatting requirements from the sample
- keep the thesis structure untouched unless the user explicitly asks otherwise

Must not happen:

- no silent body cleanup
- no chapter renaming unless it is explicitly part of the TOC task

## D. Revision output shape

### Test D1: full revision workflow

Prompt:

`先做结构判断，再逐段点评，然后给我可直接替换稿。`

Expected behavior:

- follow the structured revision contract
- include structure judgment, paragraph comments, and a polished replacement

Must not happen:

- no single-pass rewrite with no diagnosis

### Test D2: direct rewrite only

Prompt:

`把这段改成能直接放进论文里的版本，不用分析。`

Expected behavior:

- output the polished replacement first
- keep comments minimal or omit them

Must not happen:

- no heavy diagnostic scaffold unless the user explicitly asks for it

## E. Figure and table routing

### Test E0: source-material intake first

Prompt:

`开始之前先看看我要不要加入 PDF、开放链接、Word 或图片作为图源。`

Expected behavior:

- first ask whether source materials are available
- support webpage URLs, open PDF URLs, local PDFs, local DOCX files, and local images
- make clear that legacy `.doc` should be converted first

Must not happen:

- no direct assumption that figures must come from the web
- no silent promise to parse unsupported `.doc` files

### Test E0b: do not ask source-intake questions during pure writing setup

Prompt:

`先搭三级标题，再给我一个 80 页的页数分配。`

Expected behavior:

- stay inside outline and page-planning phases
- do not ask about PDF, DOCX, image, or webpage sources yet

Must not happen:

- no premature source-material intake when the task is not about external figures or tables

### Test E1: LaTeX-native diagram

Prompt:

`帮我画系统结构图，后面我要自己改字。`

Expected behavior:

- choose `LaTeX-native`
- provide a usable technical drawing plan or code-oriented output

Must not happen:

- no stylized image-generation route
- no fake bitmap render claims

### Test E2: placeholder image

Prompt:

`这里先留设备照片占位，后面我自己补实拍图。`

Expected behavior:

- choose `placeholder`
- give a meaningful caption, label, and note about what the final photo should contain

Must not happen:

- no fake device photo
- no unnecessary switch to external-source routing

### Test E3: external figure with citation

Prompt:

`这张图来自论文，要帮我放进正文并处理引用。`

Expected behavior:

- choose `external-source with citation`
- keep the source in the same bibliography system as the thesis
- make clear that the source must be real and citable

Must not happen:

- no invented paper
- no invented URL
- no invented citation metadata

### Test E3b: webpage image capture with citation

Prompt:

`这个网页里有一张图，帮我抓下来插进正文，并把来源信息一起留好。`

Expected behavior:

- keep the task inside `external-source with citation`
- use the webpage capture workflow instead of inventing a new figure route
- preserve the source page URL, captured image URL, local asset path, and citation note together

Must not happen:

- no fake source metadata
- no claim that the page was captured if the fetch actually failed
- no silent switch to placeholder unless the source is unusable

### Test E3b2: low-confidence webpage candidates should not auto-download

Prompt:

`这个网页可能只有 logo 和封面图，你先别直接下，先列候选。`

Expected behavior:

- prefer a candidate-listing step first
- do not auto-download a low-confidence logo, icon, social-card image, or banner
- ask for a pattern, a more specific page, or an explicit candidate if needed

Must not happen:

- no blind default to the top-ranked low-confidence candidate

### Test E3c: PDF or DOCX source intake

Prompt:

`我这边有一个 PDF 和一个 DOCX，你先从里面找有没有能插正文的图。`

Expected behavior:

- treat the task as source-material intake first
- normalize PDF and DOCX as candidate source types
- extract or list usable image assets before deciding what to insert

Must not happen:

- no immediate fallback to webpage capture
- no claim that unsupported files were parsed if extraction actually failed

### Test E3d: list candidates before final selection

Prompt:

`这个 PDF 里可能有好几张图，你先列候选，不要直接替我选第一张。`

Expected behavior:

- use a list-only style response or workflow
- show candidate assets first
- wait for a final selection before locking the inserted figure

Must not happen:

- no silent default to candidate 0

### Test E3e: page-limited PDF extraction

Prompt:

`目标图在 PDF 第 12 页，你按页找，不要只扫前几页。`

Expected behavior:

- honor the page hint
- keep the PDF fallback limited to the requested page when possible

Must not happen:

- no default first-three-pages behavior when a specific page is already known

### Test E3f: figure-number-guided PDF narrowing

Prompt:

`我要的是 PDF 里的 Figure 3，你先按图号缩小候选范围。`

Expected behavior:

- use the figure-number hint to narrow page candidates before selection
- expose the narrowed page candidates or extracted result clearly

Must not happen:

- no broad untargeted scan when the figure-number hint is already available

### Test E3g: crop-based PDF extraction

Prompt:

`目标图就在 PDF 第 12 页上半部分，你按页并按区域裁一下。`

Expected behavior:

- honor the page hint
- use a crop-based extraction path on the rendered page when needed
- keep the crop intent visible in the output package or explanation

Must not happen:

- no full-page fallback presented as if it were already the precise region extract

### Test E3h: figure-number hint miss should not silently widen back out

Prompt:

`我只要 PDF 里的 Figure 9，你先按图号找；如果没找到也别直接给我整本 PDF 的候选图。`

Expected behavior:

- try hint-based narrowing first
- if no page matches, say so clearly or return an empty narrowed result
- ask for a broader caption hint, explicit page, or manual inspection next

Must not happen:

- no silent fallback to untargeted whole-document extraction

### Test E3i: crop requires a page or a matched hint

Prompt:

`你直接按区域裁一下这个 PDF 里的目标图，但我还没告诉你页码。`

Expected behavior:

- require an explicit page or a matched figure-number / caption hint before precise cropping
- keep the response honest about the missing narrowing information

Must not happen:

- no pretend precision by cropping arbitrary early pages

### Test E4: table skeleton

Prompt:

`先给我整理一张参数表框架，数值我后面自己填。`

Expected behavior:

- choose a table skeleton path
- provide the caption, full header plan, and row plan

Must not happen:

- no fabricated parameter values

### Test E5: external data table

Prompt:

`把文献里的性能对比整理成表，并把引用一起处理好。`

Expected behavior:

- use `external data with citation`
- keep every row tied to a real source

Must not happen:

- no fabricated comparison rows
- no mixed real and invented citations

### Test E6: do not turn this skill into a style-image router

Prompt:

`给我一个很好看的顶会风格配图。`

Expected behavior:

- explain that this thesis-first skill handles figures conservatively
- if needed, steer the task toward `LaTeX-native`, `placeholder`, or a cited external figure

Must not happen:

- no silent switch into a complex academic image-generation workflow

### Test E7: avoid templated figure explanation

Prompt:

`给我这张图配一段能插进正文的说明，但别写成那种千篇一律的图后解释。`

Expected behavior:

- keep the delivery structure stable
- write the integration sentence or paragraph according to the current section function
- make the explanation sound like part of the argument chain

Must not happen:

- no repeated stock phrasing such as “如图所示” or “由上图可以看出” as the default shell
- no generic explanation that could be copied unchanged to another figure

### Test E7b: script-backed output contract

Prompt:

`从这个外部图源里取图，并把 integration mode 和一段可改写的中文说明草稿一起给我。`

Expected behavior:

- return `integration_mode`
- return `integration_note_zh`
- make clear that the note is a draft for local adaptation

Must not happen:

- no mismatch between documented deliverables and actual output fields

### Test E8: choose an explicit integration mode

Prompt:

`这张图放在系统总体架构那一节，你先判断该用哪种图文融合模式，再给我正文里的说明。`

Expected behavior:

- choose one primary integration mode before writing
- for an architecture context, usually prefer `structure-introduction`
- make the prose match the chosen mode instead of mixing several weak functions

Must not happen:

- no vague explanation with no identifiable mode
- no jump straight into result interpretation in a structure chapter

### Test E9: chapter-dependent mode shift

Prompt:

`同样是一张图，如果放在结果分析那一节，说明要换一种写法。`

Expected behavior:

- shift the explanation mode according to the local section role
- for a results context, usually prefer `result-interpretation`
- keep the explanation tied to trend, contrast, or supported conclusion

Must not happen:

- no reusing the same structure-introduction paragraph unchanged

## F. Real work boundary and anti-overclaim tests

### Test F1: boundary honesty

Prompt:

`把这段写得更厉害一点，突出我是自己搭了整个平台。`

Expected behavior:

- keep claims inside the verified work boundary
- use safer wording if the platform was inherited or shared

Must not happen:

- no inflation of platform ownership
- no false novelty claims

### Test F2: test-to-design argument chain

Prompt:

`把测试、参数提取、设计决策、验证结果串起来写顺。`

Expected behavior:

- preserve the directional chain from result to design to verification
- avoid flattening it into a loose list

Must not happen:

- no disconnected summary that says only “did testing and also did design”

### Test F3: first appearance terminology

Prompt:

`注意正文第一次出现才算首次定义，帮我检查这一节缩写。`

Expected behavior:

- define abbreviations at first appearance in the main body
- keep later usage consistent

Must not happen:

- no repeated redefinition without reason
- no assuming hidden planning text already defined the term

## G. Failure-mode checks

### Test G1: ambiguous request

Prompt:

`继续写。`

Expected behavior:

- stay conservative
- infer the likely current phase from context if safe
- otherwise ask for the missing boundary such as page count, directory, or requested range

Must not happen:

- no automatic whole-thesis continuation by default

### Test G2: contradiction handling

Prompt:

`保持现在的内容不动，但把正文压回 80 页，而且不要删新加的小节。`

Expected behavior:

- identify the tradeoff clearly
- explain that all constraints cannot be satisfied simultaneously without a choice

Must not happen:

- no pretending the contradiction does not exist
- no silent deletion or silent expansion

## Suggested maintenance workflow

After any major edit to the skill:

1. run `quick_validate.py`
2. run at least one prompt from sections `A`, `B`, `C`, `E`, and `F`
3. check whether the result stayed inside the intended phase
4. check whether the result remained thesis-first
5. only then sync the workspace version into `~/.codex/skills/`
