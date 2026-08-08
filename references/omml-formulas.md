# 实验报告 OMML 公式插入参考

仅在报告需要**原生 Word 数学公式**时读取本文件：复杂度公式、算法推导、数值计算类实验等场景。本文件中的公式片段都是演示结构，实际报告必须使用与真实代码、真实复杂度一致的内容，禁止为了让报告“好看”改写复杂度或推导过程。

## 适用范围

- 复杂度分析：`T(n) = O(n log n)`、`O(V+E)`、最坏/平均/最好情况公式；
- 算法推导：递推式、求和式、矩阵运算、概率统计表达式；
- 数值计算类实验：数值分析、图像处理、信号处理、机器学习基础中的公式；
- 结果分析中需要精确排版的数学表达式。

不需要公式时不要读取本文件；纯文本 `O(nlogn)` 已经足够表达时，不要为了“好看”强行插入公式。

## 为什么用 OMML

- OMML（Office Math Markup Language）是 Word 原生的公式格式，可编辑、可搜索、可复制，转 PDF 不失真；
- 与“公式截图”“OLE 对象”“图片公式”相比：不引入额外媒体文件、不依赖外部对象，且符合本 Skill“不新增媒体”的最小编辑原则；
- Pandoc 生成新文档时，Markdown 里的 `$...$` 数学会自动转换为 OMML，无需手工拼 XML。

## 两条插入路径

### A. 新文档（Pandoc 可用时）

在 Markdown 中直接写 TeX 数学，Pandoc 转 DOCX 时自动生成原生 OMML：

```powershell
pandoc report.md -o report.docx
```

```markdown
$T(n) = O(n \log n)$

$$
\sum_{i=1}^{n} a_i = \frac{n(n+1)}{2}
$$
```

复杂度符号必须与报告正文和真实实现一致，不能只为了排版整齐改写。

### B. 已有 DOCX 或没有 Pandoc（lxml 手工插入）

使用与 workbench 中 `edit_report.py` 相同的最小 OOXML 编辑方式：**只改 `word/document.xml`，不动任何受保护部件**（styles.xml / fontTable.xml / settings.xml / numbering.xml / theme / 页眉页脚 / 节属性）。

## 常用公式片段（OMML）

所有片段都放在 `<m:oMath>…</m:oMath>` 内；独立成行的显示公式用 `<m:oMathPara><m:oMath>…</m:oMath></m:oMathPara>` 包裹（作为 body 的直接子元素，且必须位于 `<w:sectPr>` 之前）。

注意：数学 run 的文本节点是 **`<m:t>`**（不是 `<w:t>`）；`<w:t>` 只用于普通段落 run。

| 用途 | OMML 片段（置于 `<m:oMath>` 内） |
|---|---|
| 简单文本式公式 `T(n)=O(n log n)` | `<m:r><m:t>T(n)=O(n log n)</m:t></m:r>`（Word 按数学字体渲染整个 run） |
| 上标 `n²` | `<m:sSup><m:e><m:r><m:t>n</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>` |
| 下标 `log₂ n` | `<m:sSub><m:e><m:r><m:t>log</m:t></m:r></m:e><m:sub><m:r><m:t>2</m:t></m:r></m:sub></m:sSub><m:r><m:t>n</m:t></m:r>` |
| 同时上下标 `xᵢᵏ` | `<m:sSubSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub><m:sup><m:r><m:t>k</m:t></m:r></m:sup></m:sSubSup>` |
| 分数 `a/b` | `<m:f><m:num><m:r><m:t>a</m:t></m:r></m:num><m:den><m:r><m:t>b</m:t></m:r></m:den></m:f>` |
| 平方根 `√n` | `<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e><m:r><m:t>n</m:t></m:r></m:e></m:rad>` |
| n 次根 `³√x` | `<m:rad><m:deg><m:r><m:t>3</m:t></m:r></m:deg><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>` |
| 求和 `Σᵢ₌₁ⁿ aᵢ` | `<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr><m:sub><m:r><m:t>i=1</m:t></m:r></m:sub><m:sup><m:r><m:t>n</m:t></m:r></m:sup><m:e><m:sSub><m:e><m:r><m:t>a</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:e></m:nary>` |
| 括号 `(…)` | `<m:d><m:e>…</m:e></m:d>`（默认圆括号；需要方括号/花括号时加 `<m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr>`） |
| 2×2 矩阵 | `<m:m><m:mPr><m:mcs><m:mc><m:mcPr><m:count m:val="2"/><m:mcJc m:val="center"/></m:mcPr></m:mc></m:mcs></m:mPr><m:mr><m:e><m:r><m:t>a</m:t></m:r></m:e><m:e><m:r><m:t>b</m:t></m:r></m:e></m:mr><m:mr><m:e><m:r><m:t>c</m:t></m:r></m:e><m:e><m:r><m:t>d</m:t></m:r></m:e></m:mr></m:m>` |

嵌套示例——分数里有上标（`a²/b`）：

```xml
<m:f>
  <m:num>
    <m:sSup>
      <m:e><m:r><m:t>a</m:t></m:r></m:e>
      <m:sup><m:r><m:t>2</m:t></m:r></m:sup>
    </m:sSup>
  </m:num>
  <m:den><m:r><m:t>b</m:t></m:r></m:den>
</m:f>
```

