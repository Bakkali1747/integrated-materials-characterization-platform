# 合成测试样品

`synthetic_constant.csv` 是人工构造的常数参数数据，不是真实 CIP 或其他材料测量。

频率为 2–18 GHz、201 点；εr=4−j0.5，μr=1.5−j0.3。文件中的虚部为损耗数值，使用 `--imaginary-convention loss --convention-confirmed`。

仅用于软件运行演示和回归检查，不能作为科研实验结论或商业软件对照。

`synthetic_variant.csv` 同样为人工构造：2–18 GHz、101 点，εr=5−j0.8、μr=1.3−j0.4。它与 constant 的采样网格不同，用于验证比较流程不偷偷插值。

`batch_example.json` 可直接传给 `run_batch.py --manifest sample_data/batch_example.json`。两个名称均明确标注 SYNTHETIC，不代表两种真实材料。
