import base64
import hashlib
import os
import re
import subprocess
from pathlib import Path

from .code import SECRET, eligible

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[a-f0-9]{40}$")


class GitRepo:
    def __init__(self, data_dir: Path, repo: str, token: str):
        if not REPO.fullmatch(repo) or any(p in {".", ".."} for p in repo.split("/")):
            raise ValueError("Invalid GitHub repository")
        self.path = data_dir / "repos" / hashlib.sha256(repo.encode()).hexdigest()
        self.path.mkdir(parents=True, exist_ok=True)
        self.repo = repo
        self.env = os.environ.copy() | {"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": "Authorization: Basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode(),
            "GIT_CONFIG_KEY_1": "core.hooksPath", "GIT_CONFIG_VALUE_1": os.devnull,
            "GIT_CONFIG_KEY_2": "core.quotePath", "GIT_CONFIG_VALUE_2": "false"}
        if not (self.path / "HEAD").exists():
            self.run("init", "--bare")

    def run(self, *args, binary=False, check=True):
        p = subprocess.run(["git", "-C", str(self.path), *args], env=self.env,
                           capture_output=True, timeout=180)
        if check and p.returncode:
            raise RuntimeError(f"Git {args[0]} failed (exit {p.returncode})")
        return p.stdout if binary else p.stdout.decode("utf-8", errors="replace")

    def sync(self, head, base):
        if not SHA.fullmatch(head) or not SHA.fullmatch(base):
            raise ValueError("Expected full Git SHA")
        self.run("fetch", "--no-tags", "--depth=100", f"https://github.com/{self.repo}.git", head, base)
        for depth in (0, 300, 1000):
            if depth:
                self.run("fetch", "--no-tags", f"--deepen={depth}", f"https://github.com/{self.repo}.git", head, base)
            merge_base = self.run("merge-base", head, base, check=False).strip()
            if SHA.fullmatch(merge_base):
                return merge_base
        raise RuntimeError("Merge base unavailable within bounded history fetch")

    def ancestor(self, old, head):
        if not old or not SHA.fullmatch(old):
            return False
        result = subprocess.run(["git", "-C", str(self.path), "merge-base", "--is-ancestor", old, head],
                                env=self.env, capture_output=True, timeout=20)
        return result.returncode == 0

    def diff(self, base, head, paths=()):
        return self.run("diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--unified=5", base, head, "--", *paths)

    def changed_paths(self, base, head):
        return self.run("diff", "--name-only", "-z", "--no-renames", base, head).rstrip("\0").split("\0")

    def read(self, sha, path):
        # No shell, no checkout, no filters, no hooks. Only Git blobs are read.
        if not SHA.fullmatch(sha) or path.startswith("/") or ".." in Path(path).parts:
            raise ValueError("Invalid blob location")
        return self.run("show", f"{sha}:{path}", check=False)

    def files(self, sha, settings, excludes=()):
        entries = self.run("ls-tree", "-rlz", sha).split("\0")
        files, skipped, total = {}, [], 0
        selected = []
        for entry in entries:
            if not entry:
                continue
            metadata, path = entry.split("\t", 1)
            mode, kind, blob, size = metadata.split()
            if kind != "blob" or mode not in {"100644", "100755"} or not eligible(path, excludes):
                continue
            size = int(size)
            if len(selected) >= settings.max_files or size > settings.max_file_bytes or total + size > settings.max_source_bytes:
                skipped.append({"path": path, "reason": "source_budget"})
                continue
            selected.append((path, blob))
            total += size
        # Batch reads avoid a process per file on large repositories.
        process = subprocess.run(["git", "-C", str(self.path), "cat-file", "--batch"],
                                 input="".join(b + "\n" for _, b in selected).encode(),
                                 env=self.env, capture_output=True, timeout=180, check=True)
        raw, cursor = process.stdout, 0
        for path, _ in selected:
            stop = raw.index(b"\n", cursor)
            header = raw[cursor:stop].split()
            size = int(header[2])
            content = raw[stop + 1:stop + 1 + size]
            cursor = stop + size + 2
            if b"\0" in content:
                skipped.append({"path": path, "reason": "binary"})
                continue
            text = content.decode("utf-8", errors="replace")
            if SECRET.search(text):
                skipped.append({"path": path, "reason": "possible_secret"})
                continue
            files[path] = text
        return files, skipped