## 插入代码（与最小 OOXML 编辑一致）

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向既有 DOCX 插入原生 OMML 公式：只改 word/document.xml。"""
import zipfile
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

def wq(tag):
    return "{%s}%s" % (W, tag)

def omath(inner_xml):
    """把 <m:oMath> 内部片段包装成带 m 命名空间的元素（片段自带 xmlns:m 声明，
    无需修改 w:document 根元素）。"""
    return etree.fromstring(
        '<m:oMath xmlns:m="%s">%s</m:oMath>' % (M, inner_xml))

def omath_para(inner_xml):
    """独立成行的显示公式；返回的元素需插在 body 的 <w:sectPr> 之前。"""
    return etree.fromstring(
        '<m:oMathPara xmlns:m="%s"><m:oMath>%s</m:oMath></m:oMathPara>'
        % (M, inner_xml))

def append_inline_math(body, anchor_text, inner_xml, changes):
    """在包含 anchor_text 的段落末尾追加内联公式。保留段落与既有 run。"""
    for p in body.iter(wq("p")):
        text = "".join(t.text or "" for t in p.iter(wq("t")))
        if anchor_text in text:
            p.append(omath(inner_xml))
            changes.append({"kind": "oMath", "anchor": anchor_text})
            return p
    raise RuntimeError("anchor not found: %r" % anchor_text)

def append_display_math(body, inner_xml, changes):
    """在 body 末尾（sectPr 之前）追加独立成行的显示公式。"""
    para = omath_para(inner_xml)
    sect = body.find(wq("sectPr"))
    if sect is not None:
        sect.addprevious(para)
    else:
        body.append(para)
    changes.append({"kind": "oMathPara"})
    return para


def main(src, dst, changes):
    with zipfile.ZipFile(src, "r") as zin:
        infos = zin.infolist()
        parts = {i.filename: zin.read(i) for i in infos}
    root = etree.fromstring(parts["word/document.xml"])
    body = root.find(wq("body"))

    # 示例：在包含“时间复杂度”的段落后插入 O(n log n) 公式
    append_inline_math(
        body,
        "时间复杂度",
        '<m:r><m:t>O(n log n)</m:t></m:r>',
        changes,
    )
    append_display_math(
        body,
        '<m:r><m:t>T(n)=O(n log n)</m:t></m:r>',
        changes,
    )

    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in infos:
            zout.writestr(info, parts[info.filename])
    print("edits applied: %d" % len(changes))


if __name__ == "__main__":
    import sys
    changes = []
    main(sys.argv[1], sys.argv[2], changes)
    for c in changes:
        print("  -", c)
```

## 与 docx_format_guard.py 的兼容规则

插入公式也必须遵守格式不可变契约，否则 `verify` 会失败并阻止交付：

- 编辑前必须 `snapshot` 建立基线，编辑后必须 `verify`（`--original` + `--manifest`）；任何非零退出码都不得交付。
- **只改 `word/document.xml`**。不得触碰 styles.xml、fontTable.xml、settings.xml、numbering.xml、theme、页眉页脚、节属性。
- 保留既有段落与 run：公式插入是**新增节点**，不是替换/删除。删除或改写既有 `<w:pPr>`、`<w:rPr>` 会让格式序列校验失败。
- 新公式 run（`<m:r>`）**不要携带 `<w:rPr>`**，让 Word 使用默认数学字体；如果必须带格式，克隆最近本地 run 的 rPr 作为 donor，否则 `format_sequences` 会把新增指纹判为“无本地格式来源”。
- 新增 `format_sequences` 类别（`paragraph_properties` 等）不允许凭空出现：插入 `<m:oMath>` 本身不新增 `w:pPr`/`w:rPr` 类别，所以是安全的；但若在公式外再新建普通段落，必须克隆 donor 的 pPr。
- 输出文件必须另存为新路径，原模板保持不变。

## 验证清单

交付前确认：

- 公式的每个符号是否在正文中先定义（如 `n` 为顶点数、`V`/`E` 为顶点/边数）；
- 复杂度公式与真实实现、汇总表数值一致，未为排版改写；
- `docx_format_guard.py verify` 退出码 0、manifest `status=ok`、受保护部件零改动；
- 公式片段用 lxml 解析无语法错误，且 `<m:oMath>` 位于 `<w:p>` 内、`<m:oMathPara>` 位于 `<w:sectPr>` 之前；
- 输出 DOCX 可被文档工具重新打开（结构校验通过）；
- 若环境支持，用 Word/WPS/LibreOffice 渲染确认公式可见、上下标/分数/根式排版正确；无法渲染时如实说明未做视觉校验。

## 诚实性规则

- 公式必须对应真实算法与真实复杂度：报告的复杂度、推导和符号必须与代码、运行结果一致，禁止为了“看起来专业”改公式。
- 不能把截图公式、伪公式文本（如 `O(nlogn)` 冒充排版公式）当作原生公式交付。
- 若用户没有提供数学推导，不编造推导步骤；保留占位符或明确标注未验证。