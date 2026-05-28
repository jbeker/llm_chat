# Development state

A handoff doc so a future session can pick up where this one stopped without re-doing the diagnosis.

## Overview

`llmchat` exists because `aichat` (the previous client) cannot complete a tool-call roundtrip against an OpenAI-compatible endpoint — confirmed across v0.28.0, v0.29.0, v0.30.0 with a transparent socat HTTP capture. The whole tool-roundtrip-failure investigation is in the git history of the `llamacpp-macpro` repo (the Ansible setup that drove this work); see commits around the move from `aichat` to `llm`. This project is the replacement REPL.

## What works

- Plain chat: a query without tools streams from `llama-server` and renders as Markdown live in the terminal.
- Spinner during the first-token latency.
- `prompt_toolkit` input with persistent history at `~/.config/io.datasette.llm/llmchat_history.txt`.
- Slash commands `/exit`, `/quit`, `/new`, `/tools`.
- Auto-loading top-level functions from `~/.config/io.datasette.llm/tools/brave_tools.py` and exposing them as tools to the underlying `llm` model.

## What's broken — tool roundtrip not rendering

When the user asks something that requires a tool call:

- Spinner shows.
- `/tools` debug line prints (e.g. `→ web_search_brave({'query': 'best new casual restaurants in washington DC', 'count': 5})`), proving the model emitted the call.
- No text from the model after the tool. Buffer stays empty. The `— (no text produced) —` placeholder either appears or doesn't depending on whether iteration yielded anything renderable at all.

Plain (non-tool) chats render fine, so the streaming + Markdown render pipeline is working. The broken step is between "tool call emitted" and "the model's follow-up summary is yielded as text chunks."

### Evidence

- `response.tool_calls()` / per-step `chain.responses()[i].tool_calls()` lists the call name and arguments. So the model is emitting a real tool call, not just text that looks like one.
- The same model + same llama-server + same `brave_tools.py` works correctly when driven through `llm`'s own CLI:
  ```
  llm 'find articles about children using noise cancelling headphones and summarize them' \
      --functions ~/.config/io.datasette.llm/tools/brave_tools.py --td
  ```
  produces a clean roundtrip with a Markdown summary at the end. So the underlying `llm` library + `llama-server` pipeline supports auto-execution-and-roundtrip — `llmchat`'s integration is wrong.

## What's been tried

In `llmchat/__init__.py`, the `_run()` helper picks the API call. Attempts so far:

1. `conversation.prompt(user_input, tools=tools, stream=True)` — iterator yields only the first model output. When the model opens with a tool call (`content: ""`), the iterator effectively yields nothing renderable, and the tool is never executed. No auto-roundtrip.
2. `conversation.chain(user_input, tools=tools)` — fall-through path in the `_run()` selector. Unverified whether `Conversation.chain` exists on the installed `llm` release or what it returns; this branch may or may not be taken in practice.
3. `model.chain(user_input, tools=tools, conversation=conversation)` — current attempt. The tool call is recorded (visible via `chain.responses()[0].tool_calls()`), but the single-level `for chunk in chain:` loop in `__init__.py` yields nothing renderable. Buffer stays empty.

## Most likely root cause

The single-level iteration is wrong. `ChainResponse` very likely yields `Response` objects (one per chain step), not strings. Each `Response` is itself iterable and yields text chunks. The current loop's `isinstance(chunk, str)` / `chunk.text()` / `str(chunk)` cascade probably either skips these objects or stringifies them in a way that produces no useful output.

This is unverified. Don't fix it blind — read the source first.

## Next steps for a future session

1. **Read `simonw/llm`'s `llm/cli.py`**, specifically the `prompt` command implementation around the tool/chain handling, and copy the exact iteration pattern verbatim. The CLI's `llm 'query' --functions tools.py` is the working reference — replicate its loop. Cite the file:line you copy from so the change is auditable.
2. **Add a temporary verbose flag** to `llmchat` that logs `type(chunk)` and `repr(chunk)[:200]` of each yielded item. Run it once against a tool-using query. This gives ground truth about what `model.chain` actually emits, with no guessing. Remove the flag once the iteration pattern is fixed.
3. **Confirm `Model.chain()` signature** on the installed `llm` version: `pip show llm` for the version, then read that tagged source. Specifically check: does `chain()` accept `stream=…`? Is streaming the default? Does `conversation=` thread history correctly through multiple chain calls in the same `Conversation`?
4. **If `chain` returns sub-`Response` objects**, restructure the loop:
   ```python
   for sub in chain.responses():       # or for sub in chain (if that's the shape)
       for chunk in sub:               # the actual text-chunk iterator
           buffer.append(chunk)
           live.update(Markdown("".join(buffer)))
   ```
   Make sure to keep the same `rich.Live` region across all sub-responses so the UI feels like one streamed answer.

## Testing recipe

- The easiest place to test is on `macrobot` (Mac Pro 6,1 running Ubuntu 24.04, the `llamacpp-macpro` deployment target) over SSH, since `llama-server`, `brave_tools.py`, and `BRAVE_API_KEY` are already wired up there.
  - Plain smoke: `llmchat`, ask any non-tool question. Expect a streaming Markdown reply.
  - Tool roundtrip: `llmchat`, `/tools` (debug on), then:
    ```
    find articles about children using noise cancelling headphones and summarize them
    ```
    Expect a final Markdown summary listing 3–5 articles. Currently fails by showing only the `→ web_search_brave({…})` debug line.
- Local repro: any OpenAI-compatible endpoint + a `brave_tools.py` (or even a trivial `add(x, y)` function tool) is enough. You don't need a Mac Pro; you just need a model that actually calls tools.

## Files of interest

- `llmchat/__init__.py`
  - `_run()` (~ lines 115–123) — the chain vs. prompt API selector. This is where the fix probably lands.
  - `for chunk in response:` loop (~ lines 134–147) — the iteration that needs to handle nested/per-response chunks.
  - `_try_get_tool_calls()` (~ lines 45–58) — defensive accessor for `tool_calls`; already supports both callable and property forms across `llm` versions.

## Not in scope (intentional)

- Persisting conversations between runs. Today, exiting drops the conversation. Adding `llm`'s built-in session save would be useful but is orthogonal to fixing the tool-roundtrip bug.
- Streaming token-level (vs. chunk-level) animation. The current chunk-level re-render of the full buffer is fine; finer animation isn't worth the complexity.
- Theme / color customization. `rich`'s defaults are fine for now.
