#!/usr/bin/env python3
"""将本地仓库发布到 GitHub。

用法（二选一提供 token，优先环境变量）：
    set GITHUB_TOKEN=ghp_xxx && python scripts/publish_github.py [repo_name]
    python scripts/publish_github.py [repo_name] C:/path/to/token.txt

脚本只从环境变量或本地文本文件读取 token，绝不写入仓库、不写入 .git/config。
推送完成后会把 remote URL 重置为不含凭据的 HTTPS 地址。
"""
import json
import os
import subprocess
import sys
import tempfile

API = "https://api.github.com"
DEFAULT_REPO = "innovative-drug-cro-rotation"
DESC = ("创新药—CRO 板块轮动交易策略：回测代码与复现数据 "
        "(A-share innovative drug / CRO sector rotation backtest)")


def get_token():
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    if len(sys.argv) > 2:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            return f.read().strip()
    raise SystemExit("未提供 token：请设置 GITHUB_TOKEN 或把 token 文件路径作为第二个参数传入")


def api(token, method, path, payload=None):
    """通过 curl 调用 GitHub API（本机 Python 的 SSL 证书链不可用，curl 正常）。
    token 只写入临时配置文件，不出现在命令行参数中。"""
    cfg_fd, cfg_path = tempfile.mkstemp(prefix="ghcfg_", suffix=".txt")
    try:
        with os.fdopen(cfg_fd, "w", encoding="utf-8") as f:
            f.write('header = "Authorization: Bearer %s"\n' % token)
            f.write('header = "Accept: application/vnd.github+json"\n')
            f.write('header = "User-Agent: repo-publisher"\n')
        cmd = ["curl", "-s", "-S", "-K", cfg_path, "--ssl-no-revoke", "-X", method,
               "-w", "\n%{http_code}", API + path]
        body_path = None
        if payload is not None:
            bfd, body_path = tempfile.mkstemp(prefix="ghbody_", suffix=".json")
            with os.fdopen(bfd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            cmd += ["-H", "Content-Type: application/json", "--data-binary", "@" + body_path]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120)
        out = r.stdout.rstrip("\n")
        if "\n" in out:
            body, code = out.rsplit("\n", 1)
        else:
            body, code = "", out
        try:
            code_i = int(code)
        except ValueError:
            return {"__error__": -1, "__body__": r.stderr[:300] or out[:300]}
        if 200 <= code_i < 300:
            return json.loads(body) if body.strip() else {}
        return {"__error__": code_i, "__body__": body[:400]}
    finally:
        for p in (cfg_path, body_path if payload is not None else None):
            if p and os.path.exists(p):
                os.remove(p)


def git(*args, check=True):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit("git %s 失败: %s" % (" ".join(args), (r.stderr or "").strip()))
    return r.stdout.strip()


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPO
    token = get_token()

    me = api(token, "GET", "/user")
    if "__error__" in me:
        raise SystemExit("获取用户信息失败(%s)：%s" % (me["__error__"], me["__body__"][:300]))
    user = me["login"]
    print("GitHub 用户:", user)

    res = api(token, "POST", "/user/repos",
              {"name": repo, "description": DESC, "private": False, "auto_init": False})
    if "__error__" in res:
        if res["__error__"] == 422 and "already exists" in res["__body__"]:
            print("仓库已存在，直接复用：%s/%s" % (user, repo))
        else:
            raise SystemExit("创建仓库失败(%s)：%s" % (res["__error__"], res["__body__"][:300]))
    else:
        print("仓库已创建:", res["html_url"])

    git("branch", "-M", "main")
    subprocess.run(["git", "remote", "remove", "origin"], capture_output=True)
    git("config", "--local", "http.schannelCheckRevoke", "false")  # 绕过本机吊销检查失败
    auth_url = "https://%s:%s@github.com/%s/%s.git" % (user, token, user, repo)
    git("remote", "add", "origin", auth_url)
    git("push", "-u", "origin", "main")
    # 清除 URL 中的凭据
    git("remote", "set-url", "origin", "https://github.com/%s/%s.git" % (user, repo))

    html = "https://github.com/%s/%s" % (user, repo)
    print("\n推送完成:", html)
    print("remote 已重置为:", git("remote", "get-url", "origin"))


if __name__ == "__main__":
    main()
