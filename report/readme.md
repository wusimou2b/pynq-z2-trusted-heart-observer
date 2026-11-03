> **2026-11-03 部署说明：** 当前仓库使用合规存储名称。本文件中的原 Notebook 名称及运行步骤仅适用于执行 `python3 -B prepare_delivery.py runtime --output ../trusted_heart_demo` 后生成的目录；请先按根目录 `readme.md` 完成准备与校验，勿直接运行仓库内的规范化副本。

# Current report and formal materials

The stable current handover is under materials/. The updated anonymous technical report is 33 pages; the older public-entry technical report is 29 pages and has not been updated to match it. Independent large-model collaboration records are 8 pages. The public versions use the current repository destination:

The updated report preserves the account-bearing GitHub links and photographs at the user's request; the device barcode and its printed number are masked in both files, and the original image data is not retained in the published copies. Identifying document metadata was removed, but suitability for a specific blind review has not been established.

https://github.com/wusimou2b/pynq-z2-trusted-heart-observer

The anonymous bilingual poster is supplied as one two-slide PPTX and one two-page PDF. Independent one-page Chinese and English posters are also retained; the English version serves the on-site printing requirement. These posters use a 16:9 page; select fit-to-A4 when printing the English page. Named posters and signed authorization documents are local-only materials and are excluded. Use materials/README_submission.md for the anonymous material index and materials/README.md for the public index; URL-bearing public versions are distinct from anonymous files. Nonvisual template revision and identity metadata is removed from public poster PPTX files where present; slide, drawing and media content is preserved. The material checksum file records the resulting public copies.

materials/sha256sums.txt is specific to the files actually included here and uses the actual lowercase file names. The updated anonymous report preserves its source document content and PDF appearance; identifying document properties were removed from the publication copies. The internal render-check handover and its machine paths are not repository contents.

Current deployment is `../board_runtime/runtime/ContinuousDemo25.ipynb`; use the complete sibling runtime/native directory layout described in the root README and `../board/README.md`. The current source run lasted 33.193811316 seconds with 832 records and 166 video frames. The new anonymous report separately describes a 115.984-second/2905-record/579-frame run; the older public report describes a different historical 80.652-second/2021-record/403-frame run. These records are not merged. Original legacy acceptance false flags remain false.

The final demonstration is `trusted_hr_browser_colors_final_20261102.mp4`, provided as a separate Release asset. It includes the corrected connection photograph, narration, music and four-colour explanation; see `../video/README.md` for its identity, licensing and technical checks. Subjective listening has not been performed. The previous `public_live` wrapper and its software tests are historical and have been superseded by the preserved portable runtime. Neither those tests nor the publication file checks establish clean-system reproduction, medical accuracy or full hardware acceptance.

The AMD guide (section 3.3.5.3, PDF page 24 / printed page 21) specifies seven report contents, previously mapped to the older 29-page public report as follows; section mapping for the 33-page revision should be checked against the new report itself:

| Required content | Report section |
|---|---|
| Background and innovation | 1.2, 1.5 |
| Design principles and functional block diagram | 2.1 |
| Hardware, software modules and interfaces | 2.2 |
| Optimization and before/after performance/resource comparison | 3.3 |
| Large-model collaboration, prompts and human decisions | 2.3.3 |
| Skills cases, lessons and verification boundaries | 2.3.4 |
| Reproduction procedure | 2.4 |

The five weighted criteria in section 3.3.5.5 (PDF page 25 / printed page 22) are innovation/application value 30%, performance/resource optimization 20%, correctness/test completeness 20%, model collaboration/Skills 15%, and documentation/reproducibility 15%. A chapter being present does not establish clean-system reproduction; the missing environment details and acceptance limits remain documented.
