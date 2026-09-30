"""Build and smoke-test a self-contained platform bundle."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "lakeview",
        "--collect-all",
        "duckdb",
        "--collect-all",
        "pyarrow",
        "--collect-all",
        "rich",
        "--collect-all",
        "typer",
        "--collect-all",
        "psutil",
        "lakeview/__main__.py",
    ],
    check=True,
)
binary = Path("dist/lakeview") / ("lakeview.exe" if sys.platform == "win32" else "lakeview")
subprocess.run([str(binary.resolve()), "--version"], check=True)
subprocess.run(
    [str(binary.resolve()), "query", "SELECT 42 answer", "--format", "jsonl"], check=True
)
Path("release-assets").mkdir(exist_ok=True)
name = f"release-assets/lakeview-{platform.system()}-{platform.machine()}"
shutil.make_archive(name, "zip" if sys.platform == "win32" else "gztar", "dist", "lakeview")
