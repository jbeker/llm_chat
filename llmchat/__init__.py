"""llmchat — a small REPL wrapper around the `llm` library with nicer UX.

Streams the response as live-rendered Markdown so bullets, links, and code
blocks look right; shows a spinner during the first-token latency; auto-loads
tool functions from the standard llm tools directory.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Callable

import llm
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner

CONFIG_DIR = Path(os.path.expanduser("~/.config/io.datasette.llm"))
TOOLS_FILE = CONFIG_DIR / "tools" / "brave_tools.py"
HISTORY_FILE = CONFIG_DIR / "llmchat_history.txt"


def load_tool_functions(path: Path) -> list[Callable[..., Any]]:
    if not path.exists():
        return []
    spec = importlib.util.spec_from_file_location("user_tools", path)
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        getattr(module, name)
        for name in dir(module)
        if not name.startswith("_")
        and callable(getattr(module, name))
        and getattr(getattr(module, name), "__module__", None) == "user_tools"
    ]


def main() -> None:
    console = Console()

    try:
        model = llm.get_model()
    except Exception as exc:
        console.print(f"[red]error loading default model:[/red] {exc}")
        console.print("[dim]set one with `llm models default <id>`[/dim]")
        sys.exit(1)

    tools = load_tool_functions(TOOLS_FILE)
    tools_label = ", ".join(t.__name__ for t in tools) or "none"

    console.rule(f"[bold cyan]llmchat[/bold cyan]")
    console.print(
        f"[dim]model:[/dim] [bold]{model.model_id}[/bold]    "
        f"[dim]tools:[/dim] {tools_label}"
    )
    console.print("[dim]commands: /exit  /new (reset)[/dim]")
    console.print()

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    session: PromptSession[str] = PromptSession(history=FileHistory(str(HISTORY_FILE)))
    conversation = model.conversation()

    while True:
        try:
            user_input = session.prompt("❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            break
        if user_input == "/new":
            conversation = model.conversation()
            console.print("[dim]— conversation reset —[/dim]\n")
            continue

        console.print()

        buffer: list[str] = []
        spinner = Spinner("dots", text="[dim]thinking…[/dim]")

        def _before_tool_call(_tool: Any, tool_call: Any) -> None:
            console.print(
                f"[dim italic]↪ {tool_call.name}({tool_call.arguments})[/dim italic]"
            )

        # Mirrors llm/cli.py:826 — conversation.chain auto-executes tools and
        # threads history; model.chain creates a fresh conversation each call.
        def _run() -> Any:
            if tools:
                return conversation.chain(
                    user_input, tools=tools, before_call=_before_tool_call
                )
            return conversation.prompt(user_input, stream=True)

        try:
            with Live(
                spinner,
                console=console,
                refresh_per_second=12,
                transient=False,
                vertical_overflow="visible",
            ) as live:
                for chunk in _run():
                    if not chunk:
                        continue
                    buffer.append(chunk)
                    live.update(Markdown("".join(buffer)))
        except KeyboardInterrupt:
            console.print("\n[dim]— cancelled —[/dim]\n")
            continue
        except Exception as exc:
            console.print(f"[red]error:[/red] {exc}\n")
            continue

        if not buffer:
            console.print("[dim]— (no text produced) —[/dim]")

        console.print()


if __name__ == "__main__":
    main()
