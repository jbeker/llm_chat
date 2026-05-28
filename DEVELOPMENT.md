# Development state

A handoff doc so a future session can pick up where this one stopped without re-doing the diagnosis.

## Overview

`llmchat` exists because `aichat` (the previous client) cannot complete a tool-call roundtrip against an OpenAI-compatible endpoint — confirmed across v0.28.0, v0.29.0, v0.30.0 with a transparent socat HTTP capture. The whole tool-roundtrip-failure investigation is in the git history of the `llamacpp-macpro` repo (the Ansible setup that drove this work); see commits around the move from `aichat` to `llm`. This project is the replacement REPL.

## What works

- Plain chat: a query without tools streams from `llama-server` and renders as Markdown live in the terminal.
- Tool-using chat: the model emits a tool call, the tool runs, and the model's follow-up summary streams as Markdown in the same `rich.Live` region.
- Spinner during first-token latency.
- `prompt_toolkit` input with persistent history at `~/.config/io.datasette.llm/llmchat_history.txt`.
- Slash commands `/exit`, `/quit`, `/new`.
- Inline tool-call indicators: each invocation prints `↪ name({args})` above the live region in real time, surfacing the model's internal back-and-forth across multi-step chains.
- Auto-loading top-level functions from `~/.config/io.datasette.llm/tools/brave_tools.py` and exposing them as tools to the underlying `llm` model.

## How the tool roundtrip works

The REPL mirrors `simonw/llm`'s own CLI (`llm/cli.py:826`):

- When tools are loaded, the chat call is `conversation.chain(user_input, tools=tools, after_call=_after_tool_call)`. The `Conversation.chain` method (`llm/models.py:468`) auto-executes tool calls, feeds the results back to the model, and threads conversation history across steps.
- The returned `ChainResponse` iterates plain strings via `__iter__` (`llm/models.py:1669`) — `yield from response_item` flattens chunks across every chain step into a single stream, so a single `for chunk in response:` loop drives the live Markdown render for both the pre-tool and post-tool segments.
- The inline tool-call indicator is emitted from a `before_call` callback passed to `conversation.chain(...)`, firing in real time as each tool is invoked (cf. the CLI's `--td` pattern at `llm/cli.py:3959`).

Earlier attempts (preserved here as context for anyone re-investigating):

- `model.chain(..., conversation=conversation)` — silently broken: `Model.chain()` does not accept a `conversation=` kwarg (raises `TypeError`, swallowed by the broad exception handler), and even without that kwarg `Model.chain` constructs a fresh conversation per call and drops history.
- `conversation.prompt(user_input, tools=tools, stream=True)` — only parses tool calls into the response object; does not execute them, no roundtrip.

## Testing recipe

- The easiest place to test is on `macrobot` (Mac Pro 6,1 running Ubuntu 24.04, the `llamacpp-macpro` deployment target) over SSH, since `llama-server`, `brave_tools.py`, and `BRAVE_API_KEY` are already wired up there.
  - Plain smoke: `llmchat`, ask any non-tool question. Expect a streaming Markdown reply.
  - Tool roundtrip: `llmchat`, `/tools` (debug on), then:
    ```
    find articles about children using noise cancelling headphones and summarize them
    ```
    Expect a `→ web_search_brave({…})` debug line followed by a final Markdown summary listing 3–5 articles.
- Local repro: any OpenAI-compatible endpoint + a `brave_tools.py` (or even a trivial `add(x, y)` function tool) is enough. You don't need a Mac Pro; you just need a model that actually calls tools.

## Files of interest

- `llmchat/__init__.py`
  - `_run()` — picks `conversation.chain` (with tools) vs `conversation.prompt` (plain). The fix lives here.
  - `_before_tool_call()` — closure callback that prints the `↪` inline tool-call indicator.
  - `for chunk in _run():` loop — single-level iteration; `ChainResponse` already flattens.

## Not in scope (intentional)

- Persisting conversations between runs. Today, exiting drops the conversation. Adding `llm`'s built-in session save would be useful but is orthogonal to the rest of the REPL.
- Streaming token-level (vs. chunk-level) animation. The current chunk-level re-render of the full buffer is fine; finer animation isn't worth the complexity.
- Theme / color customization. `rich`'s defaults are fine for now.
