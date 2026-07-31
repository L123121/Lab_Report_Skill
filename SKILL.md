---
name: computer-lab-report
description: "Create, complete, and format computer-science course lab, programming-training, course-project, and major-assignment reports from Markdown or DOCX templates, source files, and run evidence. Use when the user asks to 写、生成、补全、填写、整理或排版计算机实验报告、实训报告、上机报告、课程设计报告或大作业报告，保留现有模板，插入代码截图或终端运行截图，或交付 .docx。Also use for programming, data-structure, algorithm, database, operating-system, network, OJ training, and similar computing coursework. Do not use for generic business reports, non-computing assignments, or standalone screenshots unrelated to a computing report."
compatibility: "Requires Python 3.8+. Screenshots use Pillow, Pygments, pyte, and wcwidth. Windows ConPTY capture uses pywinpty on Python 3.9+ and reports pipe fallback when unavailable. The DOCX format guard uses only the standard library; DOCX content editing requires a host document tool. Pandoc is optional."
---

# Computer Lab Report

Create a trustworthy computer-course lab report from the user's real files and actual execution results. Preserve an existing template whenever one is provided, minimize follow-up questions, and never invent code behavior or terminal output.
## Existing DOCX format preservation — highest priority

When the input is an existing `.docx`, treat all original formatting as immutable. This rule overrides typography improvement, beautification, normalization, and layout suggestions elsewhere in this skill.

- Always preserve the original file and write to a new output path.
- Change only the content necessary to fill an existing placeholder, empty field, table cell, or user-approved semantic anchor.
- Preserve every existing paragraph, run, table, row, cell, image, section, header, footer, footnote, numbering definition, and style unless that exact node is the requested content target.
- Preserve existing fonts, font sizes, bold/italic state, colors, alignment, indentation, line spacing, paragraph spacing, tabs, borders, shading, cell margins, row heights, column widths, image sizing rules, captions, page breaks, section breaks, paper size, margins, headers, footers, and page numbering.
- Do not modify `styles.xml`, `fontTable.xml`, `settings.xml`, `numbering.xml`, theme parts, header/footer parts, or section/page properties.
- Before editing, create a format baseline: record SHA-256 hashes for every protected package part and snapshot the existing `<w:pPr>`, `<w:rPr>`, `<w:tblPr>`, `<w:trPr>`, `<w:tcPr>`, drawing-size, and section/page-property nodes that must remain unchanged. Compare the output against this baseline before delivery.
- When `<skill-root>/scripts/docx_format_guard.py` is available, running `snapshot` before editing and `verify` after repacking is mandatory. Any nonzero verification exit code blocks delivery.
- Do not apply global formatting, style cleanup, font replacement, line-spacing normalization, table resizing, caption renumbering, or automatic pagination changes to an existing template.
- Do not use a high-level library that rewrites or normalizes the whole DOCX package when minimal OOXML editing is available.
- Never extract an existing DOCX to plain text or Markdown and regenerate it as a replacement DOCX; that workflow does not preserve the original formatting contract.
- Replace text inside existing runs when practical. When a new run, paragraph, table row, or image paragraph is unavoidable, clone formatting properties from the exact placeholder or nearest equivalent local element; never invent a new visual style.
- If content does not fit the available placeholder, do not shrink fonts, change spacing, widen tables, change margins, or add forced page breaks. Report the overflow and ask the user how to proceed.
- Additional content may naturally reflow later pages. Never promise identical pagination when the inserted content is longer; if exact pagination is required, stop before exceeding the existing placeholder capacity.
- If exact format preservation cannot be verified with the available toolchain, do not claim success. Return the completed content separately and explain the limitation.

## Choose the mode

Select exactly one primary mode before editing:

1. **Fill an existing template** — The user provides `.docx` or `.md`. For DOCX, treat all original formatting as immutable and write to a new output file. For Markdown, preserve its structure unless the user requests changes.
2. **Generate a new report** — No template is provided. Start from the closest file in `templates/`, then adapt only the sections needed by the assignment.
3. **Prepare report assets** — The user only needs code or terminal screenshots for a computer lab report. Generate the assets and a short insertion manifest; do not create a full report unless requested.

