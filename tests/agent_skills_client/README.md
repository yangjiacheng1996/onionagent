
# --help
```powershell
python agent_skills_client.py  --help
Agent Skills 客户端工具
========================

用法: python agent_skills_client.py <命令> [选项] [参数]

命令:
  validate <path>             验证 Skill 目录
  to-json <path>              读取并打印 Skill 属性为 JSON
  to-xml <paths...>           为 Agent 提示生成 <available_skills> XML
  read-body <path>            读取 SKILL.md 的正文(L2 指令,不含 frontmatter)
  scan <path>                 扫描并列出所有 Skills
  disclosure <name>           展示技能的渐进式披露内容(L1/L2;L3 摘要;--full 输出全文)
  list-resources <skill>      列出某个 Skill 的 references/scripts/assets 资源
  read-ref <skill> <ref>      读取 references/ 中的某个参考文档(按需加载)
  run <skill> <script> ...    执行 scripts/ 中的某个脚本

示例:
  python agent_skills_client.py validate ./my-skill
  python agent_skills_client.py to-json ./my-skill
  python agent_skills_client.py to-xml ./skill1 ./skill2
  python agent_skills_client.py read-body ./my-skill
  python agent_skills_client.py scan ./skills
  python agent_skills_client.py disclosure pdf --root ./skills --level L2
  python agent_skills_client.py disclosure pdf --root ./skills --level L3          # 摘要
  python agent_skills_client.py disclosure pdf --root ./skills --level L3 --full   # 全文 dump
  python agent_skills_client.py list-resources pdf --root ./skills
  python agent_skills_client.py read-ref pdf REFERENCE --root ./skills
  python agent_skills_client.py run pdf extract_text.py input.pdf --root ./skills
```


# validate
```powershell
python agent_skills_client.py validate C:\workspace\github\skills\skills
Validation failed for C:\workspace\github\skills\skills:
  - Missing required file: SKILL.md

python agent_skills_client.py validate C:\workspace\github\skills\skills\pdf\
Valid skill: C:\workspace\github\skills\skills\pdf

```

# to-json  (原 read-properties,旧名仍兼容)
```json
python agent_skills_client.py to-json  C:\workspace\github\skills\skills\pptx
{
  "name": "pptx",
  "description": "Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions \"deck,\" \"slides,\" \"presentation,\" or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill.",
  "license": "Proprietary. LICENSE.txt has complete terms"
}

```

# to-xml  (原 to-prompt,旧名仍兼容)
```xml
python agent_skills_client.py to-xml  C:\workspace\github\skills\skills\pptx
<available_skills>
<skill>
<name>
pptx
</name>
<description>
Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions &quot;deck,&quot; &quot;slides,&quot; &quot;presentation,&quot; or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill.
</description>
<location>
C:\workspace\github\skills\skills\pptx\SKILL.md
</location>
</skill>
</available_skills>

```

# read-body  (L2 指令文本,纯 markdown,不含 frontmatter)
```
python agent_skills_client.py to-xml  C:\workspace\github\skills\skills\pptx
<available_skills>
<skill>
<name>
pptx
</name>
<description>
Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions &quot;deck,&quot; &quot;slides,&quot; &quot;presentation,&quot; or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill.
</description>
<location>
C:\workspace\github\skills\skills\pptx\SKILL.md
</location>
</skill>
</available_skills>

C:\workspace\github\onionagent\tests\agent_skills_client>python agent_skills_client.py read-body C:\workspace\github\skills\skills\pdf
# PDF Processing Guide

## Overview

This guide covers essential PDF processing operations using Python libraries and command-line tools. For advanced features, JavaScript libraries, and detailed examples, see REFERENCE.md. If you need to fill out a PDF form, read FORMS.md and follow its instructions.

## Quick Start
......此处省略下文内容

```

# list-resources  (L3 资源清单,含 references/scripts/assets + 根目录散落的 *.md)
```
python agent_skills_client.py list-resources pdf --root C:\workspace\github\skills\skills>python agent_skills_client.py list-resources pdf --root C:\workspace\github\skills\skills
# pdf - L3 资源清单
# 位置: C:\workspace\github\skills\skills\pdf

## <root>/*.md  (2 项,根目录散落)
  - forms.md    (兼容读取,可用 read-ref 直接读)
  - reference.md    (兼容读取,可用 read-ref 直接读)

## scripts/  (8 项)
  - check_bounding_boxes.py    (executable: True)
  - check_fillable_fields.py    (executable: True)
  - convert_pdf_to_images.py    (executable: True)
  - create_validation_image.py    (executable: True)
  - extract_form_field_info.py    (executable: True)
  - extract_form_structure.py    (executable: True)
  - fill_fillable_fields.py    (executable: True)
  - fill_pdf_form_with_annotations.py    (executable: True)

```

