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

from i18n import (
    current_language,
    localize_document,
    localize_text,
    set_language,
    tr,
)
from verify import verify_package
from export import export_html, export_markdown
from main import run_diagnosis_with_context, save_json_report
from history import HistoryError, HistoryStore
from management import AddonManager, ManagementError
from report import build_report


SEVERITY_ORDER = {"error": 3, "warning": 2, "info": 1}

_LANG_OPTIONS = ("中文", "English")


def _lang_display_name():
    return "中文" if current_language() == "zh" else "English"


def _lang_code_from_display(name):
    return "zh" if name == "中文" else "en"


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


def run_desktop_scan(community_path, mode, state_dir=None):
    """运行一次供 GUI 使用的完整诊断流程（与 CLI 共用同一实现）。"""
    path = Path(community_path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(tr("gui.err.not_dir", path=path))
    if mode not in {"quick", "full"}:
        raise ValueError(tr("gui.err.bad_mode", mode=mode))

    addons, scan_errors, issues, stats, relationships, timing = (
        run_diagnosis_with_context(
            path, full_scan=(mode == "full"), state_dir=state_dir
        )
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


def _notes_snippet(issue):
    """问题明细中展示用的备注缩写（取第一条已知结论）。"""
    notes = issue.get("notes") or []
    if not notes:
        return ""
    text = str(notes[0].get("text") or "").strip()
    if not text:
        return ""
    return text if len(text) <= 60 else text[:57] + "..."


# 行级配色标签（ttk.Treeview tag）
SEVERITY_TAG_COLORS = {
    "tag_error": "#c62828",
    "tag_warning": "#b26a00",
    "tag_info": "#1a56db",
    "tag_downgraded": "#0e7490",
}


def issue_row_tag(issue):
    """按严重等级与降级状态选择行标签。"""
    if issue.get("override") or issue.get("original_severity"):
        return "tag_downgraded"
    severity = issue.get("severity")
    if severity == "error":
        return "tag_error"
    if severity == "warning":
        return "tag_warning"
    return "tag_info"


def conflict_row_tag(conflict):
    if conflict.get("severity") == "warning":
        return "tag_warning"
    if conflict.get("severity") == "error":
        return "tag_error"
    return "tag_info"


def _value_sort_key(value):
    """排序键：数字按数值、其余按字符串不区分大小写。"""
    if isinstance(value, bool):
        return (0, int(value), "")
    if isinstance(value, (int, float)):
        return (0, value, "")
    return (1, 0, str(value).casefold())


def sort_rows(rows, column, reverse=False):
    """按 values 中第 column 列排序行列表。"""
    return sorted(
        rows,
        key=lambda row: _value_sort_key(row["values"][column]),
        reverse=reverse,
    )


def filter_rows(rows, query):
    """按查询文本过滤行；空查询返回原列表。"""
    query = (query or "").strip().casefold()
    if not query:
        return rows
    return [
        row for row in rows
        if query in " ".join(str(value) for value in row["values"]).casefold()
    ]


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
                _notes_snippet(issue),
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
                tr("gui.row.type_resource"),
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
                tr("gui.row.type_airport"),
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
                tr("gui.row.type_cycle"),
                "WARNING",
                " → ".join(cycle + cycle[:1]),
                ", ".join(cycle),
                tr("rel.cycle.exists"),
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
        self.lang_var = tk.StringVar(value=_lang_display_name())
        self.status_var = tk.StringVar(value=tr("gui.status.choose_first"))
        self._has_inventory = False
        self._has_history = False
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
        self.root.title(tr("gui.window.title"))
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
            text=tr("app.subtitle"),
        ).grid(row=1, column=0, sticky="w", columnspan=5, pady=(0, 12))

        ttk.Label(frame, text=tr("gui.field.community")).grid(row=2, column=0, sticky="w")
        path_entry = ttk.Entry(frame, textvariable=self.path_var)
        path_entry.grid(row=2, column=1, sticky="ew", padx=(8, 6))
        ttk.Button(frame, text=tr("gui.button.browse"), command=self._browse_community).grid(
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
            frame, text=tr("gui.button.start_scan"), command=self._start_scan
        )
        self.scan_button.grid(row=2, column=4)
        self.export_button = ttk.Button(
            frame,
            text=tr("gui.button.export_json"),
            command=self._export_json,
            state="disabled",
        )
        self.export_button.grid(row=2, column=5, padx=(8, 0))
        ttk.Label(frame, text=tr("gui.lang.label")).grid(
            row=2, column=6, sticky="e", padx=(14, 4)
        )
        self.lang_box = ttk.Combobox(
            frame,
            textvariable=self.lang_var,
            values=_LANG_OPTIONS,
            state="readonly",
            width=9,
        )
        self.lang_box.grid(row=2, column=7, padx=(0, 4))
        self.lang_box.bind("<<ComboboxSelected>>", self._on_language_change)
        frame.columnconfigure(1, weight=1)

    def _build_summary(self):
        frame = ttk.Frame(self.root, padding=(18, 4, 18, 10))
        frame.pack(fill="x")
        metrics = (
            ("addons", tr("gui.metric.addons")),
            ("issues", tr("gui.metric.issues")),
            ("errors", tr("gui.metric.errors")),
            ("warnings", tr("gui.metric.warnings")),
            ("resource_conflicts", tr("gui.metric.resource_conflicts")),
            ("airport_conflicts", tr("gui.metric.airport_conflicts")),
            ("elapsed_s", tr("gui.metric.elapsed")),
        )
        for column, (key, label) in enumerate(metrics):
            card = ttk.LabelFrame(frame, text=label, padding=(14, 8))
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
            ttk.Label(
                card, textvariable=self.summary_vars[key], style="Metric.TLabel"
            ).pack()
            frame.columnconfigure(column, weight=1)

    def _tree_tab(self, notebook, title, columns, widths, filterable=False):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=title)

        filter_var = None
        if filterable:
            filter_var = tk.StringVar()
            filter_bar = ttk.Frame(frame)
            filter_bar.grid(row=0, column=0, columnspan=2,
                            sticky="ew", pady=(0, 6))
            ttk.Label(filter_bar, text=tr("gui.search.label")).pack(
                side="left"
            )
            entry = ttk.Entry(filter_bar, textvariable=filter_var)
            entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
            ttk.Button(
                filter_bar, text=tr("gui.search.clear"),
                command=lambda: filter_var.set(""),
            ).pack(side="left")

        tree = ttk.Treeview(
            frame,
            columns=tuple(columns),
            show="headings",
            selectmode="browse",
        )
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        top_row = 1 if filterable else 0
        tree.grid(row=top_row, column=0, sticky="nsew")
        y_scroll.grid(row=top_row, column=1, sticky="ns")
        x_scroll.grid(row=top_row + 1, column=0, sticky="ew")
        frame.rowconfigure(top_row, weight=1)
        frame.columnconfigure(0, weight=1)

        for tag_name, color in SEVERITY_TAG_COLORS.items():
            tree.tag_configure(tag_name, foreground=color)

        columns_order = list(columns)
        tree._ag_columns = columns_order
        tree._ag_all_rows = []
        tree._ag_filter_var = filter_var
        tree._ag_sort = None
        if filter_var is not None:
            entry.bind(
                "<KeyRelease>",
                lambda event, t=tree: self._apply_tree_filter(t),
            )
            filter_var.trace_add(
                "write",
                lambda *args, t=tree: self._apply_tree_filter(t),
            )

        for index, (column, heading) in enumerate(columns.items()):
            tree.heading(
                column, text=heading,
                command=lambda c=column, t=tree: self._toggle_tree_sort(t, c),
            )
            tree.column(column, width=widths.get(column, 120), minwidth=70)
        return frame, tree

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        _, self.issue_tree = self._tree_tab(
            self.notebook,
            tr("gui.tab.issues"),
            {
                "severity": tr("gui.head.severity"), "rule": tr("gui.head.rule"),
                "package": tr("gui.head.package"),
                "affected": tr("gui.head.affected"),
                "impact": tr("gui.head.impact"), "message": tr("gui.head.message"),
                "notes": tr("gui.head.notes"),
            },
            {
                "severity": 80, "rule": 190, "package": 230,
                "affected": 65, "impact": 155, "message": 380, "notes": 220,
            },
            filterable=True,
        )
        self.issue_tree.bind("<Double-1>", self._show_selected_detail)

        _, self.conflict_tree = self._tree_tab(
            self.notebook,
            tr("gui.tab.conflicts"),
            {
                "type": tr("gui.head.type"), "severity": tr("gui.head.severity"),
                "resource": tr("gui.head.resource"),
                "packages": tr("gui.head.packages"),
                "reason": tr("gui.head.reason"),
            },
            {
                "type": 80, "severity": 80, "resource": 300,
                "packages": 380, "reason": 360,
            },
            filterable=True,
        )
        self.conflict_tree.bind("<Double-1>", self._show_selected_detail)

        management_frame, self.management_tree = self._tree_tab(
            self.notebook,
            tr("gui.tab.management"),
            {
                "status": tr("gui.head.status"), "package": tr("gui.head.folder"),
                "version": tr("gui.head.version"),
                "type": tr("gui.head.type"), "title": tr("gui.head.title"),
                "error": tr("gui.head.meta_error"),
            },
            {
                "status": 90, "package": 260, "version": 100,
                "type": 110, "title": 300, "error": 380,
            },
        )
        button_bar = ttk.Frame(management_frame, padding=(0, 8, 0, 0))
        button_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        for text, command in (
            (tr("gui.action.refresh_inventory"), self._refresh_inventory),
            (tr("gui.action.enable"), lambda: self._manage_selected("enable")),
            (tr("gui.action.disable"), lambda: self._manage_selected("disable")),
            (tr("gui.action.quarantine"), lambda: self._manage_selected("quarantine")),
            (tr("gui.action.restore"), lambda: self._manage_selected("restore")),
            (tr("gui.action.save_profile"), self._save_profile),
            (tr("gui.action.apply_profile"), self._apply_profile),
            (tr("gui.action.install_zip"), self._choose_install_zip),
            (tr("gui.action.install_dir"), self._choose_install_directory),
            (tr("gui.action.rollback_install"), self._rollback_install),
            (tr("gui.action.verify"), self._verify_selected),
        ):
            ttk.Button(button_bar, text=text, command=command).pack(
                side="left", padx=(0, 6)
            )
        self.management_tree.bind("<Double-1>", self._show_management_detail)

        history_frame, self.history_tree = self._tree_tab(
            self.notebook,
            tr("gui.tab.history"),
            {
                "time": tr("gui.head.time"), "id": tr("gui.head.id"),
                "label": tr("gui.head.label"),
                "mode": tr("gui.head.mode"), "addons": tr("gui.head.addons"),
                "issues": tr("gui.head.issues"),
                "conflicts": tr("gui.head.conflicts"),
                "error": tr("gui.head.error"),
            },
            {
                "time": 175, "id": 220, "label": 160, "mode": 70,
                "addons": 65, "issues": 65, "conflicts": 85, "error": 300,
            },
        )
        history_buttons = ttk.Frame(history_frame, padding=(0, 8, 0, 0))
        history_buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
        for text, command in (
            (tr("gui.action.refresh_history"), self._refresh_history),
            (tr("gui.action.record_snapshot"), self._record_current_snapshot),
            (tr("gui.action.set_baseline"), self._set_selected_baseline),
            (tr("gui.action.compare_baseline"), self._compare_current_baseline),
        ):
            ttk.Button(history_buttons, text=text, command=command).pack(
                side="left", padx=(0, 6)
            )
        self.history_tree.bind("<Double-1>", self._show_selected_detail)

        errors_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(errors_frame, text=tr("gui.tab.scan_errors"))
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
        selected = filedialog.askdirectory(title=tr("gui.prompt.choose_community"))
        if selected:
            self.path_var.set(selected)
            self._refresh_inventory()

    def _community_path(self):
        value = self.path_var.get().strip().strip('"')
        if not value:
            raise ValueError(tr("gui.err.choose_community"))
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(tr("gui.err.not_dir", path=path))
        return path

    def _manager(self):
        return AddonManager(self._community_path(), self.state_dir)

    def _history_store(self):
        return HistoryStore(self._community_path(), self.state_dir)

    def _on_close(self):
        """关闭窗口前确认：后台任务（如安装/回滚）仍在运行时先询问。"""
        if self._busy:
            confirmed = messagebox.askokcancel(
                tr("gui.dialog.close_busy_title"),
                tr("gui.dialog.close_busy_text"),
                parent=self.root,
            )
            if not confirmed:
                return
        self.root.destroy()

    def _on_language_change(self, event=None):
        """头部语言下拉框切换：即时重建界面文案。

        已载入的检测说明是在扫描时生成的语言；切换语言时询问是否
        重新扫描，让说明（message / reason）也切换为新语言。
        """
        code = _lang_code_from_display(self.lang_var.get())
        if code == current_language():
            return
        if self._busy:
            self.lang_var.set(_lang_display_name())
            self.status_var.set(tr("gui.lang.busy"))
            return
        set_language(code)
        self.lang_var.set(_lang_display_name())

        result = self.result
        if result is not None:
            rescan = messagebox.askyesno(
                tr("gui.lang.rescan_title"),
                tr("gui.lang.rescan_text"),
                parent=self.root,
            )
            if rescan:
                path = result.community_path
                mode = result.mode
                self._rebuild_ui(restore_data=False)
                label = (
                    tr("gui.status.scan_full") if mode == "full"
                    else tr("gui.status.scan_quick")
                )
                self._run_async(
                    label,
                    lambda: run_desktop_scan(path, mode, self.state_dir),
                    self._receive_scan,
                )
                return
            self.status_var.set(tr("gui.lang.declined_note"))
        self._rebuild_ui()

    def _rebuild_ui(self, restore_data=True):
        """按当前语言重建静态界面。

        restore_data=True 时用已载入数据重填各页签；
        为 False（即将重新扫描）时只重建界面框架。
        """
        result = self.result
        for child in list(self.root.winfo_children()):
            child.destroy()
        self._detail_by_item.clear()
        self._management_by_item.clear()

        self.root.title(tr("gui.window.title"))
        self._build_header()
        self._build_summary()
        self._build_tabs()
        self._build_status_bar()

        if not restore_data:
            return

        if result is not None:
            # 会重填问题/冲突/异常页签，并异步刷新管理清单
            self._receive_scan(result)
        else:
            has_path = bool(self.path_var.get().strip().strip('"'))
            if self._has_inventory and has_path:
                self._refresh_inventory()
        if self._has_history:
            self._refresh_history()

    def _run_async(self, label, task, on_success):
        if self._busy:
            self.status_var.set(tr("gui.err.task_busy"))
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
            self.status_var.set(tr("gui.err.task_failed"))
            messagebox.showerror(
                tr("gui.dialog.close_busy_title"), localize_text(str(payload)), parent=self.root
            )
            return
        try:
            callback(payload)
        except Exception as error:
            self.status_var.set(tr("gui.err.render_failed"))
            messagebox.showerror(
                tr("gui.dialog.close_busy_title"), localize_text(str(error)), parent=self.root
            )

    def _start_scan(self):
        try:
            path = self._community_path()
        except ValueError as error:
            messagebox.showerror("AeroGuard", localize_text(str(error)), parent=self.root)
            return
        mode = self.mode_var.get()
        label = tr("gui.status.scan_full") if mode == "full" \
            else tr("gui.status.scan_quick")
        self._run_async(
            label,
            lambda: run_desktop_scan(path, mode, self.state_dir),
            self._receive_scan,
        )

    @staticmethod
    def _clear_tree(tree):
        for item in tree.get_children():
            tree.delete(item)

    def _fill_detail_tree(self, tree, rows, tag_fn=None):
        self._clear_tree(tree)
        for item_id in list(self._detail_by_item):
            if item_id.startswith(str(tree)):
                del self._detail_by_item[item_id]
        for index, row in enumerate(rows):
            item_id = f"{tree}-{index}"
            tags = (tag_fn(row["detail"]),) if tag_fn is not None else ()
            tree.insert(
                "", "end", iid=item_id, values=row["values"], tags=tags
            )
            self._detail_by_item[item_id] = row["detail"]

    def _render_tree_rows(self, tree):
        """按当前筛选与排序重新渲染 issue/conflict 树。"""
        rows = getattr(tree, "_ag_all_rows", []) or []
        filter_var = getattr(tree, "_ag_filter_var", None)
        if filter_var is not None:
            rows = filter_rows(rows, filter_var.get())
        sort = getattr(tree, "_ag_sort", None)
        if sort is not None:
            column, reverse = sort
            index = tree._ag_columns.index(column)
            rows = sort_rows(rows, index, reverse)
        tag_fn = (
            issue_row_tag if tree is self.issue_tree
            else (conflict_row_tag if tree is self.conflict_tree else None)
        )
        self._fill_detail_tree(tree, rows, tag_fn=tag_fn)

    def _apply_tree_filter(self, tree):
        self._render_tree_rows(tree)

    def _toggle_tree_sort(self, tree, column):
        current = getattr(tree, "_ag_sort", None)
        if current is not None and current[0] == column:
            tree._ag_sort = (column, not current[1])
        else:
            tree._ag_sort = (column, False)
        self._render_tree_rows(tree)

    def _receive_scan(self, result):
        self.result = result
        summary = diagnostic_summary(result)
        for key, variable in self.summary_vars.items():
            variable.set(summary[key])
        issue_tree = self.issue_tree
        issue_tree._ag_all_rows = issue_table_rows(result.issues)
        issue_tree._ag_sort = None
        self._render_tree_rows(issue_tree)
        conflict_tree = self.conflict_tree
        conflict_tree._ag_all_rows = conflict_table_rows(result.relationships)
        conflict_tree._ag_sort = None
        self._render_tree_rows(conflict_tree)
        self._set_error_text(result.scan_errors)
        self.export_button.configure(state="normal")
        self.status_var.set(tr(
            "gui.status.scan_done",
            addons=summary["addons"], issues=summary["issues"],
            elapsed=summary["elapsed_s"],
        ))
        self._refresh_inventory()

    def _set_error_text(self, errors):
        text = (
            json.dumps(errors, ensure_ascii=False, indent=2)
            if errors else tr("gui.no_scan_errors")
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
        text.insert(
            "1.0",
            json.dumps(
                localize_document(document), ensure_ascii=False, indent=2
            ),
        )
        text.configure(state="disabled")

    def _show_selected_detail(self, event):
        item_id = event.widget.focus()
        detail = self._detail_by_item.get(item_id)
        if detail is not None:
            self._show_json_detail(tr("gui.detail.issue"), detail)

    def _show_management_detail(self, event):
        item_id = event.widget.focus()
        detail = self._management_by_item.get(item_id)
        if detail is not None:
            self._show_json_detail(tr("gui.detail.addon"), detail)

    def _export_json(self):
        if self.result is None:
            return
        filename = filedialog.asksaveasfilename(
            title=tr("gui.export.title"),
            defaultextension=".json",
            filetypes=(
                ("JSON", "*.json"),
                (tr("gui.export.markdown"), "*.md"),
                (tr("gui.export.html"), "*.html"),
                (tr("gui.export.all_files"), "*.*"),
            ),
        )
        if not filename:
            return
        document = self.result.report_document()
        suffix = Path(filename).suffix.casefold()
        if suffix in {".md", ".markdown"}:
            output = Path(filename)
            output.write_text(export_markdown(document), encoding="utf-8")
        elif suffix in {".html", ".htm"}:
            output = Path(filename)
            output.write_text(export_html(document), encoding="utf-8")
        else:
            output = save_json_report(document, filename)
        self.status_var.set(tr("gui.status.report_saved", path=output))

    def _refresh_inventory(self):
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            self.status_var.set(localize_text(str(error)))
            return
        self._run_async(tr("gui.status.refreshing_inventory"), manager.inventory, self._receive_inventory)

    def _receive_inventory(self, inventory):
        self._has_inventory = True
        self._clear_tree(self.management_tree)
        self._management_by_item.clear()
        rows = management_table_rows(inventory)
        for index, row in enumerate(rows):
            item_id = f"management-{index}"
            self.management_tree.insert("", "end", iid=item_id, values=row["values"])
            self._management_by_item[item_id] = row["detail"]
        summary = inventory["summary"]
        self.status_var.set(tr(
            "gui.status.inventory_done",
            enabled=summary["enabled"], disabled=summary["disabled"],
            quarantined=summary["quarantined"],
            invalid=summary["invalid_entries"],
        ))

    def _selected_management_record(self):
        selection = self.management_tree.selection()
        if not selection:
            raise ManagementError(tr("gui.err.select_management_row"))
        return self._management_by_item[selection[0]]

    def _manage_selected(self, action):
        try:
            record = self._selected_management_record()
            manager = self._manager()
            status = record["status"]
            if action == "enable" and status != "disabled":
                raise ManagementError(tr("gui.err.only_disabled_enable"))
            if action == "disable" and status != "enabled":
                raise ManagementError(tr("gui.err.only_enabled_disable"))
            if action == "restore" and status != "quarantined":
                raise ManagementError(tr("gui.err.only_quarantined_restore"))
            if action == "quarantine" and status == "quarantined":
                raise ManagementError(tr("gui.err.already_quarantined"))
            reason = "GUI manual quarantine"
            if action == "quarantine":
                reason = simpledialog.askstring(
                    tr("gui.dialog.quarantine_reason_title"),
                    tr("gui.dialog.quarantine_reason_prompt"),
                    parent=self.root,
                    initialvalue=tr("gui.dialog.quarantine_initial"),
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
                tr("gui.status.operation_prefix",
                   action=action, package=record["package"]),
                operations[action],
                self._receive_management_action,
            )
        except (ValueError, ManagementError) as error:
            messagebox.showerror(
                tr("gui.dialog.close_busy_title"), localize_text(str(error)), parent=self.root
            )

    def _receive_management_action(self, transaction):
        warnings = transaction.get("dependency_warnings", [])
        suffix = ""
        if warnings:
            suffix = tr("gui.status.dependency_warning_suffix",
                        n=len(warnings))
        self.status_var.set(tr(
            "gui.status.operation_done", tid=transaction["id"], suffix=suffix
        ))
        if warnings:
            self._show_json_detail(
                tr("gui.detail.dependency_warnings"), warnings
            )
        self.root.after(100, self._refresh_inventory)

    def _refresh_history(self):
        try:
            store = self._history_store()
        except (ValueError, HistoryError) as error:
            self.status_var.set(localize_text(str(error)))
            return
        self._run_async(
            tr("gui.status.reading_history"),
            lambda: store.list_snapshots(limit=100),
            self._receive_history,
        )

    def _receive_history(self, snapshots):
        self._has_history = True
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
        self.status_var.set(
            tr("gui.status.history_count", n=len(snapshots))
        )

    def _current_report_for_history(self):
        if self.result is None:
            raise HistoryError(tr("gui.err.need_scan_first"))
        if self.result.community_path != self._community_path():
            raise HistoryError(tr("gui.err.path_changed"))
        return self.result.report_document()

    def _record_current_snapshot(self):
        try:
            store = self._history_store()
            report = self._current_report_for_history()
        except (ValueError, HistoryError) as error:
            messagebox.showerror("AeroGuard", localize_text(str(error)), parent=self.root)
            return
        label = simpledialog.askstring(
            tr("gui.dialog.record_history"), tr("gui.dialog.label_prompt"),
            parent=self.root,
        )
        if label is None:
            return

        def receive(snapshot):
            self.status_var.set(
                tr("gui.status.snapshot_saved", sid=snapshot["snapshot_id"])
            )
            self.root.after(100, self._refresh_history)

        self._run_async(
            tr("gui.status.record_snapshot"),
            lambda: store.record(report, label=label or None),
            receive,
        )

    def _selected_snapshot(self):
        selection = self.history_tree.selection()
        if not selection:
            raise HistoryError(tr("gui.err.no_snapshot_selected"))
        snapshot = self._detail_by_item.get(selection[0])
        if not snapshot or snapshot.get("error"):
            raise HistoryError(tr("gui.err.snapshot_unavailable"))
        return snapshot

    def _set_selected_baseline(self):
        try:
            snapshot = self._selected_snapshot()
            store = self._history_store()
        except (ValueError, HistoryError) as error:
            messagebox.showerror(
                tr("gui.dialog.close_busy_title"), localize_text(str(error)), parent=self.root
            )
            return
        name = simpledialog.askstring(
            tr("gui.dialog.set_baseline"), tr("gui.dialog.baseline_name"),
            parent=self.root,
        )
        if not name:
            return
        self._run_async(
            tr("gui.status.set_baseline_running", name=name),
            lambda: store.set_baseline(name, snapshot["snapshot_id"]),
            lambda result: self.status_var.set(
                tr("gui.status.baseline_saved", name=result["baseline_name"])
            ),
        )

    def _compare_current_baseline(self):
        try:
            store = self._history_store()
            report = self._current_report_for_history()
        except (ValueError, HistoryError) as error:
            messagebox.showerror(
                tr("gui.dialog.close_busy_title"), localize_text(str(error)), parent=self.root
            )
            return
        name = simpledialog.askstring(
            tr("gui.dialog.compare_baseline"), tr("gui.dialog.baseline_name2"),
            parent=self.root,
        )
        if not name:
            return

        def receive(comparison):
            changes = comparison["summary"]["total_changes"]
            warnings = comparison["summary"]["compatibility_warnings"]
            self.status_var.set(tr(
                "gui.status.baseline_compare_done",
                changes=changes, warnings=warnings,
            ))
            self._show_json_detail(
                tr("gui.dialog.compare_baseline") + f" — {name}",
                comparison,
            )

        self._run_async(
            tr("gui.status.compare_running", name=name),
            lambda: store.compare(name, report),
            receive,
        )

    def _save_profile(self):
        name = simpledialog.askstring(
            tr("gui.dialog.save_profile"), tr("gui.dialog.profile_name"),
            parent=self.root,
        )
        if not name:
            return
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror(
                tr("gui.dialog.close_busy_title"), localize_text(str(error)), parent=self.root
            )
            return
        self._run_async(
            tr("gui.status.save_profile_running", name=name),
            lambda: manager.save_profile(name),
            lambda result: self.status_var.set(
                tr("gui.status.profile_saved", path=result["profile_path"])
            ),
        )

    def _apply_profile(self):
        name = simpledialog.askstring(
            tr("gui.dialog.apply_profile"), tr("gui.dialog.profile_name2"),
            parent=self.root,
        )
        if not name:
            return
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror(
                tr("gui.dialog.close_busy_title"), localize_text(str(error)), parent=self.root
            )
            return

        def receive_plan(plan):
            move_count = len(plan["moves"])
            warning_count = len(plan.get("warnings", [])) + len(
                plan.get("dependency_warnings", [])
            )
            if move_count == 0:
                self.status_var.set(
                    tr("gui.status.profile_applied_already", name=name)
                )
                return
            accepted = messagebox.askyesno(
                tr("gui.dialog.apply_profile"),
                tr("gui.dialog.apply_profile_confirm",
                   name=name, moves=move_count, warnings=warning_count),
                parent=self.root,
            )
            if accepted:
                self._run_async(
                    tr("gui.status.apply_profile_running", name=name),
                    lambda: manager.apply_profile(name),
                    self._receive_management_action,
                )

        self._run_async(
            tr("gui.status.profile_dry_run", name=name),
            lambda: manager.apply_profile(name, dry_run=True),
            receive_plan,
        )

    def _choose_install_zip(self):
        source = filedialog.askopenfilename(
            title=tr("gui.dialog.choose_zip"),
            filetypes=(("ZIP", "*.zip"), (tr("gui.export.all_files"), "*.*")),
        )
        if source:
            self._inspect_then_offer_install(source)

    def _choose_install_directory(self):
        source = filedialog.askdirectory(title=tr("gui.dialog.choose_dir"))
        if source:
            self._inspect_then_offer_install(source)

    def _inspect_then_offer_install(self, source):
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror("AeroGuard", localize_text(str(error)), parent=self.root)
            return

        def receive_inspection(inspection):
            summary = inspection.summary()
            if not inspection.can_install:
                self._show_json_detail(
                    tr("gui.dialog.install_check_title"),
                    inspection.as_dict(),
                )
                self.status_var.set(tr("gui.dialog.inspect_not_passed"))
                return
            package_names = ", ".join(
                item["folder_name"] for item in inspection.packages
            )
            allow_executables = inspection.requires_executable_override
            executable_note = ""
            if allow_executables:
                executable_note = tr(
                    "gui.dialog.executable_note",
                    n=summary["executable_files"],
                )
            accepted = messagebox.askyesno(
                tr("gui.dialog.install_check_title"),
                tr("gui.dialog.install_done_offer",
                   packages=package_names,
                   issues=summary["issues"], note=executable_note),
                parent=self.root,
            )
            if accepted:
                self._run_async(
                    tr("gui.status.install_running"),
                    lambda: manager.install(source, allow_executables),
                    self._receive_install,
                )

        self._run_async(
            tr("gui.status.inspect_running"),
            lambda: manager.inspect_install_source(source),
            receive_inspection,
        )

    def _receive_install(self, result):
        transaction = result["transaction"]
        self.status_var.set(tr(
            "gui.status.install_done", tid=transaction["id"]
        ))
        self._show_json_detail(
            tr("gui.detail.install_transaction"), transaction
        )
        self.root.after(100, self._refresh_inventory)

    def _rollback_install(self):
        transaction_id = simpledialog.askstring(
            tr("gui.dialog.rollback_title"), tr("gui.dialog.rollback_prompt"),
            parent=self.root,
        )
        if not transaction_id:
            return
        try:
            manager = self._manager()
        except (ValueError, ManagementError) as error:
            messagebox.showerror("AeroGuard", localize_text(str(error)), parent=self.root)
            return
        self._run_async(
            tr("gui.status.rollback_running", tid=transaction_id),
            lambda: manager.rollback_install(transaction_id),
            self._receive_management_action,
        )

    def _verify_selected(self):
        """只读校验管理页签中选中的单个插件。"""
        try:
            record = self._selected_management_record()
            community = self._community_path()
        except (ValueError, ManagementError) as error:
            messagebox.showerror(
                "AeroGuard", localize_text(str(error)), parent=self.root
            )
            return
        package = record["package"]

        def receive(result):
            summary = result["summary"]
            self.status_var.set(tr(
                "gui.status.verify_done",
                package=result["package"],
                error=summary["error"],
                warning=summary["warning"],
                info=summary["info"],
            ))
            self._show_json_detail(tr("gui.detail.verify"), result)

        self._run_async(
            tr("gui.status.verifying", package=package),
            lambda: verify_package(community, package, self.state_dir),
            receive,
        )


def _preset_language(argv):
    """在解析参数前，先根据 --lang 预设语言，使 --help 也使用该语言。"""
    arguments = sys.argv[1:] if argv is None else list(argv)
    for index, argument in enumerate(arguments):
        if argument == "--lang" and index + 1 < len(arguments):
            set_language(arguments[index + 1])
            return
        if argument.startswith("--lang="):
            set_language(argument.split("=", 1)[1])
            return


def parse_args(argv=None):
    _preset_language(argv)
    parser = argparse.ArgumentParser(
        prog="aeroguard-gui",
        description=tr("help.gui.description"),
    )
    parser.add_argument("community_path", nargs="?", default="")
    parser.add_argument("--mode", choices=("quick", "full"), default="quick")
    parser.add_argument(
        "--lang", choices=("zh", "en", "zh-CN", "en-US"),
        help=tr("help.gui.lang"),
    )
    parser.add_argument("--state-dir")
    return parser.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    args = parse_args(argv)
    set_language(args.lang)
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
