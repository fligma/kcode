from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Any

from PyQt6 import QtCore, QtWidgets


BASE_DIR = Path(__file__).resolve().parent
PKG_DIR = BASE_DIR / "packages"
CFG_FILE = BASE_DIR / "kcodehelper.ini"
JSON_FILE = BASE_DIR / "kcodehelper.json"


def _safe_read(path: Path, encoding: str = "utf-8") -> str:
    return path.read_text(encoding=encoding)


def _safe_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.write_text(text, encoding=encoding)


def _fallback_pget(kind: str, path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    if kind == "f":
        return [i.name for i in p.iterdir() if i.is_file()]
    if kind == "d":
        return [i.name for i in p.iterdir() if i.is_dir()]
    if kind == "r":
        return [i.name for i in p.iterdir() if i.is_dir() and os.access(i, os.R_OK)]
    if kind == "w":
        return [i.name for i in p.iterdir() if i.is_dir() and os.access(i, os.W_OK)]
    if kind == "e":
        return [i.name for i in p.iterdir() if i.is_file() and os.access(i, os.X_OK)]
    return []


def _fallback_pcheck(kind: str, path: str) -> bool:
    p = Path(path)
    if kind == "d":
        return p.is_dir()
    if kind == "f":
        return p.is_file()
    if kind == "r":
        return os.access(path, os.R_OK)
    if kind == "w":
        return os.access(path, os.W_OK)
    if kind == "x":
        return os.access(path, os.X_OK)
    return False


def _fallback_pfile(op: str, p1: str, p2: str = "") -> Any:
    if op == "r":
        return _safe_read(Path(p1))
    if op == "w":
        _safe_write(Path(p1), p2)
        return None
    if op == "mv":
        Path(p1).rename(p2)
        return None
    if op == "cp":
        src = Path(p1)
        dst = Path(p2)
        if src.is_dir():
            raise IsADirectoryError(f"cp fallback does not copy directories: {p1}")
        dst.write_bytes(src.read_bytes())
        return None
    raise ValueError(f"Unsupported op: {op}")


def load_pkg_runtime() -> dict[str, Any]:
    ns: dict[str, Any] = {
        "__name__": "__pkg_runtime__",
        "__file__": str(BASE_DIR / "_pkg_runtime.py"),
        "os": os,
        "sys": sys,
        "json": json,
        "traceback": traceback,
        "datetime": __import__("datetime"),
    }

    if not PKG_DIR.exists():
        return ns

    for pkg_path in sorted(PKG_DIR.glob("*.pkg")):
        try:
            exec(pkg_path.read_text(encoding="utf-8"), ns, ns)
        except Exception as exc:
            print(f"[LOAD ERROR] {pkg_path.name}: {exc}")
    return ns


PKG_NS = load_pkg_runtime()

pget = PKG_NS.get("pget", _fallback_pget)
pcheck = PKG_NS.get("pcheck", _fallback_pcheck)
pfile = PKG_NS.get("pfile", _fallback_pfile)
lprint = PKG_NS.get("lprint", lambda m, t="i": print(m))
cfgio = PKG_NS.get("cfgio")
jio = PKG_NS.get("jio")
kreq = PKG_NS.get("kreq")
execute = PKG_NS.get("execute")
sysinfo = PKG_NS.get("sysinfo")
kzip = PKG_NS.get("kzip")
KError = PKG_NS.get("KError", Exception)
kerr_catch = PKG_NS.get("kerr_catch")
kerr_assert_k = PKG_NS.get("kerr_assert_k")
kqt = PKG_NS.get("kqt")


def read_pkg_text(pkg_name: str) -> str:
    pkg_path = PKG_DIR / pkg_name
    try:
        return str(pfile("r", str(pkg_path)))
    except Exception:
        return _safe_read(pkg_path)


def list_packages() -> list[str]:
    if not PKG_DIR.exists():
        PKG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        files = pget("f", str(PKG_DIR))
        return sorted([f for f in files if f.endswith(".pkg")])
    except Exception:
        return sorted([p.name for p in PKG_DIR.glob("*.pkg")])


def build_script(selected: list[str], dest_path: Path, template_path: Path) -> str:
    template_lines = (
        template_path.read_text(encoding="utf-8").splitlines()
        if template_path.exists()
        else [
            "# IMPORTS",
            "",
            "# marking",
            "",
            "# __pkg__",
            "",
            "# __main__",
        ]
    )

    all_imports: set[str] = set()
    slots: dict[str, list[str]] = {"__pkg__": [], "__main__": []}

    for p_name in selected:
        content = read_pkg_text(p_name)
        lines = content.splitlines()
        pkg_code: list[str] = []
        clean_header = p_name
        target_slot = "__pkg__"

        for line in lines:
            if line.startswith("import "):
                for part in line.split(";"):
                    part = part.strip()
                    if part.startswith("import "):
                        for mod in part.replace("import ", "").split(","):
                            mod = mod.strip()
                            if mod:
                                all_imports.add(mod)
            elif "__pkg__" in line or "__main__" in line:
                target_slot = "__pkg__" if "__pkg__" in line else "__main__"
                clean_header = line.replace("__pkg__", "").replace("__main__", "").strip()
            else:
                pkg_code.append(line)

        formatted_code = "\n".join(pkg_code)
        if target_slot == "__main__":
            formatted_code = "\n".join([f"    {l}" if l.strip() else l for l in pkg_code])

        block = f"{clean_header}\n{formatted_code}\n#"
        slots[target_slot].append(block)

    final_output: list[str] = []
    marking = f"# flyonisis ({date.today().year})"

    for line in template_lines:
        if "# IMPORTS" in line:
            final_output.append(f"import {', '.join(sorted(all_imports))}" if all_imports else "# No imports")
        elif "# marking" in line:
            final_output.append(marking)
        elif "# __pkg__" in line:
            final_output.extend(slots["__pkg__"])
        elif "# __main__" in line:
            final_output.extend(slots["__main__"])
        else:
            final_output.append(line)

    output_text = "\n".join(final_output)
    dest_path.write_text(output_text, encoding="utf-8")
    return output_text


class BuilderWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("K-Code Project Builder")
        self.resize(1200, 780)
        self._build_ui()
        self._load_prefs()
        self.refresh_packages()
        self._log_startup()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel("<h1>K-CODE SCRIPT BUILDER</h1>")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Build scripts from .pkg blocks, preview output, and use the helper packages from your packages/ folder."
        )
        subtitle.setWordWrap(True)
        subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)

        path_row = QtWidgets.QHBoxLayout()
        self.output_dir = QtWidgets.QLineEdit(str(BASE_DIR))
        self.output_dir.setPlaceholderText("Output folder")
        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self.choose_output_dir)
        path_row.addWidget(self.output_dir, 1)
        path_row.addWidget(browse_btn)
        left_layout.addLayout(path_row)

        self.output_name = QtWidgets.QLineEdit("build.py")
        self.output_name.setPlaceholderText("Output filename")
        left_layout.addWidget(self.output_name)

        self.filter_box = QtWidgets.QLineEdit()
        self.filter_box.setPlaceholderText("Filter packages...")
        self.filter_box.textChanged.connect(self.filter_packages)
        left_layout.addWidget(self.filter_box)

        pkg_btn_row = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.select_all_btn = QtWidgets.QPushButton("Select All")
        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.refresh_btn.clicked.connect(self.refresh_packages)
        self.select_all_btn.clicked.connect(self.select_all)
        self.clear_btn.clicked.connect(self.clear_all)
        pkg_btn_row.addWidget(self.refresh_btn)
        pkg_btn_row.addWidget(self.select_all_btn)
        pkg_btn_row.addWidget(self.clear_btn)
        left_layout.addLayout(pkg_btn_row)

        self.pkg_list = QtWidgets.QListWidget()
        self.pkg_list.itemChanged.connect(self.update_preview)
        left_layout.addWidget(self.pkg_list, 1)

        build_row = QtWidgets.QHBoxLayout()
        self.build_btn = QtWidgets.QPushButton("Build Script")
        self.preview_btn = QtWidgets.QPushButton("Preview")
        self.save_btn = QtWidgets.QPushButton("Save Prefs")
        self.load_btn = QtWidgets.QPushButton("Load Prefs")
        self.build_btn.clicked.connect(self.build_clicked)
        self.preview_btn.clicked.connect(self.update_preview)
        self.save_btn.clicked.connect(self.save_prefs)
        self.load_btn.clicked.connect(self.load_prefs_from_disk)
        for b in (self.build_btn, self.preview_btn, self.save_btn, self.load_btn):
            build_row.addWidget(b)
        left_layout.addLayout(build_row)

        tools_box = QtWidgets.QGroupBox("Package Tools")
        tools_layout = QtWidgets.QGridLayout(tools_box)

        self.cmd_input = QtWidgets.QLineEdit()
        self.cmd_input.setPlaceholderText("shell command for execute()")
        self.run_cmd_btn = QtWidgets.QPushButton("Run Command")
        self.run_cmd_btn.clicked.connect(self.run_command)

        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("URL for knet.kreq('g', ...)")
        self.fetch_btn = QtWidgets.QPushButton("Fetch URL")
        self.fetch_btn.clicked.connect(self.fetch_url)

        self.json_path = QtWidgets.QLineEdit(str(JSON_FILE))
        self.json_path.setPlaceholderText("JSON path")
        self.save_json_btn = QtWidgets.QPushButton("Save JSON")
        self.save_json_btn.clicked.connect(self.save_json_state)
        self.load_json_btn = QtWidgets.QPushButton("Load JSON")
        self.load_json_btn.clicked.connect(self.load_json_state)

        self.zip_btn = QtWidgets.QPushButton("Zip Output")
        self.zip_btn.clicked.connect(self.zip_output)
        self.sysinfo_btn = QtWidgets.QPushButton("Sysinfo")
        self.sysinfo_btn.clicked.connect(self.show_sysinfo)
        self.show_pkg_btn = QtWidgets.QPushButton("Show Selected Text")
        self.show_pkg_btn.clicked.connect(self.show_selected_text)

        tools_layout.addWidget(self.cmd_input, 0, 0)
        tools_layout.addWidget(self.run_cmd_btn, 0, 1)
        tools_layout.addWidget(self.url_input, 1, 0)
        tools_layout.addWidget(self.fetch_btn, 1, 1)
        tools_layout.addWidget(self.json_path, 2, 0)
        tools_layout.addWidget(self.save_json_btn, 2, 1)
        tools_layout.addWidget(self.load_json_btn, 2, 2)
        tools_layout.addWidget(self.zip_btn, 3, 0)
        tools_layout.addWidget(self.sysinfo_btn, 3, 1)
        tools_layout.addWidget(self.show_pkg_btn, 3, 2)

        left_layout.addWidget(tools_box)

        splitter.addWidget(left_panel)

        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)

        self.preview = QtWidgets.QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        self.preview.setPlaceholderText("Selected package content and build preview appear here.")
        right_layout.addWidget(self.preview, 1)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(220)
        self.log.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        right_layout.addWidget(self.log)

        splitter.addWidget(right_panel)
        splitter.setSizes([420, 780])

        self.setStyleSheet(
            """
            QWidget { background: #1b1b1b; color: #d8ffd8; font-family: Consolas, 'Courier New', monospace; }
            QLineEdit, QTextEdit, QListWidget { background: #101010; border: 1px solid #3a5; padding: 6px; selection-background-color: #285; }
            QPushButton { background: #203020; border: 1px solid #3a5; padding: 7px 10px; }
            QPushButton:hover { background: #284028; }
            QGroupBox { border: 1px solid #3a5; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            """
        )

    def _log(self, msg: str, kind: str = "i") -> None:
        try:
            lprint(msg, kind)
        except Exception:
            pass
        self.log.append(msg)

    def _selected_packages(self) -> list[str]:
        selected: list[str] = []
        for row in range(self.pkg_list.count()):
            item = self.pkg_list.item(row)
            if item.isHidden():
                continue
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                selected.append(item.text())
        return selected

    def refresh_packages(self) -> None:
        self.pkg_list.blockSignals(True)
        self.pkg_list.clear()

        if not PKG_DIR.exists():
            PKG_DIR.mkdir(parents=True, exist_ok=True)

        packages = list_packages()
        for pkg in packages:
            item = QtWidgets.QListWidgetItem(pkg)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.pkg_list.addItem(item)

        self.pkg_list.blockSignals(False)
        self._log(f"Loaded {len(packages)} packages from {PKG_DIR}")
        self.update_preview()

    def filter_packages(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.pkg_list.count()):
            item = self.pkg_list.item(row)
            item.setHidden(bool(needle and needle not in item.text().lower()))
        self.update_preview()

    def select_all(self) -> None:
        for row in range(self.pkg_list.count()):
            item = self.pkg_list.item(row)
            if not item.isHidden():
                item.setCheckState(QtCore.Qt.CheckState.Checked)
        self.update_preview()

    def clear_all(self) -> None:
        for row in range(self.pkg_list.count()):
            self.pkg_list.item(row).setCheckState(QtCore.Qt.CheckState.Unchecked)
        self.update_preview()

    def choose_output_dir(self) -> None:
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose output folder", self.output_dir.text() or str(BASE_DIR)
        )
        if chosen:
            self.output_dir.setText(chosen)

    def update_preview(self) -> None:
        selected = self._selected_packages()
        if not selected:
            self.preview.setPlainText("Select one or more packages to preview them here.")
            return

        chunks = []
        for name in selected:
            try:
                chunks.append(f"### {name}\n{read_pkg_text(name)}")
            except Exception as exc:
                chunks.append(f"### {name}\n[ERROR] {exc}")
        self.preview.setPlainText("\n\n".join(chunks))

    def build_clicked(self) -> None:
        try:
            out_dir = Path(self.output_dir.text().strip() or str(BASE_DIR))
            out_name = self.output_name.text().strip() or "build.py"
            if not out_name.endswith(".py"):
                out_name += ".py"

            if not out_dir.exists():
                raise KError(f"Output folder does not exist: {out_dir}")

            selected = self._selected_packages()
            if callable(kerr_assert_k):
                kerr_assert_k(bool(selected), "Select at least one package first.")
            elif not selected:
                raise KError("Select at least one package first.")

            template_path = BASE_DIR / "fill.template"
            dest = out_dir / out_name
            output_text = build_script(selected, dest, template_path)

            self.preview.setPlainText(output_text)
            self._log(f"Built script: {dest}", "s")

            self._save_prefs()
            self._save_json()
        except Exception as exc:
            if callable(kerr_catch):
                try:
                    kerr_catch(exc, "build_clicked")
                except Exception:
                    pass
            self._log(f"Build failed: {exc}", "e")
            QtWidgets.QMessageBox.critical(self, "Build Failed", str(exc))

    def show_selected_text(self) -> None:
        selected = self._selected_packages()
        if not selected:
            QtWidgets.QMessageBox.information(self, "Packages", "No packages selected.")
            return
        text = []
        for name in selected:
            try:
                text.append(f"--- {name} ---\n{read_pkg_text(name)}")
            except Exception as exc:
                text.append(f"--- {name} ---\n[ERROR] {exc}")
        self.preview.setPlainText("\n\n".join(text))

    def run_command(self) -> None:
        cmd = self.cmd_input.text().strip()
        if not cmd:
            QtWidgets.QMessageBox.information(self, "Command", "Enter a shell command first.")
            return
        try:
            if callable(execute):
                out = execute(cmd, v=False)
            else:
                out = os.popen(cmd).read()
            self._log(out or "(no output)", "i")
        except Exception as exc:
            self._log(f"Command failed: {exc}", "e")

    def fetch_url(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.information(self, "Fetch URL", "Enter a URL first.")
            return
        try:
            if callable(kreq):
                result = kreq("g", url)
            else:
                result = "knet.kreq not available"
            text = str(result)
            self.preview.setPlainText(text[:20000])
            self._log(f"Fetched: {url}", "s")
        except Exception as exc:
            self._log(f"Fetch failed: {exc}", "e")

    def zip_output(self) -> None:
        try:
            out_dir = Path(self.output_dir.text().strip() or str(BASE_DIR))
            out_name = self.output_name.text().strip() or "build.py"
            if not out_name.endswith(".py"):
                out_name += ".py"
            src = out_dir / out_name
            if not src.exists():
                raise KError(f"Output file does not exist: {src}")
            dest = str(src.with_suffix(".zip"))
            if callable(kzip):
                msg = kzip("z", str(src), dest)
            else:
                import zipfile
                with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(src, arcname=src.name)
                msg = f"Zipped to {dest}"
            self._log(str(msg), "s")
            QtWidgets.QMessageBox.information(self, "Zip", str(msg))
        except Exception as exc:
            self._log(f"Zip failed: {exc}", "e")
            QtWidgets.QMessageBox.critical(self, "Zip Failed", str(exc))

    def show_sysinfo(self) -> None:
        try:
            info = sysinfo() if callable(sysinfo) else {"os": sys.platform, "pid": os.getpid()}
            self.preview.setPlainText(json.dumps(info, indent=2, default=str))
            self._log("Sysinfo collected.", "i")
        except Exception as exc:
            self._log(f"Sysinfo failed: {exc}", "e")

    def _prefs_payload(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir.text().strip(),
            "output_name": self.output_name.text().strip(),
            "selected_packages": self._selected_packages(),
            "filter_text": self.filter_box.text().strip(),
            "cmd_input": self.cmd_input.text().strip(),
            "url_input": self.url_input.text().strip(),
            "json_path": self.json_path.text().strip(),
        }

    def _save_prefs(self) -> None:
        payload = self._prefs_payload()
        if callable(cfgio):
            try:
                cfg_path = str(CFG_FILE)
                for key, val in payload.items():
                    cfgio("w", cfg_path, "ui", key, json.dumps(val))
            except Exception as exc:
                self._log(f"cfg save failed: {exc}", "e")

    def save_prefs(self) -> None:
        self._save_prefs()
        self._save_json()
        self._log("Preferences saved.", "s")

    def _save_json(self) -> None:
        payload = self._prefs_payload()
        json_path = Path(self.json_path.text().strip() or str(JSON_FILE))
        try:
            if callable(jio):
                jio("w", str(json_path), payload)
            else:
                _safe_write(json_path, json.dumps(payload, indent=4))
        except Exception as exc:
            self._log(f"JSON save failed: {exc}", "e")

    def save_json_state(self) -> None:
        self._save_json()
        self._log("JSON saved.", "s")

    def load_json_state(self) -> None:
        try:
            json_path = Path(self.json_path.text().strip() or str(JSON_FILE))
            if not json_path.exists():
                raise FileNotFoundError(json_path)
            if callable(jio):
                loaded = jio("r", str(json_path))
            else:
                loaded = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._apply_state(loaded)
            self._log("JSON loaded.", "s")
        except Exception as exc:
            self._log(f"JSON load failed: {exc}", "e")

    def load_prefs_from_disk(self) -> None:
        self._load_prefs()
        self._log("Preferences loaded.", "s")

    def _apply_state(self, data: dict[str, Any]) -> None:
        if data.get("output_dir"):
            self.output_dir.setText(str(data["output_dir"]))
        if data.get("output_name"):
            self.output_name.setText(str(data["output_name"]))
        if data.get("filter_text"):
            self.filter_box.setText(str(data["filter_text"]))
        if data.get("cmd_input"):
            self.cmd_input.setText(str(data["cmd_input"]))
        if data.get("url_input"):
            self.url_input.setText(str(data["url_input"]))
        if data.get("json_path"):
            self.json_path.setText(str(data["json_path"]))

        selected = set(data.get("selected_packages", []) or [])
        for row in range(self.pkg_list.count()):
            item = self.pkg_list.item(row)
            item.setCheckState(
                QtCore.Qt.CheckState.Checked
                if item.text() in selected
                else QtCore.Qt.CheckState.Unchecked
            )

    def _load_prefs(self) -> None:
        try:
            data: dict[str, Any] = {}

            if callable(jio) and JSON_FILE.exists():
                loaded = jio("r", str(JSON_FILE))
                if isinstance(loaded, dict):
                    data.update(loaded)

            if callable(cfgio) and CFG_FILE.exists():
                for key in (
                    "output_dir",
                    "output_name",
                    "selected_packages",
                    "filter_text",
                    "cmd_input",
                    "url_input",
                    "json_path",
                ):
                    raw = cfgio("r", str(CFG_FILE), "ui", key)
                    if raw not in (None, ""):
                        try:
                            data[key] = json.loads(raw)
                        except Exception:
                            data[key] = raw

            self._apply_state(data)
        except Exception as exc:
            self._log(f"Load prefs failed: {exc}", "e")

    def _log_startup(self) -> None:
        self._log(f"Builder ready. Packages folder: {PKG_DIR}")
        enabled = [
            k
            for k in (
                "kqt",
                "pget",
                "pcheck",
                "pfile",
                "lprint",
                "cfgio",
                "jio",
                "kreq",
                "execute",
                "sysinfo",
                "kzip",
            )
            if callable(globals().get(k, None))
        ]
        self._log(f"Loaded helpers: {', '.join(enabled)}")


def main() -> int:
    if callable(kqt):
        try:
            kqt("i")
        except Exception:
            pass

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = BuilderWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())