# read-ref  (L3 单个 reference 文档全文,带 fallback)
```
python agent_skills_client.py read-ref pdf forms --root C:\workspace\github\skills\skills 
**CRITICAL: You MUST complete these steps in order. Do not skip ahead to writing code.**

If you need to fill out a PDF form, first check to see if the PDF has fillable form fields. Run this script from this file's directory:
 `python scripts/check_fillable_fields <file.pdf>`, and depending on the result go to either the "Fillable fields" or "Non-fillable fields" and follow those instructions.

# Fillable fields
If the PDF has fillable form fields:
- Run this script from this file's directory: `python scripts/extract_form_field_info.py <input.pdf> <field_info.json>`. It will create a JSON file with a list of fields in this format:

[
  {
    "field_id": (unique ID for the field),
    "page": (page number, 1-based),
    "rect": ([left, bottom, right, top] bounding box in PDF coordinates, y=0 is the bottom of the page),
    "type": ("text", "checkbox", "radio_group", or "choice"),
  },
  // Checkboxes have "checked_value" and "unchecked_value" properties:
  {
    "field_id": (unique ID for the field),
    "page": (page number, 1-based),
    "type": "checkbox",
    "checked_value": (Set the field to this value to check the checkbox),
    "unchecked_value": (Set the field to this value to uncheck the checkbox),
  },
......此处省略下文

```

查找顺序:references/<name>.md → <name>.md(根目录) → 任意扩展名(兜底),支持带/不带 .md 两种调用。

# run  (L3 脚本执行,支持任意参数,带超时)
“--”符号区分外层命令行和内层命令行。
“--”符号之前的参数传递给agent_skills_client.py run命令。
“--”符号之后的参数传递给check_fillable_fields.py，这个脚本来自pdf这个skill。
这个设计方法属于国际标准，这是 git、docker、kubectl 都用的范式。
```
python agent_skills_client.py run pdf check_fillable_fields.py --root C:\workspace\github\skills\skills --timeout 10 -- "C:\Users\Administrator\Downloads\Langchain官方文档.pdf"
This PDF does not have fillable form fields; you will need to visually determine where to enter data
```

退出码语义:
- 0 = 脚本 returncode == 0(成功)
- 1 = CLI 错误(脚本不存在 / 解释器缺失 / 超时)
- 2 = 脚本 returncode != 0(业务失败,业务侧问题)

跨平台执行:Windows 自动按 .py→python / .sh→bash / .js→node / .ps1→pwsh 选解释器;POSIX 尊重 shebang。

# scan
```
python agent_skills_client.py scan  C:\workspace\github\skills\skills\
📁 algorithmic-art
   描述: Creating algorithmic art using p5.js with seeded randomness and interactive para...
   许可证: Complete terms in LICENSE.txt

📁 brand-guidelines
   描述: Applies Anthropic's official brand colors and typography to any sort of artifact...
   许可证: Complete terms in LICENSE.txt

📁 canvas-design
   描述: Create beautiful visual art in .png and .pdf documents using design philosophy. ...
   许可证: Complete terms in LICENSE.txt

📁 claude-api
   描述: Reference for the Claude API / Anthropic SDK — model ids, pricing, params, strea...
   许可证: Complete terms in LICENSE.txt

📁 doc-coauthoring
   描述: Guide users through a structured workflow for co-authoring documentation. Use wh...
   许可证: Complete terms in LICENSE.txt

📁 docx
   描述: Use this skill whenever the user wants to create, read, edit, or manipulate Word...
   许可证: Proprietary. LICENSE.txt has complete terms

📁 frontend-design
   描述: Create distinctive, production-grade frontend interfaces with high design qualit...
   许可证: Complete terms in LICENSE.txt

📁 internal-comms
   描述: A set of resources to help me write all kinds of internal communications, using ...
   许可证: Complete terms in LICENSE.txt

📁 mcp-builder
   描述: Guide for creating high-quality MCP (Model Context Protocol) servers that enable...
   许可证: Complete terms in LICENSE.txt

📁 pdf
   描述: Use this skill whenever the user wants to do anything with PDF files. This inclu...
   许可证: Proprietary. LICENSE.txt has complete terms

📁 pptx
   描述: Use this skill any time a .pptx file is involved in any way — as input, output, ...
   许可证: Proprietary. LICENSE.txt has complete terms

📁 skill-creator
   描述: Create new skills, modify and improve existing skills, and measure skill perform...
   许可证: Complete terms in LICENSE.txt

📁 slack-gif-creator
   描述: Knowledge and utilities for creating animated GIFs optimized for Slack. Provides...
   许可证: Complete terms in LICENSE.txt

📁 theme-factory
   描述: Toolkit for styling artifacts with a theme. These artifacts can be slides, docs,...
   许可证: Complete terms in LICENSE.txt

📁 web-artifacts-builder
   描述: Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts ...
   许可证: Complete terms in LICENSE.txt

📁 webapp-testing
   描述: Toolkit for interacting with and testing local web applications using Playwright...
   许可证: Complete terms in LICENSE.txt

📁 xlsx
   描述: Use this skill whenever a spreadsheet file is the primary input or output. This ...
   许可证: Proprietary. LICENSE.txt has complete terms

共找到 17 个技能


```

# disclosure
```
python agent_skills_client.py disclosure pdf --root  C:\workspace\github\skills\skills\  --level L2
# pdf

# PDF Processing Guide

## Overview

This guide covers essential PDF processing operations using Python libraries and command-line tools. For advanced features, JavaScript libraries, and detailed examples, see REFERENCE.md. If you need to fill out a PDF form, read FORMS.md and follow its instructions.

## Quick Start

```python
from pypdf import PdfReader, PdfWriter

# Read a PDF
reader = PdfReader("document.pdf")
print(f"Pages: {len(reader.pages)}")

# Extract text
text = ""
for page in reader.pages:
    text += page.extract_text()
```

## Python Libraries

### pypdf - Basic Operations
......此处省略下文

```
