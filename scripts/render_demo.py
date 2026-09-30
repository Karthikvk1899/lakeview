"""Export real command output as the README terminal illustration."""

from rich.console import Console
from rich.terminal_theme import MONOKAI

from lakeview.core.differ import diff
from lakeview.core.engine import Engine
from lakeview.formatters.terminal import render

console = Console(record=True, width=100, force_terminal=True)
console.print("$ lakeview diff prod.parquet staging.parquet --on id", style="bold cyan")
with Engine() as engine:
    render(diff(engine, "demo/prod.parquet", "demo/staging.parquet", ["id"]), console)
console.save_svg("docs/demo.svg", title="lakeview · local data, visible changes", theme=MONOKAI)
