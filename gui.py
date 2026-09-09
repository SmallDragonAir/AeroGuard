"""AeroGuard 原生 Tk 桌面界面。"""

import argparse
import json
import queue
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from main import run_full_diagnosis, save_json_report
from history import HistoryError, HistoryStore
from management import AddonManager, ManagementError
from report import build_report


SEVERITY_ORDER = {"error": 3, "warning": 2, "info": 1}


@dataclass
class DesktopScanResult:
    community_path: Path
    mode: str
    addons: list
    scan_errors: list
    issues: list
    stats: object
    timing: dict
    relationships: object

    def report_document(self):
        return build_report(
            community_path=self.community_path,
            scan_mode=self.mode,
            addons=self.addons,
            scan_errors=self.scan_errors,
            issues=self.issues,
            stats=self.stats,
            timing=self.timing,
            relationships=self.relationships,
        )


def run_desktop_scan(community_path, mode):
    """运行一次供 GUI 使用的完整诊断流程（与 CLI 共用同一实现）。"""
    path = Path(community_path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Community 路径不存在或不是目录：{path}")
    if mode not in {"quick", "full"}:
        raise ValueError(f"不支持的扫描模式：{mode}")

    addons, scan_errors, issues, stats, relationships, timing = (
        run_full_diagnosis(path, full_scan=(mode == "full"))
    )
    return DesktopScanResult(
        community_path=path,
        mode=mode,
        addons=addons,
        scan_errors=scan_errors,
        issues=issues,
        stats=stats,
        timing=timing,
        relationships=relationships,
    )


def diagnostic_summary(result):
    severity_counts = {severity: 0 for severity in SEVERITY_ORDER}
    for issue in result.issues:
        severity = issue.get("severity")
        if severity in severity_counts:
            severity_counts[severity] += 1
    relationships = result.relationships.summary()
    return {
        "addons": len(result.addons),
        "issues": len(result.issues),
        "errors": severity_counts["error"],
        "warnings": severity_counts["warning"],
        "resource_conflicts": relationships["resource_conflicts"],
        "airport_conflicts": relationships["airport_conflicts"],
        "scan_errors": len(result.scan_errors),
        "elapsed_s": round(result.timing["total"], 2),
    }


def issue_table_rows(issues):
    ordered = sorted(
        issues,
        key=lambda issue: (
            SEVERITY_ORDER.get(issue.get("severity"), 0),
            issue.get("affected_count", 1),
            issue.get("package", "").casefold(),
        ),
        reverse=True,
    )
    return [
        {
            "values": (
                issue.get("severity", "unknown").upper(),
                issue.get("rule_id", ""),
                issue.get("package", ""),
                issue.get("affected_count", 1),
                issue.get("impact", "unknown").upper(),
                issue.get("message", ""),
            ),
            "detail": issue,
        }
        for issue in ordered
    ]


def conflict_table_rows(relationships):
    rows = []
    for conflict in relationships.resource_conflicts:
        rows.append({
            "values": (
                "资源",
                conflict["severity"].upper(),
                conflict["path"],
                ", ".join(item["package"] for item in conflict["packages"]),
                conflict["reason"],
            ),
            "detail": conflict,
        })
    for conflict in relationships.airport_conflicts:
        rows.append({
            "values": (
                "机场",
                conflict["severity"].upper(),
                conflict["airport_code"],
                ", ".join(item["package"] for item in conflict["packages"]),
                conflict["reason"],
            ),
            "detail": conflict,
        })
    for cycle in relationships.dependency_cycles:
        detail = {"packages": cycle, "type": "dependency_cycle"}
        rows.append({
            "values": (
                "依赖环",
                "WARNING",
                " → ".join(cycle + cycle[:1]),
                ", ".join(cycle),
                "当前扫描根目录内存在循环依赖",
            ),
            "detail": detail,
        })
    return rows


def management_table_rows(inventory):
    rows = []
    for location in ("enabled", "disabled", "quarantined"):
        for record in inventory.get(location, []):
            rows.append({
                "values": (
                    record.get("status", ""),
                    record.get("package", ""),
                    record.get("version") or "",
                    record.get("content_type") or "",
                    record.get("title") or "",
                    record.get("error") or "",
                ),
                "detail": record,
            })
    return rows


class AeroGuardApp:
    """AeroGuard 的单窗口桌面应用。"""

    def __init__(self, root, community_path="", mode="quick", state_dir=None):
        self.root = root
        self.state_dir = state_dir
        self.result = None
        self._busy = False
        self._work_queue = queue.Queue()
        self._detail_by_item = {}
        self._management_by_item = {}

        self.path_var = tk.StringVar(value=str(community_path or ""))
        self.mode_var = tk.StringVar(value=mode)
        self.status_var = tk.StringVar(value="请选择 Community 路径后开始扫描。")
        self.summary_vars = {
            key: tk.StringVar(value="—")
            for key in (
                "addons", "issues", "errors", "warnings",
                "resource_conflicts", "airport_conflicts", "elapsed_s",
            )
        }

        self._configure_window()
        self._build_header()
        self._build_summary()
        self._build_tabs()
        self._build_status_bar()

    def _configure_window(self):
        self.root.title("AeroGuard — MSFS 插件诊断与管理")
        self.root.geometry("1280x800")
        self.root.minsize(980, 640)
        self.root.option_add("*Font", "{Segoe UI} 10")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        style = ttk.Style(self.root)
        for theme in ("vista", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18))
        style.configure("Metric.TLabel", font=("Segoe UI Semibold", 18))
        style.configure("Treeview", rowheight=25)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _build_header(self):
        frame = ttk.Frame(self.root, padding=(18, 14, 18, 8))
        frame.pack(fill="x")
        ttk.Label(frame, text="AeroGuard", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=5
        )
        ttk.Label(
            frame,
            text="本地、可解释的 MSFS Package 诊断与管理",
        ).grid(row=1, column=0, sticky="w", columnspan=5, pady=(0, 12))

        ttk.Label(frame, text="Community").grid(row=2, column=0, sticky="w")
        path_entry = ttk.Entry(frame, textvariable=self.path_var)
        path_entry.grid(row=2, column=1, sticky="ew", padx=(8, 6))
        ttk.Button(frame, text="浏览…", command=self._browse_community).grid(
            row=2, column=2, padx=(0, 12)
        )
        ttk.Combobox(
            frame,
            textvariable=self.mode_var,
            values=("quick", "full"),
            state="readonly",
            width=8,
        ).grid(row=2, column=3, padx=(0, 8))
        self.scan_button = ttk.Button(
            frame, text="开始扫描", command=self._start_scan
        )
        self.scan_button.grid(row=2, column=4)
        self.export_button = ttk.Button(
            frame,
            text="导出 JSON",
            command=self._export_json,
            state="disabled",
        )
        self.export_button.grid(row=2, column=5, padx=(8, 0))
        frame.columnconfigure(1, weight=1)

    def _build_summary(self):
        frame = ttk.Frame(self.root, padding=(18, 4, 18, 10))
        frame.pack(fill="x")
        metrics = (
            ("addons", "插件"),
            ("issues", "问题"),
            ("errors", "错误"),
            ("warnings", "警告"),
            ("resource_conflicts", "资源重叠"),
            ("airport_conflicts", "机场重复"),
            ("elapsed_s", "耗时 / 秒"),
        )
        for column, (key, label) in enumerate(metrics):
            card = ttk.LabelFrame(frame, text=label, padding=(14, 8))
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
            ttk.Label(
                card, textvariable=self.summary_vars[key], style="Metric.TLabel"
            ).pack()
            frame.columnconfigure(column, weight=1)

    def _tree_tab(self, notebook, title, columns, widths):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=title)
        tree = ttk.Treeview(
            frame,
            columns=tuple(columns),
            show="headings",
            selectmode="browse",
        )
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        for column, heading in columns.items():
            tree.heading(column, text=heading)
            tree.column(column, width=widths.get(column, 120), minwidth=70)
        return frame, tree

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        _, self.issue_tree = self._tree_tab(
            self.notebook,
            "问题",
            {
                "severity": "等级", "rule": "规则", "package": "插件",
                "affected": "数量", "impact": "运行影响", "message": "说明",
            },
            {
                "severity": 80, "rule": 190, "package": 230,
                "affected": 65, "impact": 155, "message": 420,
            },
        )
        self.issue_tree.bind("<Double-1>", self._show_selected_detail)

        _, self.conflict_tree = self._tree_tab(
            self.notebook,
            "冲突与依赖",
            {
                "type": "类型", "severity": "等级", "resource": "资源 / 代码",
                "packages": "涉及插件", "reason": "判断",
            },
            {
                "type": 80, "severity": 80, "resource": 300,
                "packages": 380, "reason": 360,
            },
        )
        self.conflict_tree.bind("<Double-1>", self._show_selected_detail)

        management_frame, self.management_tree = self._tree_tab(
            self.notebook,
            "插件管理",
            {
                "status": "状态", "package": "包目录", "version": "版本",
                "type": "类型", "title": "标题", "error": "元数据异常",
            },
            {
                "status": 90, "package": 260, "version": 100,
                "type": 110, "title": 300, "error": 380,
            },
        )
        button_bar = ttk.Frame(management_frame, padding=(0, 8, 0, 0))
        button_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        for text, command in (
            ("刷新清单", self._refresh_inventory),
            ("启用", lambda: self._manage_selected("enable")),
            ("禁用", lambda: self._manage_selected("disable")),
            ("隔离", lambda: self._manage_selected("quarantine")),
            ("恢复", lambda: self._manage_selected("restore")),
            ("保存 Profile", self._save_profile),
            ("应用 Profile", self._apply_profile),
            ("安装 ZIP", self._choose_install_zip),
            ("安装目录", self._choose_install_directory),
            ("回滚安装", self._rollback_install),
        ):
            ttk.Button(button_bar, text=text, command=command).pack(
                side="left", padx=(0, 6)
            )
        self.management_tree.bind("<Double-1>", self._show_management_detail)

        history_frame, self.history_tree = self._tree_tab(
            self.notebook,
            "历史与基线",
            {
                "time": "记录时间", "id": "快照 ID", "label": "标签",
                "mode": "模式", "addons": "插件", "issues": "问题",
                "conflicts": "资源重叠", "error": "异常",
            },
            {
                "time": 175, "id": 220, "label": 160, "mode": 70,
                "addons": 65, "issues": 65, "conflicts": 85, "error": 300,
            },
        )
        history_buttons = ttk.Frame(history_frame, padding=(0, 8, 0, 0))
        history_buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
        for text, command in (
            ("刷新历史", self._refresh_history),
            ("记录当前结果", self._record_current_snapshot),
            ("设为基线", self._set_selected_baseline),
            ("与基线比较", self._compare_current_baseline),
        ):
            ttk.Button(history_buttons, text=text, command=command).pack(
                side="left", padx=(0, 6)
            )
        self.history_tree.bind("<Double-1>", self._show_selected_detail)

        errors_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(errors_frame, text="扫描异常")
        self.error_text = tk.Text(errors_frame, wrap="word", state="disabled")
        error_scroll = ttk.Scrollbar(
            errors_frame, orient="vertical", command=self.error_text.yview
        )
        self.error_text.configure(yscrollcommand=error_scroll.set)
        self.error_text.grid(row=0, column=0, sticky="nsew")
        error_scroll.grid(row=0, column=1, sticky="ns")
        errors_frame.rowconfigure(0, weight=1)
        errors_frame.columnconfigure(0, weight=1)

    def _build_status_bar(self):
        frame = ttk.Frame(self.root, padding=(18, 2, 18, 12))
        frame.pack(fill="x")
        ttk.Label(frame, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=180)
        self.progress.pack(side="right")

    def _browse_community(self):
        selected = filedialog.askdirectory(title="选择 Community 文件夹")
        if selected:
            self.path_var.set(selected)
            self._refresh_inventory()

    def _community_path(self):
        value = self.path_var.get().strip().strip('"')
        if not value:
            raise ValueError("请先选择 Community 路径")
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"Community 路径不存在或不是目录：{path}")
        return path

    def _manager(self):
        return AddonManager(self._community_path(), self.state_dir)

    def _history_store(self):
        return HistoryStore(self._community_path(), self.state_dir)

    def _on_close(self):
        """关闭窗口前确认：后台任务（如安装/回滚）仍在运行时先询问。"""
        if self._busy:
            confirmed = messagebox.askokcancel(
                "AeroGuard",
                "后台任务仍在运行，现在退出可能中断正在进行的操作。"
                "确定要退出吗？",
                parent=self.root,
            )
            if not confirmed:
                return
        self.root.destroy()

    def _run_async(self, label, task, on_success):
        if self._busy:
            self.status_var.set("已有任务正在运行，请等待完成。")
            return
        self._busy = True
        self.scan_button.configure(state="disabled")
        self.progress.start(10)
        self.status_var.set(label)

        def worker():
            try:
                self._work_queue.put((True, task(), on_success))
            except Exception as error:
                self._work_queue.put((False, error, None))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, self._poll_worker)

    def _poll_worker(self):
        try:
            succeeded, payload, callback = self._work_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_worker)
            return

        self._busy = False
        self.scan_button.configure(state="normal")
        self.progress.stop()
        if not succeeded:
            self.status_var.set("任务失败。")
            messagebox.showerror("AeroGuard", str(payload), parent=self.root)
            return
        try:
            callback(payload)
        except Exception as error:
            self.status_var.set("结果呈现失败。")
            messagebox.showerror("AeroGuard", str(error), parent=self.root)

    def _start_scan(self):
        try:
            path = self._community_path()
        except ValueError as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return
        mode = self.mode_var.get()
        self._run_async(
            f"正在执行{'完整' if mode == 'full' else '快速'}扫描…",
            lambda: run_desktop_scan(path, mode),
            self._receive_scan,
        )

    @staticmethod
    def _clear_tree(tree):
        for item in tree.get_children():
            tree.delete(item)

    def _fill_detail_tree(self, tree, rows):
        self._clear_tree(tree)
        for item_id in list(self._detail_by_item):
            if item_id.startswith(str(tree)):
                del self._detail_by_item[item_id]
        for index, row in enumerate(rows):
            item_id = f"{tree}-{index}"
            tree.insert("", "end", iid=item_id, values=row["values"])
            self._detail_by_item[item_id] = row["detail"]

    def _receive_scan(self, result):
        self.result = result
        summary = diagnostic_summary(result)
        for key, variable in self.summary_vars.items():
            variable.set(summary[key])
        self._fill_detail_tree(self.issue_tree, issue_table_rows(result.issues))
        self._fill_detail_tree(
            self.conflict_tree, conflict_table_rows(result.relationships)
        )
        self._set_error_text(result.scan_errors)
        self.export_button.configure(state="normal")
        self.status_var.set(
            f"扫描完成：{summary['addons']} 个插件，{summary['issues']} 条问题，"
            f"耗时 {summary['elapsed_s']:.2f} 秒。双击表格行可查看完整数据。"
        )
        self._refresh_inventory()

    def _set_error_text(self, errors):
        text = (
            json.dumps(errors, ensure_ascii=False, indent=2)
            if errors else "没有扫描异常。"
        )
        self.error_text.configure(state="normal")
        self.error_text.delete("1.0", "end")
        self.error_text.insert("1.0", text)
        self.error_text.configure(state="disabled")

    def _show_json_detail(self, title, document):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("900x620")
        text = tk.Text(window, wrap="none")
        y_scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        x_scroll = ttk.Scrollbar(window, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)
        text.insert("1.0", json.dumps(document, ensure_ascii=False, indent=2))
        text.configure(state="disabled")

    def _show_selected_detail(self, event):
        item_id = event.widget.focus()
        detail = self._detail_by_item.get(item_id)
        if detail is not None:
            self._show_json_detail("检测详情", detail)

    def _show_management_detail(self, event):
        item_id = event.widget.focus()
        detail = self._management_by_item.get(item_id)
        if detail is not None:
            self._show_json_detail("插件详情", detail)

    def _export_json(self):
        if self.result is None:
            return
        filename = filedialog.asksaveasfilename(
            title="导出 AeroGuard JSON 报告",
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("所有文件", "*.*")),
        )
        if not filename:
            return
        output = save_json_report(self.result.report_document(), filename)
        self.status_var.set(f"JSON 报告已保存：{output}")

    def _refresh_inventory(self):
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            self.status_var.set(str(error))
            return
        self._run_async("正在刷新插件管理清单…", manager.inventory, self._receive_inventory)

    def _receive_inventory(self, inventory):
        self._clear_tree(self.management_tree)
        self._management_by_item.clear()
        rows = management_table_rows(inventory)
        for index, row in enumerate(rows):
            item_id = f"management-{index}"
            self.management_tree.insert("", "end", iid=item_id, values=row["values"])
            self._management_by_item[item_id] = row["detail"]
        summary = inventory["summary"]
        self.status_var.set(
            f"管理清单：启用 {summary['enabled']}，禁用 {summary['disabled']}，"
            f"隔离 {summary['quarantined']}，无效目录 {summary['invalid_entries']}。"
        )

    def _selected_management_record(self):
        selection = self.management_tree.selection()
        if not selection:
            raise ManagementError("请先在插件管理表格中选择一个包")
        return self._management_by_item[selection[0]]

    def _manage_selected(self, action):
        try:
            record = self._selected_management_record()
            manager = self._manager()
            status = record["status"]
            if action == "enable" and status != "disabled":
                raise ManagementError("只有禁用状态的包可以启用")
            if action == "disable" and status != "enabled":
                raise ManagementError("只有启用状态的包可以禁用")
            if action == "restore" and status != "quarantined":
                raise ManagementError("只有隔离状态的包可以恢复")
            if action == "quarantine" and status == "quarantined":
                raise ManagementError("该包已经位于隔离区")
            reason = "GUI manual quarantine"
            if action == "quarantine":
                reason = simpledialog.askstring(
                    "隔离原因", "记录隔离原因：", parent=self.root,
                    initialvalue="待排查冲突",
                )
                if reason is None:
                    return

            operations = {
                "enable": lambda: manager.enable(record["package"]),
                "disable": lambda: manager.disable(record["package"]),
                "quarantine": lambda: manager.quarantine(record["package"], reason),
                "restore": lambda: manager.restore_quarantine(record["package"]),
            }
            self._run_async(
                f"正在执行：{action} {record['package']}…",
                operations[action],
                self._receive_management_action,
            )
        except (ValueError, ManagementError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)

    def _receive_management_action(self, transaction):
        warnings = transaction.get("dependency_warnings", [])
        suffix = f"；依赖警告 {len(warnings)} 条" if warnings else ""
        self.status_var.set(
            f"操作完成，事务 {transaction['id']}{suffix}。重启模拟器后生效。"
        )
        if warnings:
            self._show_json_detail("依赖警告", warnings)
        self.root.after(100, self._refresh_inventory)

    def _refresh_history(self):
        try:
            store = self._history_store()
        except (ValueError, HistoryError) as error:
            self.status_var.set(str(error))
            return
        self._run_async(
            "正在读取扫描历史…",
            lambda: store.list_snapshots(limit=100),
            self._receive_history,
        )

    def _receive_history(self, snapshots):
        rows = []
        for snapshot in snapshots:
            summary = snapshot.get("summary", {})
            rows.append({
                "values": (
                    snapshot.get("recorded_at") or "",
                    snapshot.get("snapshot_id") or "",
                    snapshot.get("label") or "",
                    snapshot.get("scan_mode") or "",
                    summary.get("addons", ""),
                    summary.get("issues", ""),
                    summary.get("resource_conflicts", ""),
                    snapshot.get("error") or "",
                ),
                "detail": snapshot,
            })
        self._fill_detail_tree(self.history_tree, rows)
        self.status_var.set(f"已读取 {len(snapshots)} 个扫描历史快照。")

    def _current_report_for_history(self):
        if self.result is None:
            raise HistoryError("请先完成一次扫描")
        if self.result.community_path != self._community_path():
            raise HistoryError("路径已改变，请先重新扫描当前 Community")
        return self.result.report_document()

    def _record_current_snapshot(self):
        try:
            store = self._history_store()
            report = self._current_report_for_history()
        except (ValueError, HistoryError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return
        label = simpledialog.askstring(
            "记录扫描历史", "可选标签：", parent=self.root
        )
        if label is None:
            return

        def receive(snapshot):
            self.status_var.set(f"快照已保存：{snapshot['snapshot_id']}")
            self.root.after(100, self._refresh_history)

        self._run_async(
            "正在保存紧凑扫描快照…",
            lambda: store.record(report, label=label or None),
            receive,
        )

    def _selected_snapshot(self):
        selection = self.history_tree.selection()
        if not selection:
            raise HistoryError("请先选择一个历史快照")
        snapshot = self._detail_by_item.get(selection[0])
        if not snapshot or snapshot.get("error"):
            raise HistoryError("所选历史快照不可用")
        return snapshot

    def _set_selected_baseline(self):
        try:
            snapshot = self._selected_snapshot()
            store = self._history_store()
        except (ValueError, HistoryError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return
        name = simpledialog.askstring("设置环境基线", "基线名称：", parent=self.root)
        if not name:
            return
        self._run_async(
            f"正在设置基线 {name}…",
            lambda: store.set_baseline(name, snapshot["snapshot_id"]),
            lambda result: self.status_var.set(
                f"环境基线已保存：{result['baseline_name']}"
            ),
        )

    def _compare_current_baseline(self):
        try:
            store = self._history_store()
            report = self._current_report_for_history()
        except (ValueError, HistoryError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return
        name = simpledialog.askstring("比较环境基线", "基线名称：", parent=self.root)
        if not name:
            return

        def receive(comparison):
            changes = comparison["summary"]["total_changes"]
            warnings = comparison["summary"]["compatibility_warnings"]
            self.status_var.set(
                f"基线比较完成：{changes} 项变化，{warnings} 条兼容性提示。"
            )
            self._show_json_detail(f"基线比较 — {name}", comparison)

        self._run_async(
            f"正在与基线 {name} 比较…",
            lambda: store.compare(name, report),
            receive,
        )

    def _save_profile(self):
        name = simpledialog.askstring("保存 Profile", "Profile 名称：", parent=self.root)
        if not name:
            return
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return
        self._run_async(
            f"正在保存 Profile {name}…",
            lambda: manager.save_profile(name),
            lambda result: self.status_var.set(
                f"Profile 已保存：{result['profile_path']}"
            ),
        )

    def _apply_profile(self):
        name = simpledialog.askstring("应用 Profile", "Profile 名称：", parent=self.root)
        if not name:
            return
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return

        def receive_plan(plan):
            move_count = len(plan["moves"])
            warning_count = len(plan.get("warnings", [])) + len(
                plan.get("dependency_warnings", [])
            )
            if move_count == 0:
                self.status_var.set(f"Profile {name} 已处于目标状态。")
                return
            accepted = messagebox.askyesno(
                "应用 Profile",
                f"Profile {name} 将移动 {move_count} 个包，"
                f"有 {warning_count} 条提示。是否应用？",
                parent=self.root,
            )
            if accepted:
                self._run_async(
                    f"正在应用 Profile {name}…",
                    lambda: manager.apply_profile(name),
                    self._receive_management_action,
                )

        self._run_async(
            f"正在预演 Profile {name}…",
            lambda: manager.apply_profile(name, dry_run=True),
            receive_plan,
        )

    def _choose_install_zip(self):
        source = filedialog.askopenfilename(
            title="选择插件 ZIP",
            filetypes=(("ZIP", "*.zip"), ("所有文件", "*.*")),
        )
        if source:
            self._inspect_then_offer_install(source)

    def _choose_install_directory(self):
        source = filedialog.askdirectory(title="选择插件目录或包集合目录")
        if source:
            self._inspect_then_offer_install(source)

    def _inspect_then_offer_install(self, source):
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return

        def receive_inspection(inspection):
            summary = inspection.summary()
            if not inspection.can_install:
                self._show_json_detail("安装前检查未通过", inspection.as_dict())
                self.status_var.set("安装前检查未通过，Community 未发生变化。")
                return
            package_names = ", ".join(
                item["folder_name"] for item in inspection.packages
            )
            allow_executables = inspection.requires_executable_override
            executable_note = (
                f"\n检测到 {summary['executable_files']} 个可执行文件；"
                "AeroGuard 只复制、不执行。"
                if allow_executables else ""
            )
            accepted = messagebox.askyesno(
                "安装检查完成",
                f"包：{package_names}\n问题：{summary['issues']} 条"
                f"{executable_note}\n\n是否开始安装？",
                parent=self.root,
            )
            if accepted:
                self._run_async(
                    "正在安装并保存可回滚备份…",
                    lambda: manager.install(source, allow_executables),
                    self._receive_install,
                )

        self._run_async(
            "正在暂存并检查安装源…",
            lambda: manager.inspect_install_source(source),
            receive_inspection,
        )

    def _receive_install(self, result):
        transaction = result["transaction"]
        self.status_var.set(
            f"安装完成，事务 {transaction['id']}。重启模拟器后生效。"
        )
        self._show_json_detail("安装事务", transaction)
        self.root.after(100, self._refresh_inventory)

    def _rollback_install(self):
        transaction_id = simpledialog.askstring(
            "回滚安装", "安装事务 ID：", parent=self.root
        )
        if not transaction_id:
            return
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror("AeroGuard", str(error), parent=self.root)
            return
        self._run_async(
            f"正在回滚安装事务 {transaction_id}…",
            lambda: manager.rollback_install(transaction_id),
            self._receive_management_action,
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="aeroguard-gui",
        description="启动 AeroGuard 原生桌面界面。",
    )
    parser.add_argument("community_path", nargs="?", default="")
    parser.add_argument("--mode", choices=("quick", "full"), default="quick")
    parser.add_argument("--state-dir")
    return parser.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    args = parse_args(argv)
    root = tk.Tk()
    AeroGuardApp(
        root,
        community_path=args.community_path,
        mode=args.mode,
        state_dir=args.state_dir,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
