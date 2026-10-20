---
owns: The index of docs/ — which page owns which subject, and which code each page documents.
not:  How to work here (.claude/docs/) · the subjects themselves (the pages below)
---
<!-- scaffold: core/docs/README.md — project-owned after setup -->

# Juice-Mate — documentation

Grep the **Code** column for a source path to find the page that documents it.

| Page | Owns | Code |
| ---- | ---- | ---- |
| [architecture.md](architecture.md) | stack, sources, install and self-update, layout, icons | `src/juice_mate/**`, `pyproject.toml`, `.github/workflows/**` |
| [plan/](plan/README.md) | the order of building, state of each step | — |

A big document is a folder: one section per file (`§N` → `N-....md`), the folder's `README.md` is its
index. Every page opens with an `owns:` / `not:` / `code:` header.
