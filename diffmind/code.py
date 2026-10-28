"""Static code inspection. Never imports or executes repository code."""
import fnmatch
import re
from pathlib import PurePosixPath

from tree_sitter_language_pack import get_parser

from .models import Chunk

LANGUAGES = {".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
             ".jsx": "javascript", ".go": "go", ".rs": "rust", ".java": "java", ".cs": "csharp",
             ".rb": "ruby", ".php": "php", ".c": "c", ".cpp": "cpp"}
TEXT_EXTENSIONS = set(LANGUAGES) | {".md", ".sql", ".json", ".yaml", ".yml", ".toml", ".graphql"}
IGNORE_PARTS = {".git", "node_modules", "vendor", "dist", "build", ".next", ".venv", "coverage", "__pycache__"}
SECRET = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:ghp_|ghs_|github_pat_)[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9_-]{24,}")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]{2,}")


def eligible(path, excludes=()):
    p = PurePosixPath(path)
    if (p.is_absolute() or ".." in p.parts or any(x in IGNORE_PARTS for x in p.parts)
            or any(ord(c) < 32 or c in {'"', '\\'} for c in path)):
        return False
    name = p.name.lower()
    if (name.startswith(".env") or name.endswith((".pem", ".key", ".lock", "-lock.json", ".min.js"))
            or name in {"credentials.json", "secrets.json", "secrets.yaml"}):
        return False
    return p.suffix in TEXT_EXTENSIONS and not any(fnmatch.fnmatchcase(path, g) for g in excludes)


def lexical(text):
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).replace("_", " ")
    return text + "\n" + split


def chunk_file(path, text, token_count=None):
    if SECRET.search(text):
        return []
    language = LANGUAGES.get(PurePosixPath(path).suffix, "text")
    raw = text.encode()
    lines = text.splitlines()
    if not lines:
        return []
    boundaries = {0, len(lines)}
    symbols = []
    if language != "text":
        try:
            root = get_parser(language).parse(raw).root_node
            def visit(node):
                if any(x in node.type for x in ("function", "method", "class", "interface", "struct")):
                    name = node.child_by_field_name("name")
                    if name:
                        start, end = node.start_point.row, node.end_point.row + 1
                        symbols.append((start, end, raw[name.start_byte:name.end_byte].decode(errors="replace")))
                        boundaries.update((start, min(end, len(lines))))
                for child in node.named_children:
                    visit(child)
            visit(root)
        except (LookupError, ValueError, RuntimeError):
            pass  # Unsupported grammar: explicit line-window fallback.
    chunks = []
    edges = sorted(boundaries)
    for begin, end in zip(edges, edges[1:]):
        symbol = next((s for a, b, s in sorted(symbols, key=lambda x: x[1]-x[0]) if a <= begin < b), "module")
        cursor = begin
        while cursor < end:
            stop = min(cursor + 40, end)
            prefix = f"{path}\n{language} {symbol}\n"
            while stop > cursor + 1:
                body = "\n".join(lines[cursor:stop])
                size = token_count(prefix + body) if token_count else len(prefix + body) // 3
                if size <= 440:
                    break
                stop -= 1
            body = "\n".join(lines[cursor:stop])
            # A single minified/oversize line is deliberately not silently truncated.
            size = token_count(prefix + body) if token_count else len(prefix + body) // 3
            if body.strip() and size <= 480:
                chunks.append(Chunk(path, cursor + 1, stop, symbol, body, language))
            cursor = stop
    return chunks


def parse_diff(patch):
    """GitHub commentable lines, keyed by path then side; handles deletions and multiple hunks."""
    result, path, old, new = {}, None, None, None
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            path, old, new = None, None, None
        elif line.startswith("+++ "):
            candidate = line[4:]
            if candidate != "/dev/null":
                path = candidate.removeprefix("b/")
            if path:
                result.setdefault(path, {"LEFT": set(), "RIGHT": set(), "changed": set(), "patch": []})
        elif line.startswith("--- ") and line[4:] != "/dev/null":
            path = line[4:].removeprefix("a/")
        elif line.startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if match:
                old, new = map(int, match.groups())
                result.setdefault(path, {"LEFT": set(), "RIGHT": set(), "changed": set(), "patch": []})
        elif path in result and old is not None:
            if line.startswith("\\"):
                continue
            if line.startswith("-"):
                result[path]["LEFT"].add(old)
                old += 1
            elif line.startswith("+"):
                result[path]["RIGHT"].add(new)
                result[path]["changed"].add(new)
                new += 1
            elif line.startswith(" "):
                result[path]["RIGHT"].add(new)
                result[path]["LEFT"].add(old)
                old += 1
                new += 1
    return result
