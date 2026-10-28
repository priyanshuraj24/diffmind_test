import hashlib
import json
import threading

from .code import SECRET, eligible, parse_diff
from .git import GitRepo
from .retrieval import Index
from .reviewer import Reviewer, validate_findings


def fingerprint(finding, source):
    lines = source.splitlines()
    anchor = lines[finding.line-1].strip() if finding.line <= len(lines) else finding.title
    return hashlib.sha256(f"{finding.path}:{finding.category}:{anchor}".encode()).hexdigest()[:24]


class Engine:
    def __init__(self, settings, store, github):
        self.s, self.store, self.github = settings, store, github
        self.index = None
        self.reviewer = Reviewer(settings)
        self.lock = threading.Lock()

    def run_once(self):
        if not self.lock.acquire(blocking=False):
            return {"status": "busy"}
        job, stop = None, threading.Event()
        try:
            job = self.store.claim(self.s.lease_seconds)
            if not job:
                return {"status": "idle"}
            def heartbeat():
                while not stop.wait(30):
                    self.store.heartbeat(job, self.s.lease_seconds)
            thread = threading.Thread(target=heartbeat, daemon=True)
            thread.start()
            result = self.run(job)
            self.store.finish(job, result, result.get("status", "done"))
            return {"job_id": str(job["id"]), **result}
        except Exception as error:
            if job:
                # Exceptions can contain request headers or source; persist only class + bounded safe message.
                detail = f"{type(error).__name__}: {str(error).splitlines()[0][:400]}"
                if SECRET.search(detail) or "Bearer " in detail:
                    detail = type(error).__name__
                self.store.fail(job, detail)
            return {"status": "error", "job_id": str(job["id"]) if job else None, "error_type": type(error).__name__}
        finally:
            stop.set()
            self.lock.release()

    def current(self, job):
        pr = self.github.pr(job["repo"], job["number"], job["payload"]["installation_id"])
        state = self.store.pr_state(job["repo"], job["number"])
        return pr, (pr["head"]["sha"] == job["head"] and pr["state"] == "open" and not pr.get("draft")
                    and not state.get("paused", False))

    def run(self, job):
        repo, head, installation = job["repo"], job["head"], job["payload"]["installation_id"]
        if not self.s.allows(repo):
            return {"status": "superseded", "reason": "repository_not_allowed"}
        pr, is_current = self.current(job)
        if not is_current:
            return {"status": "superseded"}
        # Reuse the durable publication intent after a timeout. Never regenerate a different
        # set of findings while reconciling a possibly successful GitHub write.
        if job.get("result"):
            result = job["result"]
            if self.s.publish and self.store.heartbeat(job, self.s.lease_seconds):
                self.publish(job, result, self.store.findings(repo, job["number"]))
            return result
        git = GitRepo(self.s.data_dir, repo, self.github.token(installation))
        merge_base = git.sync(head, pr["base"]["sha"])
        state = self.store.pr_state(repo, job["number"])
        old_head = state.get("last_head")
        incremental = job["kind"] == "review" and git.ancestor(old_head, head)
        analysis_base = old_head if incremental else merge_base
        paths = [p for p in git.changed_paths(analysis_base, head) if eligible(p)]
        # Rules come from the target branch, never from unmerged PR instructions.
        rules = git.read(pr["base"]["sha"], ".diffmind.json")
        config = {}
        if rules and len(rules) < 20000:
            config = json.loads(rules)
        excludes = config.get("exclude", [])
        if not isinstance(excludes, list) or not all(isinstance(p, str) for p in excludes):
            raise ValueError("Invalid trusted repository exclude rules")
        paths = [p for p in paths if eligible(p, excludes)]
        if not self.index:
            self.index = Index(self.s, self.store)
        files, skipped = git.files(head, self.s, excludes)
        chunks, coverage = self.index.build(repo, head, files, skipped)
        full_diff = git.diff(merge_base, head)
        locations = parse_diff(full_diff)
        previous = self.store.findings(repo, job["number"])
        batches, batch, size = [], [], 0
        for path in paths:
            patch = git.diff(analysis_base, head, [path])
            if SECRET.search(patch):
                skipped.append({"path": path, "reason": "possible_secret_in_diff"})
                continue
            if len(patch) > self.s.batch_chars:
                skipped.append({"path": path, "reason": "diff_budget"})
                continue
            if batch and size + len(patch) > self.s.batch_chars:
                batches.append(batch)
                batch, size = [], 0
            batch.append((path, patch))
            size += len(patch)
        if batch:
            batches.append(batch)
        for dropped in batches[self.s.max_batches:]:
            skipped.extend({"path": p, "reason": "review_batch_budget"} for p, _ in dropped)
        summaries, findings, traces, usages, rejected = [], [], [], [], []
        for batch in batches[:self.s.max_batches]:
            batch_paths = [p for p, _ in batch]
            patch = "\n".join(d for _, d in batch)
            query = "\n".join(batch_paths) + "\n" + patch[:6000]
            evidence, trace = self.index.search(repo, head, query, chunks, batch_paths, parse_diff(patch))
            # Removed files still need local evidence with the old revision clearly labelled.
            for path in batch_paths:
                if path not in files:
                    before = git.read(merge_base, path)
                    if before and not SECRET.search(before):
                        evidence.append({"evidence_id": f"E{len(evidence)+1}", "path": path, "start": 1,
                            "end": len(before.splitlines()), "text": before[:12000], "head": merge_base,
                            "revision_role": "before"})
            if not evidence:
                raise RuntimeError("No usable evidence for changed code")
            context = {"title": pr["title"][:500], "description": (pr.get("body") or "")[:3000],
                "repository": repo, "head": head, "merge_base": merge_base, "patch": patch,
                "trusted_rules": config.get("instructions", ""), "evidence": evidence,
                "previous_findings": [x["payload"] for x in previous if x["payload"]["path"] in batch_paths],
                "commentable_lines": {p: {s: sorted(locations.get(p, {}).get(s, [])) for s in ("LEFT", "RIGHT")} for p in batch_paths}}
            output, usage = self.reviewer.review(context)
            valid, invalid = validate_findings(output.findings, locations, evidence, self.s.max_findings)
            for finding in valid:
                source = files.get(finding.path, "") if finding.side == "RIGHT" else git.read(merge_base, finding.path)
                finding_data = finding.model_dump()
                finding_data["fingerprint"] = fingerprint(finding, source)
                finding_data["evidence"] = [{k: item[k] for k in ("evidence_id", "path", "start", "end", "head")} for item in evidence if item["evidence_id"] in finding.evidence_ids]
                findings.append(finding_data)
            summaries.append(output.summary)
            traces.append(trace)
            usages.extend(usage)
            rejected.extend(invalid)
        unique = {f["fingerprint"]: f for f in findings}
        findings = list(unique.values())[:self.s.max_findings]
        result = {"status": "done", "head": head, "merge_base": merge_base, "incremental": bool(incremental),
                  "coverage": coverage | {"skipped": skipped + coverage.get("skipped", [])},
                  "retrieval": traces, "usage": usages, "rejected": rejected, "findings": findings,
                  "summary": "\n\n".join(summaries), "publish": self.s.publish}
        _, still_current = self.current(job)
        if not still_current or not self.store.heartbeat(job, self.s.lease_seconds):
            return result | {"status": "superseded", "publish": False}
        if self.s.publish:
            if not self.store.prepare(job, result):
                return result | {"status": "superseded", "publish": False}
            self.publish(job, result, previous)
        self.index.prune(repo, [head, old_head] if old_head else [head])
        return result

    def publish(self, job, result, previous):
        repo, number, installation = job["repo"], job["number"], job["payload"]["installation_id"]
        root = f"/repos/{repo}"
        marker = f"<!-- diffmind:review:{job['id']} -->"
        summary_marker = "<!-- diffmind:summary:v1 -->"
        existing_reviews = self.github.pages(f"{root}/pulls/{number}/reviews", installation)
        comments = self.github.pages(f"{root}/pulls/{number}/comments", installation)
        known = {f["fingerprint"] for f in previous}
        for comment in comments:
            if not self.github.own_comment(comment):
                continue
            for f in result["findings"]:
                if f"<!-- diffmind:finding:{f['fingerprint']} -->" in comment.get("body", ""):
                    known.add(f["fingerprint"])
                    f["comment_id"] = comment["id"]
        fresh = [f for f in result["findings"] if f["fingerprint"] not in known]
        if not any(marker in r.get("body", "") and self.github.own_comment(r) for r in existing_reviews):
            inline = []
            for f in fresh:
                citations = "\n".join(f"- [{e.get('evidence_id', 'Source')} · {e['path']}:{e['start']}](https://github.com/{repo}/blob/{e['head']}/{e['path']}#L{e['start']})" for e in f["evidence"])
                body = f"**[{f['severity']}] {f['title']}**\n\n{f['body']}\n\nScenario: {f['scenario']}\n\nEvidence:\n{citations}\n\n<!-- diffmind:finding:{f['fingerprint']} -->"
                if f.get("suggestion") and f["side"] == "RIGHT" and "```" not in f["suggestion"]:
                    body += "\n\n```suggestion\n" + f["suggestion"] + "\n```"
                inline.append({"path": f["path"], "line": f["line"], "side": f["side"], "body": body})
            _, current = self.current(job)
            if not current:
                raise RuntimeError("Head changed before publication")
            if inline:
                self.github.request("POST", f"{root}/pulls/{number}/reviews", installation,
                    json={"commit_id": job["head"], "event": "COMMENT", "body": marker + "\nDiffMind review; see the maintained summary for coverage.", "comments": inline})
        skipped = result["coverage"].get("skipped", [])
        body = (f"{summary_marker}\n## DiffMind review\n\nReviewed `{job['head'][:12]}` · "
                f"{'Incremental' if result['incremental'] else 'Full'} review · "
                f"{len(result['retrieval'])} review batches\n\n{result['summary'] or 'No eligible code changes to review.'}\n\n"
                f"**Context:** {result['coverage']['chunks']} indexed chunks; exact, lexical and semantic retrieval "
                f"completed for {len(result['retrieval'])} batches.\n\n"
                f"**Findings:** {len(fresh)} new; {len(result['findings'])-len(fresh)} already reported. "
                "Tests were not executed. Existing discussions remain open for human confirmation.\n")
        if skipped:
            body += "\n**Partial coverage — skipped:**\n" + "\n".join(f"- `{s['path']}`: {s['reason']}" for s in skipped[:30])
        _, current = self.current(job)
        if not current:
            raise RuntimeError("Head changed after inline review; newer review required")
        timeline = self.github.pages(f"{root}/issues/{number}/comments", installation)
        summary = next((c for c in timeline if summary_marker in c.get("body", "") and self.github.own_comment(c)), None)
        if summary:
            saved = self.github.request("PATCH", f"{root}/issues/comments/{summary['id']}", installation, json={"body": body})
        else:
            saved = self.github.request("POST", f"{root}/issues/{number}/comments", installation, json={"body": body})
        self.store.published(job, result["findings"], saved["id"])
