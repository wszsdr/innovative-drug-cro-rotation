#!/usr/bin/env python3
"""通过 GitHub Git Data API 上传本地仓库内容（git push 在本机 TLS 校验不可用时的备用通道）。

用法：
    python scripts/publish_github_api.py [repo_name] [token_file]

流程：为每个文件创建 blob → 建 tree → 建 commit → 创建 refs/heads/main。
全程使用 curl 并保留证书校验（仅跳过本机异常的吊销检查），token 只写入临时配置文件。
"""
import base64
import json
import os
import subprocess
import sys
import tempfile

API = "https://api.github.com"
DEFAULT_REPO = "innovative-drug-cro-rotation"
COMMIT_MSG = ("Add innovative-drug/CRO sector rotation backtest code and replication data\n\n"
              "- scripts/backtest_v2.py: 回测主程序\n"
              "- data/: 12 只成分股与 2 个指数前复权日频行情\n"
              "- results/: 绩效指标与逐日净值（v2 口径）\n"
              "- 论文 Markdown 源码与 Word 提交稿")


def load_token():
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    if len(sys.argv) > 2:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            return f.read().strip()
    raise SystemExit("未提供 token")


def call(token, method, path, payload=None, timeout=120):
    cfd, cfg = tempfile.mkstemp(prefix="ghcfg_", suffix=".txt")
    body_path = None
    try:
        with os.fdopen(cfd, "w", encoding="utf-8") as f:
            f.write('header = "Authorization: Bearer %s"\n' % token)
            f.write('header = "Accept: application/vnd.github+json"\n')
            f.write('header = "User-Agent: repo-publisher"\n')
        cmd = ["curl", "-s", "-S", "-K", cfg, "--ssl-no-revoke", "-X", method,
               "-w", "\n%{http_code}", API + path]
        if payload is not None:
            bfd, body_path = tempfile.mkstemp(prefix="ghbody_", suffix=".json")
            with os.fdopen(bfd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            cmd += ["-H", "Content-Type: application/json", "--data-binary", "@" + body_path]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        out = r.stdout.rstrip("\n")
        body, code = (out.rsplit("\n", 1) if "\n" in out else ("", out))
        try:
            code_i = int(code)
        except ValueError:
            raise SystemExit("请求失败: %s %s | %s" % (method, path, r.stderr[:200]))
        if not (200 <= code_i < 300):
            raise SystemExit("API %s %s 返回 %s: %s" % (method, path, code_i, body[:400]))
        return json.loads(body) if body.strip() else {}
    finally:
        for p in (cfg, body_path):
            if p and os.path.exists(p):
                os.remove(p)


def git_out(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("git %s 失败: %s" % (" ".join(args), (r.stderr or "").strip()))
    return r.stdout.strip()


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPO
    token = load_token()
    user = call(token, "GET", "/user")["login"]
    print("GitHub 用户:", user)

    files = [f for f in git_out("-c", "core.quotepath=false", "ls-files").split("\n") if f.strip()]
    print("待上传文件:", len(files))

    # 空仓库不允许创建 blob，先用 contents API 写入占位文件激活仓库
    probe = subprocess.run(
        ["curl", "-s", "-S", "--ssl-no-revoke", "-o", os.devnull, "-w", "%{http_code}",
         "%s/repos/%s/%s/contents/README.md" % (API, user, repo)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if probe.stdout.strip() in ("404", "409", "000"):
        call(token, "PUT", "/repos/%s/%s/contents/README.md" % (user, repo),
             {"message": "init", "content": base64.b64encode(b"# init\n").decode("ascii")})
        print("已激活空仓库")

    tree = []
    for i, rel in enumerate(files, 1):
        with open(rel, "rb") as f:
            content = base64.b64encode(f.read()).decode("ascii")
        b = call(token, "POST", "/repos/%s/%s/git/blobs" % (user, repo),
                 {"content": content, "encoding": "base64"})
        tree.append({"path": rel.replace("\\", "/"), "mode": "100644",
                     "type": "blob", "sha": b["sha"]})
        if i % 8 == 0 or i == len(files):
            print("  blob 进度 %d/%d" % (i, len(files)))

    t = call(token, "POST", "/repos/%s/%s/git/trees" % (user, repo), {"tree": tree})
    print("tree:", t["sha"][:12])
    c = call(token, "POST", "/repos/%s/%s/git/commits" % (user, repo),
             {"message": COMMIT_MSG, "tree": t["sha"], "parents": []})
    print("commit:", c["sha"][:12])

    ref_path = "/repos/%s/%s/git/refs" % (user, repo)
    try:
        call(token, "GET", "/repos/%s/%s/git/ref/heads/main" % (user, repo))
        call(token, "PATCH", ref_path + "/heads/main", {"sha": c["sha"], "force": True})
    except SystemExit:
        call(token, "POST", ref_path, {"ref": "refs/heads/main", "sha": c["sha"]})

    print("\n上传完成: https://github.com/%s/%s" % (user, repo))


if __name__ == "__main__":
    main()
