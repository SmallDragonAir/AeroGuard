"""锁定 Analyzer 跨包并行建索引的确定性。

并行仅改变文件树枚举的调度方式；无论 workers=None（自动并行）、
workers=1（强制串行）还是指定线程数，输出问题列表必须完全一致。
"""

import tempfile
import unittest
from pathlib import Path

from .fixtures import make_addon
from scanner import scan_community
from analyzer import (
    PARALLEL_MIN_ADDONS,
    analyze_community_with_stats,
)


def build_community(community, addon_count):
    for index in range(addon_count):
        folder = f"addon-{index:02d}"
        make_addon(
            community,
            folder,
            layout_content=[
                {"path": "ok.txt", "size": 3},
                {"path": "gone.txt", "size": 1},   # 声明的文件不存在
            ],
            files={
                "ok.txt": b"abc",
                "extra.txt": b"zzz",               # 未登记文件
            },
        )


class AnalyzerParallelDeterminismTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.community = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_auto_parallel_matches_serial_output(self):
        build_community(self.community, PARALLEL_MIN_ADDONS + 4)
        addons, _ = scan_community(self.community)

        serial_issues, serial_stats = analyze_community_with_stats(
            addons, full_scan=True, workers=1
        )
        auto_issues, auto_stats = analyze_community_with_stats(
            addons, full_scan=True, workers=None
        )

        # 输出必须逐字一致（顺序、明细、计数）
        self.assertEqual(serial_issues, auto_issues)

        self.assertEqual(serial_stats.addon_count, auto_stats.addon_count)
        serial_packages = {
            item["package"] for item in serial_stats.package_timings
        }
        auto_packages = {
            item["package"] for item in auto_stats.package_timings
        }
        self.assertEqual(serial_packages, auto_packages)

        # 并行后整段耗时不应慢于串行（允许小幅抖动：放宽到 3 倍以内）
        self.assertLess(
            auto_stats.tree_walk_time,
            max(serial_stats.tree_walk_time * 3, 0.001) + 1.0,
        )

    def test_explicit_workers_matches_serial(self):
        build_community(self.community, 6)
        addons, _ = scan_community(self.community)

        serial_issues, _ = analyze_community_with_stats(
            addons, full_scan=True, workers=1
        )
        threaded_issues, _ = analyze_community_with_stats(
            addons, full_scan=True, workers=3
        )

        self.assertEqual(serial_issues, threaded_issues)

    def test_small_community_stays_serial_correct(self):
        build_community(self.community, 3)
        addons, _ = scan_community(self.community)

        issues, stats = analyze_community_with_stats(
            addons, full_scan=True
        )

        # 每个插件都有 1 条缺失 + 1 条未登记
        self.assertEqual(
            sum(1 for issue in issues
                if issue["rule_id"] == "LAYOUT_FILE_MISSING"),
            3,
        )
        self.assertEqual(
            sum(1 for issue in issues
                if issue["rule_id"] == "LAYOUT_UNLISTED_FILE"),
            3,
        )
        self.assertEqual(stats.addon_count, 3)


if __name__ == "__main__":
    unittest.main()
