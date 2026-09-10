"""AeroGuard 单文件启动器：GUI 与三个 CLI 合一。

双击（无参数）→ 打开桌面界面（自动隐藏自身控制台窗口）；
带子命令 → 对应 CLI：

    AeroGuard.exe                    桌面界面
    AeroGuard.exe scan <Community> --mode full --json ...
    AeroGuard.exe manage <Community> <子命令> ...
    AeroGuard.exe history <Community> <子命令> ...

也可以分别执行对应的 Python 模块（python main.py / manage.py /
history_cli.py），行为一致。
"""

import sys

import gui
import history_cli
import main as scan_cli
import manage
from i18n import tr


#: 第一参数到目标模块的映射（None 表示缺省 = GUI）
COMMAND_TARGETS = {
    "gui": "gui",
    "app": "gui",
    "scan": "scan",
    "manage": "manage",
    "history": "history",
}

USAGE = """\
AeroGuard —— MSFS 插件诊断与管理（单文件版）

用法：
  AeroGuard.exe                        启动桌面界面（无参数，双击）
  AeroGuard.exe gui                    同上
  AeroGuard.exe scan <Community> [--mode quick|full] [--json] [--no-relationships]
  AeroGuard.exe manage <Community> <inventory|versions|disable|enable|
                      quarantine|restore|profile-save|profile-apply|
                      check|install|rollback|note-list|note-add|note-remove> ...
  AeroGuard.exe history <Community> <record|list|baseline-set|compare> ...

提示：也可以直接运行 python main.py / manage.py / history_cli.py。
"""


def _hide_own_console_if_sole():
    """双击启动时隐藏仅属于本进程的控制台窗口。

    仅当当前控制台只属于本进程（GetConsoleProcessList == 1）时才隐藏，
    因此从 cmd / PowerShell 启动时不会影响调用方终端。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        process_list = (ctypes.c_uint * 4)()
        count = kernel32.GetConsoleProcessList(process_list, 4)
        if count <= 1:
            kernel32.FreeConsole()
    except Exception:
        # 隐藏失败不影响功能，GUI 仍可打开。
        pass


def select_command(argv):
    """解析 argv，返回 (target, remainder)。

    target: "gui" | "scan" | "manage" | "history"
    remainder: 交给目标模块的剩余参数（不含命令本身）
    """
    rest = list(argv or [])
    if not rest:
        return "gui", []

    head = rest[0].casefold()

    if head in {"-h", "--help", "help"}:
        return "help", []

    target = COMMAND_TARGETS.get(head)
    if target == "gui":
        return "gui", []
    if target is not None:
        return target, rest[1:]
    return "gui", rest


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    target, remainder = select_command(argv)

    if target == "help":
        print(tr("launcher.usage"))
        return 0

    if target == "gui":
        _hide_own_console_if_sole()
        return gui.main(remainder)

    if target == "scan":
        return scan_cli.main(remainder)

    if target == "manage":
        return manage.main(remainder)

    if target == "history":
        return history_cli.main(remainder)

    raise AssertionError(f"未处理的目标：{target}")


if __name__ == "__main__":
    sys.exit(main())
