# COD 自动物相匹配

v0.24.0 起，XRD 页面默认启用 **COD 无机物相库** 自动 search-match。它提供候选相，不是物相鉴定。

## 数据来源与许可

- 晶体结构来源：[Crystallography Open Database (COD)](https://www.crystallography.net/cod/) 2026-07-02 快照的无机子集。
- 派生参考库：[QualX reference databases from the COD](https://zenodo.org/records/23297507)（CC-BY-4.0）。
- 本程序整理为每个 COD 条目保留按相对强度排序的前 20 条衍射线（d, 相对强度），共 88,311 个无机相，约 173 万条线。
- 许可：**CC-BY-4.0**。完整署名与引用见 [assets/COD_LICENSE.txt](../assets/COD_LICENSE.txt)。
- 本程序**不包含 ICDD PDF-2/PDF-4/PDF-5+ 卡片**；这些是商业授权数据库，不能从公开网络下载后随程序分发。

## 工作方式

1. 分析开始时，程序在用户数据目录准备 COD 库（首次从安装包内 `assets/cod_inorg_compact.zip` 解压约 100 MB 到 `%LOCALAPPDATA%\IntegratedMaterialsCharacterizationPlatform\phase_library\`）。
2. 用检测峰的 2θ 与 d 值，按容差（默认 0.2°）在 SQLite 索引中查找候选相。
3. 对候选相计算：
   - `reference_coverage`：参考行强度加权覆盖率；
   - `observed_coverage`：实测峰强度加权覆盖率；
   - `score = 0.6 × reference_coverage + 0.4 × observed_coverage`。
4. 按分数返回前 10 个候选，写入 `phase_library_matching.json`，并在界面摘要和报告中显示前 8 个。
5. 页面可取消勾选“自动匹配 COD 物相库”关闭。

## 输出

```text
phase_library_matching.json
{
  "matches": [
    {
      "phase_id": 4519515,
      "formula": "Fe",
      "mineral": null,
      "spacegroup": "I m -3 m",
      "score": 0.83,
      "reference_coverage": ...,
      "observed_coverage": ...,
      "matched_count": ...,
      "reference_count": ...,
      "matched_lines": [...]
    }
  ],
  "library": {"source": "COD", "license": "CC-BY-4.0", "phase_count": 88311},
  "screening_only": true
}
```

## 解释边界

- COD 是**计算模拟**的粉末图谱，不是 ICDD 实验 PDF 卡片；峰位/强度与实验卡片可能有差异。
- 同一个峰位可能对应多个同构/同晶型相（例如 bcc Fe、Cr 与无序合金）；仅凭 XRD 不能唯一确定元素组成。
- 分数是峰位匹配程度，不是相含量；不能直接作为定量相分析。
- 候选必须结合样品成分、工艺、PDF 卡片/结构数据库和 Rietveld 等定量方法核对。
- 当前内置的是 COD **无机**子集；有机物、药物、部分矿物/AMCSD 条目未包含。
- 结果状态仍为 PENDING/WARNING/NOT_COMPUTABLE，不自动升级为 VALIDATED。

## 引用

使用本功能时请引用：

- Gražulis, S. et al. (2009). Crystallography Open Database – an open-access collection of crystal structures. *J. Appl. Cryst.* 42, 726–729.
- Gražulis, S. et al. (2012). COD: an open-access collection of crystal structures and platform for world-wide collaboration. *Nucleic Acids Research* 40(D1), D420–D427.
- Altomare, A. et al. (2015). QUALX2.0: a qualitative phase analysis software using the freely available database POW_COD. *J. Appl. Cryst.* 48, 598–603.

数据下载页：<https://zenodo.org/records/23297507>
