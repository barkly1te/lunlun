---
name: paper-aesthetic-critic
description: Judge the taste, publishability, and venue fit of academic paper ideas, abstracts, outlines, figures, experiments, and revisions. Use when the task is about top-journal or top-conference aesthetics, research taste, whether an AI-generated paper plan is genuinely good or merely polished, or how to raise a draft toward expert-level scholarly quality.
---

# Paper Aesthetic Critic

## Overview

Provide expert-level paper taste instead of generic encouragement. Decide whether a research idea, title, abstract, section outline, experiment plan, figure story, or full draft feels like top-tier scholarly work, merely competent work, or polished but shallow AI writing.

Top-tier paper aesthetics are not only about elegant wording. Judge problem taste, claim sharpness, evidence discipline, figure logic, venue fit, rhetorical restraint, and whether the work creates the feeling of inevitability rather than hype.

## Workflow

1. Identify the target venue, field, and artifact type.
   If the user does not specify a venue, infer the most plausible venue family and say that the venue is inferred.

2. Judge the artifact across these dimensions:
   - problem choice and stakes
   - contribution sharpness
   - novelty versus inevitability
   - claim-evidence match
   - narrative architecture
   - experiment and figure taste
   - venue fit
   - restraint versus overclaiming

3. Produce a hard verdict using one of these labels:
   - top-tier ready
   - strong but not yet top-tier
   - competent but generic
   - polished but shallow
   - not submission-ready

4. Explain exactly what creates or destroys the sense of quality.
   Prefer decisive language. Do not hide behind vague balance if the weakness is obvious.

5. Give revision priorities in descending order of expected impact.
   Focus on the 2-4 changes most likely to improve publication quality.

6. If the user wants rewriting help, rewrite the title, abstract, outline, contribution framing, figure narrative, or experiment story in a way that better matches the target venue.

## Skill Composition

Use this skill as the coordinator when the user asks for paper taste, venue-grade judgment, or whether an AI-generated solution is actually good.

Combine it with other local skills as follows:

- Use `venue-templates` to calibrate venue-specific expectations, formatting norms, and reviewer preferences.
- Use `peer-review` when methodological rigor, statistics, reproducibility, or reviewer-style critique is central.
- Use `scientific-critical-thinking` when the main question is whether the evidence really supports the claims.
- Use `paper_review` when polishing local wording, paragraph flow, figure-text consistency, or Chinese-facing explanation.
- Use `literature-review` or `citation-management` when novelty and positioning need external support.
- Use `pdf` or `pdf_analysis` when layout, figure presentation, and final rendering quality matter.
- Use `scholar-evaluation` when the user wants a quantitative rubric in addition to a taste judgment.

## Output Contract

Always structure the answer in this order unless the user asks for a different format:

1. `Verdict`: one clear label from the workflow.
2. `Why It Feels Strong or Weak`: the core aesthetic judgment.
3. `Top Issues`: the most damaging weaknesses.
4. `What To Keep`: the few elements that already work.
5. `Highest-Leverage Revisions`: prioritized fixes.
6. `Rewrite` or `Alternative Framing`: only when it would materially help.

## Anti-Patterns

Treat the following as strong negative signals unless the user explicitly wants early brainstorming:

- inflated claims without matching evidence
- generic “important problem + strong results” framing with no distinctive taste
- contributions that sound like a shopping list instead of a thesis
- figure plans that summarize rather than argue
- excessive terminology density masking weak ideas
- venue mismatch, such as workshop-level framing dressed as a Nature-style story
- AI-polished prose that sounds smooth but has no conceptual edge

## References

Read these references when deeper calibration is needed:

- For detailed criteria and positive/negative signals, read `references/top-tier-paper-aesthetics.md`.
- For a reusable response template, read `references/output-template.md`.
