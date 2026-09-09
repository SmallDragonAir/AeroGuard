# tools/dev —— 开发期脚本

这些脚本是开发 AeroGuard 期间用于现场调试、规则对比与性能调查的
辅助工具，**不属于产品代码**，也**不应被 README 架构图引用**。

它们大多硬编码了本机路径（例如 `D:\MSFS2024_DATA\Community`），
换机器后需要自行修改，因此不适合纳入常规测试或 CI。

从仓库根目录运行（脚本已自带 `sys.path` 引导）：

```powershell
python tools/dev/debug.py            # 检查某个目录的 symlink / junction 属性
python tools/dev/debug_index.py      # 用 fsl-a32x 验证 build_file_index 的缺失判定
python tools/dev/compare_analyzer.py # 对比旧版与新版 Analyzer 的 SIZE_MISMATCH 结果
```

各文件说明：

| 文件 | 用途 | 状态 |
|---|---|---|
| `analyzer_old.py` | 旧版 Analyzer（逐文件 `exists()`/`rglob`），仅作为对比基线 | 已冻结，不再维护 |
| `compare_analyzer.py` | 对比新旧 Analyzer 的 Package 级数量差异 | 需要真实 Community |
| `debug.py` | 打印路径的 is_dir/is_symlink/is_junction/readlink 信息 | 一次性调试 |
| `debug_index.py` | 针对 fsl-a32x 检查索引判定缺失与磁盘实际状态是否一致 | 需要该插件目录 |

> 新的一致性逻辑请优先写成 `tests/` 下的自动化测试，
> 而不是继续依赖这些一次性脚本。
