import time
from pathlib import Path

import httpx
import jwt


class GitHub:
    def __init__(self, app_id: int, key_path: Path, client=None):
        self.app_id, self.key_path = app_id, key_path
        self.client = client or httpx.Client(base_url="https://api.github.com", timeout=45,
                                            headers={"Accept": "application/vnd.github+json",
                                                     "X-GitHub-Api-Version": "2022-11-28"})
        self.tokens = {}
        self.bot_login = None

    def app_headers(self):
        now = int(time.time())
        app_jwt = jwt.encode({"iat": now-60, "exp": now+540, "iss": str(self.app_id)},
                             self.key_path.read_text(), algorithm="RS256")
        return {"Authorization": f"Bearer {app_jwt}"}

    def installation_for_repo(self, repo):
        response = self.client.get(f"/repos/{repo}/installation", headers=self.app_headers())
        response.raise_for_status()
        return response.json()["id"]

    def own_comment(self, comment):
        return comment.get("user", {}).get("login") == self.bot_login and comment.get("user", {}).get("type") == "Bot"

    def token(self, installation_id):
        from datetime import datetime
        cached = self.tokens.get(installation_id)
        if cached and cached[1] > time.time() + 120:
            return cached[0]
        headers = self.app_headers()
        if not self.bot_login:
            app = self.client.get("/app", headers=headers)
            app.raise_for_status()
            self.bot_login = app.json()["slug"] + "[bot]"
        response = self.client.post(f"/app/installations/{int(installation_id)}/access_tokens",
                                    headers=headers)
        response.raise_for_status()
        data = response.json()
        self.tokens[installation_id] = (data["token"], datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp())
        return data["token"]

    def request(self, method, path, installation, **kwargs):
        for attempt in range(3):
            response = self.client.request(method, path, headers={"Authorization": f"Bearer {self.token(installation)}"}, **kwargs)
            if response.status_code == 401 and attempt == 0:
                self.tokens.pop(installation, None)
                continue
            if method == "GET" and response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(min(10, int(response.headers.get("Retry-After", "2"))))
                continue
            response.raise_for_status()
            return response.json() if response.content else None
        raise RuntimeError("GitHub request exhausted retries")

    def pages(self, path, installation):
        output = []
        for page in range(1, 101):
            rows = self.request("GET", path, installation, params={"per_page": 100, "page": page})
            output.extend(rows)
            if len(rows) < 100:
                return output
        raise RuntimeError("GitHub pagination exceeded safety budget")

    def pr(self, repo, number, installation):
        return self.request("GET", f"/repos/{repo}/pulls/{number}", installation)

    def can_command(self, repo, login, installation):
        result = self.request("GET", f"/repos/{repo}/collaborators/{login}/permission", installation)
        return result.get("permission") in {"admin", "maintain", "write"}