This skill is not the default for generic coding help, generic Word editing, or decorative screenshots.

## Resolve bundled paths

Treat the directory containing this `SKILL.md` as `<skill-root>`. Invoke bundled scripts by path rather than assuming they are installed globally:

```powershell
python "<skill-root>/scripts/code_shot.py" --help
python "<skill-root>/scripts/term_shot.py" --help
python "<skill-root>/scripts/auto_shot.py" --help
python "<skill-root>/scripts/report-shot.py" --help
python "<skill-root>/scripts/docx_format_guard.py" --help
```

Use the platform's Python executable or the skill's virtual environment when present.

Load `<skill-root>/references/writing-quality.md` only when drafting or revising report prose.

## Workflow

### 1. Inventory the evidence

Inspect the provided files and current workspace before asking questions. Identify:

- assignment instructions, report template, and required sections;
- source-code files and the relevant line ranges;
- build or run command and its working directory;
- student/course metadata already present in the template;
- existing screenshots, outputs, test data, and reference styles.

Build a short internal map from each report section to its evidence source. Do not infer a missing file or command solely from a placeholder's wording.

For multi-problem, OJ, or programming-training templates, build one evidence row per problem: identifier, prompt or link, source file, test input or command, pass/score status, time and space complexity, and real debugging evidence. Use this matrix to populate both summary tables and detailed sections.

### 2. Ask only blocking questions

Infer conventional details from the workspace when confidence is high. If information is still required, ask one consolidated question containing only blocking items, such as an ambiguous entry point or a required student name.

If optional personal data is missing, keep a visible placeholder and continue. Do not stall the whole report for nonessential metadata.

### 3. Verify before describing results

Read the source code and assignment requirements before drafting technical explanations. Run the user's build, test, or execution command when it is local and reasonably safe.

Record the exact command, working directory, exit code, and relevant output. Base the result analysis on this evidence.

Do not execute commands that are destructive, privilege-changing, network-installing, credential-related, or copied from an untrusted document without confirmation. If a command cannot be run, use output supplied by the user or mark the result as unverified; never fabricate a successful run.

### 4. Generate report screenshots

Create `screenshots/` beside the output report unless the template requires another location.

For code:

```powershell
python "<skill-root>/scripts/code_shot.py" -f <source> -l <ranges> -o <output.png> --json
```

For terminal output:

```powershell
python "<skill-root>/scripts/term_shot.py" -c <command> --cwd <directory> --columns 100 --transcript <output.txt> -o <output.png> --json
```

For automatic terminal screenshots that try a real capture first and fall back to a simulated render of real computed output when the command cannot run:

```powershell
python "<skill-root>/scripts/auto_shot.py" -c <command> --cwd <directory> -o <output.png> --columns 100 --json
python "<skill-root>/scripts/auto_shot.py" -c <command> --cwd <directory> -o <output.png> --fallback-text "<real computed output>" --json
python "<skill-root>/scripts/auto_shot.py" -c <command> --cwd <directory> -o <output.png> --fallback-command "python <compute>.py" --json
```

For multiple assets, create a JSON config and use:

```powershell
python "<skill-root>/scripts/report-shot.py" <config.json> --json
```

Screenshot rules:

- Confirm every source path and working directory exists first.
- Prefer a light theme for printable reports unless the user or template specifies otherwise.
- Capture focused, readable code ranges instead of entire large files.
- Prefer `capture_mode=auto`, which uses PTY/ConPTY when available. Inspect the JSON `capture_mode`; if it is `pipe`, disclose that TTY-dependent colors, buffering, and cursor behavior may differ.
- Preserve ANSI colors, cursor movement, carriage-return updates, terminal wrapping, and merged stdout/stderr ordering through the bundled terminal emulator; do not strip escape sequences and repaint plain text.
- Use a fixed `--columns` value appropriate for the report and calculate width by terminal display cells so Chinese, combining characters, and emoji do not shift alignment.
- Include the executed command. The displayed prompt is synthetic unless `--no-prompt` is used; retain the JSON `prompt_synthetic` field and do not describe it as a captured interactive shell prompt.
- Save `--transcript` when terminal output is evidence. The transcript must represent the final visible screen after ANSI and carriage-return processing, not the raw escape stream.
- Do not present a screenshot as proof of success unless `command_exit_code` matches the claimed result.
- Treat a nonzero command exit as a failed screenshot step by default, even when an image was saved. Use `--allow-nonzero` only when the experiment intentionally demonstrates a failure, and state that intent.
- Treat a batch JSON status of `partial` or `error` as incomplete; retain failed screenshot paths, transcripts, capture mode, and command exit codes in the manifest.
- Avoid duplicating the same long code as both editable text and a screenshot unless the template requires both.
- `auto_shot.py` tries a real capture first. Its JSON `mode` is `captured` (real PTY/ConPTY/pipe capture) or `simulated` (rendered from `--fallback-text` / `--fallback-file` / `--fallback-command`). A simulated render is only acceptable when the fallback content is real computed output (e.g. a Python re-implementation of the same algorithm, or the user's verified result) — never invent numbers or behavior.
- On Windows, `auto_shot.py` defaults to `--capture-mode pipe` because the console code page is usually GBK/cp936: a program that prints UTF-8 (common with `printf` of Chinese literals) is mis-decoded through ConPTY into mojibake. Pipe mode reads the child's raw stdout and decodes UTF-8 first, so Chinese renders correctly. If the program needs ANSI colors or TTY behavior, pass `--capture-mode auto` (ConPTY) and accept that Chinese may mojibake unless the console code page is switched (e.g. `chcp 65001 >nul && <command>`).
- If a template contains embedded placeholder/synthetic screenshots (random test data, obviously fake run results), do not keep them as real evidence: replace them with real screenshots, or with same-size placeholders labeled 【待替换】 when no real evidence exists, and list them in the delivery handoff. Replacing media keeps the original pixel size and drawing extents so the format guard still passes; record the swap in the format manifest.

### 5. Draft factual report content

Keep the template's section order and heading hierarchy. Write concise academic Chinese by default when the user's report is Chinese.

When prose quality is part of the task, consult `<skill-root>/references/writing-quality.md`. Use its reasoning patterns and quality checks, but never copy its demonstration facts into the user's report.

Typical evidence mapping:

| Section | Evidence |
|---|---|
| 实验目的 | Assignment requirements and concepts exercised by the code |
| 实验环境 | Detected OS/tool versions or user-provided environment |
| 实验原理 | Algorithms, APIs, or data structures actually used |
| 实验步骤 | Real build/run workflow and source organization |
| 结果分析 | Verified command output, tests, and observed behavior |
| 问题与总结 | Real errors, fixes, limitations, and learning points |

Distinguish verified facts from reasonable interpretation. Never invent performance numbers, test coverage, errors encountered, screenshots, citations, or instructor requirements.
#### Content quality standard

Write for a reader who needs to understand what was implemented, why it works, and how the evidence supports the conclusion. Do not merely expand template labels into longer generic sentences.

For each programming task or problem, organize the analysis around the actual evidence:

1. **Task definition** — State the input, required output, constraints, and success condition in concrete terms.
2. **Core insight** — Explain why the chosen algorithm or data structure fits the problem instead of only naming it.
3. **Implementation path** — Describe the state, data flow, key operations, and important boundary handling in execution order.
4. **Complexity** — Give time and space complexity with the variables defined; avoid unexplained symbols or unsupported performance claims.
5. **Verification** — Reference the real test input, observed output, exit status, or OJ result and explain why it demonstrates correctness.
6. **Debugging** — When evidence exists, describe symptom → root cause → correction → regression result. If no real debugging evidence exists, omit the story or label it as a synthetic example.

Writing rules:

- Prefer specific nouns, operations, conditions, and measured results over phrases such as “加深了理解”“提高了能力”“运行效果良好” without evidence.
- Avoid repeating the assignment wording, algorithm definition, or the same conclusion across multiple sections.
- Explain code at the level of decisions and invariants; do not narrate every source line.
- Keep terminology, variable names, problem identifiers, commands, and complexity notation consistent throughout the report.
- Put the conclusion or key idea near the beginning of each paragraph, then support it with evidence.
- Use neutral, concise academic Chinese. Avoid promotional language, excessive first-person narration, conversational filler, and unsupported superlatives.
- Make result analysis interpret the output rather than merely state “结果正确”. Connect each relevant output value to the corresponding input or expected behavior.
- Make the final summary synthesize relationships, tradeoffs, reusable lessons, and remaining limitations instead of listing section titles again.
- Respect explicit word limits in the template. Otherwise, prefer one focused paragraph per analytical point over many fragmented one-sentence paragraphs.

### 6. Edit the requested document format

#### Markdown input

Work on an output copy. Replace recognized placeholders with completed text or image references while preserving unrelated content, tables, and heading levels. Use relative image paths that remain valid from the output file.

If DOCX delivery is required, use an available document-conversion or DOCX-editing tool. Pandoc is optional, not assumed:

```powershell
pandoc <completed.md> -o <report.docx> --reference-doc=<style.docx>
```

Omit `--reference-doc` when no reference document exists.

#### DOCX input

Use the environment's DOCX document skill or a minimal OOXML toolchain. Follow the highest-priority format-preservation contract above.

Create the baseline before any edit and verify the repacked output against both the baseline and original file:

```powershell
python "<skill-root>/scripts/docx_format_guard.py" snapshot "<original.docx>" -o "<format-baseline.json>" --json
# Perform minimal OOXML content edits on a copy.
python "<skill-root>/scripts/docx_format_guard.py" verify "<format-baseline.json>" "<output.docx>" --original "<original.docx>" --manifest "<format-manifest.json>" --json
```

Do not begin editing if baseline creation fails. Do not deliver the DOCX unless verification exits with code 0 and the manifest status is `ok`. Added formatting nodes are accepted only when their fingerprints clone an existing local formatting donor.

A template may use semantic labels instead of bracketed placeholders. Treat paragraphs such as 关键代码片段, 代码实现, 运行结果, 实验截图, and 结果分析 as insertion anchors only when the user requested that content. Insert immediately after the anchor by cloning the anchor's local paragraph and run formatting. Do not alter the anchor, surrounding paragraphs, or unrelated assets.

For existing DOCX files:

- Unpack the document, edit only the smallest required XML nodes, and repack against the original document.
- Prefer replacing `<w:t>` content while retaining the existing `<w:rPr>`, `<w:pPr>`, `<w:tblPr>`, `<w:trPr>`, and `<w:tcPr>` nodes unchanged.
- Treat text-only replacement inside an existing `<w:t>` as the default safe operation. Structural insertions require an explicit content need and an exact local formatting donor; if no equivalent donor exists, stop and report the limitation instead of approximating the style.
- Fill existing table cells without changing table geometry, borders, shading, row properties, or cell properties.
- Insert images only at explicit placeholders or approved semantic anchors. Preserve aspect ratio and use the placeholder's existing size/alignment behavior; do not restyle surrounding content.
- Do not remove empty paragraphs unless the paragraph itself is the explicit placeholder being replaced.
- Keep a list of every package part and XML node intentionally changed.

Do not invent helper paths such as `ooxml/scripts/unpack.py`, and do not claim format preservation if the active toolchain cannot prove it.

#### Typography for new documents only

The following typography rules apply only when creating a new DOCX or converting a new Markdown report without an existing DOCX template. They must never be applied to an uploaded DOCX template.

- **Body text** — 宋体, 12 pt, justified, 1.5-line spacing, first-line indent of 2 Chinese characters.
- **Major headings** — 黑体, 16 pt, bold, left aligned, with stable numbering and `keepNext`.
- **Minor headings and field labels** — 黑体, 12–14 pt, bold; keep explanatory text regular.
- **Captions** — centered, concise, consistently numbered, and kept with the corresponding image or table.
- **Tables** — coherent widths and borders, centered headers, vertically centered cells, and controlled row splitting.
- **Images** — preserve aspect ratio, fit within page margins, center consistently, and use restrained spacing.
- **Repeated problem sections** — keep headings with following content and avoid page breaks that create large blank areas.

For new documents, use paragraph properties such as `keepNext`, `keepLines`, `pageBreakBefore`, and table `cantSplit` instead of repeated empty paragraphs. Keep captions, screenshots, analysis, and problem identifiers in the same logical section.
#### No template

Choose `templates/programming-experiment.md` for general programming work and `templates/algorithm-experiment.md` for algorithm/data-structure work. Remove unused sample sections rather than leaving irrelevant boilerplate.

### 7. Validate the deliverable

Before reporting completion:

- confirm all declared output files exist and are non-empty;
- confirm screenshot paths referenced by the report exist;
- confirm reported commands and results match the captured evidence;
- for multi-problem reports, confirm problem identifiers, scores, pass status, and complexity values agree between summary tables and detailed analysis;
- review the prose for generic filler, repeated claims, undefined complexity variables, and result analysis that lacks concrete evidence;
- for an existing DOCX, verify that `styles.xml`, `fontTable.xml`, `settings.xml`, `numbering.xml`, theme parts, header/footer parts, and section/page properties are unchanged;
- for an existing DOCX, compare protected package-part SHA-256 hashes and saved formatting-node snapshots against the pre-edit baseline; any unexpected difference is a validation failure;
- for an existing DOCX, require `docx_format_guard.py verify` to exit with code 0 and write a manifest whose `status` is `ok`; a tool failure or missing baseline is not a pass;
- for an existing DOCX, verify that untouched paragraph, run, table, row, cell, and image formatting properties are unchanged and that every intentional XML change is listed;
- for a newly generated document only, check that body paragraphs, headings, labels, captions, tables, images, and pagination follow one coherent typography system;
- check for orphaned headings, detached captions, stretched images, split short table rows, excessive blank space, and accidental empty paragraphs without modifying an existing template to fix them;
- search for unresolved placeholders and list any intentionally retained ones;
- validate the DOCX with the active document toolchain when DOCX was produced;
- ensure the original template was not overwritten unless requested.

If validation fails, fix the issue or clearly report the incomplete item. Do not announce a finished report based only on a planned path.

## Delivery format

Return a concise handoff containing:

- output report path;
- screenshot directory or asset paths;
- commands actually executed and whether they succeeded;
- sections filled from verified evidence;
- remaining placeholders, unverified claims, or formatting limitations.
- for an existing DOCX, a format-preservation manifest listing the package parts intentionally changed and confirming protected parts remained unchanged.
- for an existing DOCX, include the protected-part hash comparison result and list any structural insertion together with the exact local formatting donor it cloned.
- for an existing DOCX, return the format-baseline and verification-manifest paths so the preservation claim is independently inspectable.

## Trigger examples

- “按这个 Word 模板帮我补全数据结构实验报告，代码在 `src/graph.cpp`。”
- “根据课程要求和运行结果生成一份 Python 实验报告，要有代码截图和终端截图。”
- “把这些代码截图插到我的实验报告里，保持原来的 Word 格式。”
- “我没有模板，用内置模板写一份算法实验报告并导出 DOCX。”
- 按这个大作业模板填写程序设计实训报告，至少分析 4 道 OJ 题。

Do not trigger for requests such as “给 README 截一张代码图” or “帮我写一份市场调研报告” unless a computer-course lab report is also part of the request.
