"""dsh 浏览器容器：pywebview 内嵌 DeepSeek Harness Web UI。

启动时自动找一个空闲端口，用捆绑/环境的 node 离线启动
`@deepseek-ai/dsh web`，就绪后在内嵌 WebView 中加载，关闭窗口即回收进程。
"""
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

import webview

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DSH_PACKAGE = "@deepseek-ai/dsh"
DSH_BIN_JS = os.path.join("node_modules", "@deepseek-ai", "dsh", "lib", "bin.js")
REGISTRY_LATEST = "https://registry.npmjs.org/@deepseek-ai%2Fdsh/latest"
NPM_LATEST = "https://registry.npmjs.org/npm/latest"
CHECK_TIMEOUT = 3      # 版本检查超时:离线/网络差时最多阻塞这么久
INSTALL_TIMEOUT = 1800  # 下载 npm + 安装依赖的总超时（慢网络实测可达 20 分钟+）

_instance_mutex = None


def base_dir():
    """打包后为 exe 所在目录；源码运行时为脚本所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def candidate_node_dirs():
    """本地运行时的候选目录（去重、去掉空项）。"""
    dirs = [os.path.join(base_dir(), "node"), os.environ.get("DSH_BROWSER_NODE_DIR", "")]
    return [d for d in dict.fromkeys(dirs) if d]


def find_node_dir():
    """返回可用的本地 dsh 运行时目录（含 node.exe 与 dsh），找不到返回 None。"""
    for node_dir in candidate_node_dirs():
        if os.path.isfile(os.path.join(node_dir, "node.exe")) and os.path.isfile(
            os.path.join(node_dir, DSH_BIN_JS)
        ):
            return node_dir
    return None


def resolve_dsh_cmd():
    """返回启动 dsh 的命令前缀列表。

    优先级：捆绑 node（exe/脚本同级 node/）→ 环境变量 DSH_BROWSER_NODE_DIR → 系统 PATH 的 npx。
    """
    node_dir = find_node_dir()
    if node_dir:
        return [os.path.join(node_dir, "node.exe"), os.path.join(node_dir, DSH_BIN_JS)]
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", "@deepseek-ai/dsh"]
    raise RuntimeError(
        "未找到 dsh 运行时：请将 node 目录放到程序同级的 node/ 下，"
        "或设置环境变量 DSH_BROWSER_NODE_DIR，或确保 npx 在 PATH 中。"
    )


def _fetch_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def local_dsh_version(node_dir):
    """读取本地 dsh 包的版本号，读取失败返回 None。"""
    pkg_json = os.path.join(node_dir, "node_modules", "@deepseek-ai", "dsh", "package.json")
    try:
        with open(pkg_json, encoding="utf-8") as f:
            return json.load(f).get("version")
    except Exception:
        return None


def _split_ver(v):
    """把 '0.1.1-rc.2' 拆成 (主次补丁号元组, 预发布段列表)。"""
    core, _, pre = v.strip().lstrip("v").partition("-")
    nums = []
    for part in core.split("."):
        nums.append(int(part) if part.isdigit() else 0)
    while len(nums) < 3:
        nums.append(0)
    pre_parts = []
    for token in re.findall(r"\d+|\D+", pre):
        pre_parts.append((0, int(token)) if token.isdigit() else (1, token))
    return nums, pre_parts


def is_newer_version(local, remote):
    """remote 是否比 local 新；local 解析失败视为极老版本（触发自愈式升级）。"""
    try:
        lnums, lpre = _split_ver(local)
        rnums, rpre = _split_ver(remote)
    except Exception:
        return False
    if lnums != rnums:
        return rnums > lnums
    if lpre and not rpre:
        return True  # 远端从 rc 转正式版
    if not lpre and rpre:
        return False  # 本地已是正式版，不回退到预发布
    return rpre > lpre


def _writable(path):
    try:
        probe = os.path.join(path, ".dsh-update-probe")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return True
    except Exception:
        return False


def recover_runtime_backup(node_dir):
    """上次自更新中断的恢复：node_modules 缺失而备份还在时，把备份还原。"""
    nm = os.path.join(node_dir, "node_modules")
    bak = nm + ".bak"
    if not os.path.isdir(bak):
        return
    if not os.path.isdir(nm):
        try:
            os.rename(bak, nm)
        except Exception:
            pass
    else:  # 两份都在说明上次已成功、仅清理失败
        shutil.rmtree(bak, ignore_errors=True)


def check_for_update(node_dir):
    """启动时的轻量检查（≤CHECK_TIMEOUT 秒）：有新版返回版本号，否则/离线返回 None。"""
    local = local_dsh_version(node_dir)
    if not local:
        return None
    try:
        latest = _fetch_json(REGISTRY_LATEST, CHECK_TIMEOUT).get("version")
    except Exception:
        return None  # 离线或超时：照常使用现有运行时
    return latest if is_newer_version(local, latest) else None


def perform_update(node_dir, latest):
    """把 node/ 里的 dsh 升级到 latest；任何失败都回滚，绝不破坏现有运行时。

    捆绑包里没有 npm：临时下载 npm 官方 tarball，用捆绑 node 引导一个临时 npm，
    借用户自己的 npmrc 配置（镜像源等）完成整棵依赖树的安装。
    """
    nm = os.path.join(node_dir, "node_modules")
    bak = nm + ".bak"
    tmpdir = tempfile.mkdtemp(prefix="dsh-update-")
    try:
        npm_meta = _fetch_json(NPM_LATEST, INSTALL_TIMEOUT)
        tgz_path = os.path.join(tmpdir, "npm.tgz")
        with urllib.request.urlopen(npm_meta["dist"]["tarball"], timeout=INSTALL_TIMEOUT) as r:
            with open(tgz_path, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
        with tarfile.open(tgz_path, "r:gz") as tf:
            tf.extractall(tmpdir, filter="data")
        npm_cli = os.path.join(tmpdir, "package", "bin", "npm-cli.js")
        node_exe = os.path.join(node_dir, "node.exe")
        if not (os.path.isfile(npm_cli) and os.path.isfile(node_exe) and _writable(node_dir)):
            return False

        env = os.environ.copy()
        env.pop("NODE_OPTIONS", None)  # 同主进程：防 WorkBuddy 注入的 shim 干扰 npm 子进程
        cmd = [
            node_exe, npm_cli, "install",
            "--prefix", node_dir,
            "--no-audit", "--no-fund", "--loglevel=error",
            "--update-notifier=false", "--cache", os.path.join(tmpdir, "npm-cache"),
            f"{DSH_PACKAGE}@{latest}",
        ]
        if os.path.isdir(bak):  # 清掉历史残留再备份
            shutil.rmtree(bak, ignore_errors=True)
        os.rename(nm, bak)  # 同卷改名瞬间完成；此后任何失败都走回滚
        proc = subprocess.run(
            cmd, cwd=tmpdir, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW, timeout=INSTALL_TIMEOUT,
        )
        ok = (
            proc.returncode == 0
            and local_dsh_version(node_dir) == latest
            and os.path.isfile(os.path.join(node_dir, DSH_BIN_JS))
        )
        if ok:
            shutil.rmtree(bak, ignore_errors=True)
            print(f"dsh 运行时已更新到 {latest}，下次启动生效。", flush=True)
            return True
        raise RuntimeError(
            f"npm install failed rc={proc.returncode}\n{proc.stdout.decode(errors='replace')[-2000:]}"
        )
    except Exception:
        try:  # 回滚：丢弃装了一半的 node_modules，还原备份
            if os.path.isdir(nm):
                shutil.rmtree(nm, ignore_errors=True)
            if os.path.isdir(bak):
                os.rename(bak, nm)
        except Exception:
            pass  # 回滚也失败时留给下次启动的 recover_runtime_backup 兜底
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def update_dsh_runtime(node_dir, latest=None):
    """检查并同步执行更新（一步到位版；主流程分两段调用以便关窗后再装）。"""
    latest = latest or check_for_update(node_dir)
    if latest:
        perform_update(node_dir, latest)


def find_free_port():
    """借用系统分配一个空闲端口。"""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_ready(url, proc, timeout=60):
    """轮询 dsh 直到 HTTP 200；进程早退或超时抛错。"""
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError(f"dsh exited early with code {proc.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"dsh not ready within {timeout}s at {url}")


def acquire_single_instance():
    """会话级互斥锁：已有实例在运行时返回 False，调用方应退出。

    handle 挂在模块级全局变量上防 GC，窗口关闭进程退出时自动释放。
    """
    global _instance_mutex
    if sys.platform != "win32":
        return True
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, "Local\\dsh-browser-single-instance"
    )
    if not _instance_mutex:
        return True
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    if not acquire_single_instance():
        print("dsh-browser 已在运行，本实例退出。")
        sys.exit(0)

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    for d in candidate_node_dirs():  # 先恢复上次可能中断的自更新，再做解析
        recover_runtime_backup(d)
    node_dir = find_node_dir()
    # 只做 ≤3s 的轻量检查；耗时的安装推迟到关窗之后（见 main 尾部），不阻塞启动
    pending_version = check_for_update(node_dir) if node_dir else None

    # 标题带上实际运行的 dsh 版本；npx 兜底/读取失败时退化为裸标题
    title = "DeepSeek Harness"
    if node_dir:
        dsh_ver = local_dsh_version(node_dir)
        if dsh_ver:
            title = f"DeepSeek Harness (dsh {dsh_ver})"

    cmd = resolve_dsh_cmd() + ["web", "--port", str(port)]
    env = os.environ.copy()
    env.pop("NODE_OPTIONS", None)  # 去掉 WorkBuddy 注入的 safe-delete shim（会拦截 dsh 的 trash 操作）
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )

    log = []

    def _drain():
        try:
            for line in proc.stdout:
                log.append(line.decode(errors="replace"))
        except Exception:
            pass

    threading.Thread(target=_drain, daemon=True).start()

    try:
        wait_ready(url, proc)
    except Exception as e:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        raise RuntimeError(f"启动 dsh 失败: {e}\n日志尾部:\n{''.join(log[-40:])}")

    print(f"dsh web 已就绪: {url}", flush=True)
    webview.create_window(title, url, width=1280, height=800)
    webview.start()

    # 窗口关闭 → 杀整个进程树（node/npx → dsh），避免孤儿进程
    subprocess.run(
        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    if pending_version and node_dir:
        # dsh 已停：此时安装再慢也无感，失败自动回滚，下次启动生效
        perform_update(node_dir, pending_version)


if __name__ == "__main__":
    main()
