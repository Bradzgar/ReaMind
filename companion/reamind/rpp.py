from __future__ import annotations

import re
from pathlib import Path


def parse_chunks(text: str) -> list[dict]:
    lines = text.split("\n")
    root = {"children": [], "name": "__root__", "lines": []}
    stack = [root]

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<"):
            rest = stripped[1:]
            name = rest.split()[0] if rest.strip() else rest
            chunk = {"name": name, "full_tag": rest, "lines": [], "children": []}
            stack[-1]["children"].append(chunk)
            stack.append(chunk)
        elif stripped == ">":
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1]["lines"].append(stripped)

    return root["children"]


_SOURCE_PATTERN = re.compile(r'<SOURCE\s+(\w+)')


def extract_sources(rpp_path: Path) -> list[dict]:
    try:
        text = rpp_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return []

    chunks = parse_chunks(text)

    def walk(chunk_list, results):
        for chunk in chunk_list:
            m = _SOURCE_PATTERN.match(f"<{chunk['full_tag']}")
            if m:
                source_type = m.group(1).upper()
                file_path = None
                for line in chunk["lines"]:
                    if line.startswith("FILE "):
                        file_path = line[5:].strip().strip('"')
                        break
                if file_path:
                    p = Path(file_path)
                    if not p.is_absolute():
                        p = (rpp_path.parent / p).resolve()
                    results.append({
                        "type": source_type,
                        "path": str(p),
                        "line": 0,
                    })
            walk(chunk["children"], results)

    results = []
    walk(chunks, results)
    return results
