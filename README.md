# llmchat

A small Python REPL that wraps the [`llm`](https://github.com/simonw/llm) library and gives it a chat UX that doesn't feel like talking to `cat`. Live-rendered Markdown so bullets, links, and code blocks survive streaming. A spinner during the gap between submitting a prompt and the first token. `prompt_toolkit` input with persistent history. Slash commands. Auto-loads a tool functions file from the standard `llm` config directory.

## Requirements

- Python 3.11 or newer.
- `llm` configured with a default model already set:
  ```bash
  llm models default <model_id>
  ```
- Optional: a tools file at `~/.config/io.datasette.llm/tools/brave_tools.py`. Any top-level functions in that file (with type hints and docstrings) become tools the model can call. Credentials those tools need (e.g. `BRAVE_API_KEY`) must be in the environment before `llmchat` is launched — they are deliberately not stored in this repo.

## Install

One-shot, from GitHub:

```bash
uv tool install git+https://github.com/jbeker/llm_chat
```

Editable / development:

```bash
git clone git@github.com:jbeker/llm_chat.git
cd llm_chat
uv tool install --from . llmchat
```

`uv` puts the entry point at `~/.local/bin/llmchat`; make sure that's on your `PATH`.

## Usage

```
llmchat
```

You'll see a header showing the loaded model and any registered tools, then a `❯ ` prompt. Type and hit enter. Responses stream as rendered Markdown.

Slash commands:

| Command  | Effect                                                 |
| -------- | ------------------------------------------------------ |
| `/exit`  | Quit the REPL (`/quit` and Ctrl-D also work).          |
| `/new`   | Reset the conversation history.                        |
| `/tools` | Toggle a debug line that prints each tool call.        |

Prompt history is stored at `~/.config/io.datasette.llm/llmchat_history.txt` and recalled with the up arrow across sessions.

## Design notes

- Loads tool functions from `~/.config/io.datasette.llm/tools/brave_tools.py` via `importlib`. The path is hard-coded by convention so any deployment that already manages the standard `llm` config directory (an Ansible playbook, a dotfiles repo, etc.) works without further wiring.
- Renders streamed responses with `rich.Live` + `rich.Markdown`, re-rendering the entire accumulated buffer on each chunk. This keeps URLs intact (no mid-token line breaks) and renders proper bullet indentation while still feeling like streaming.
- Conversation state is held in a single `llm.Conversation`; multi-turn works as long as the session is alive. There is intentionally no persistence between runs.

## License

MIT.
