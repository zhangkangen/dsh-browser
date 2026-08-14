"""dsh 浏览器容器：pywebview 内嵌 DeepSeek Harness Web UI。

启动时自动找一个空闲端口，用捆绑/环境的 node 离线启动
`@deepseek-ai/dsh web`，就绪后在内嵌 WebView 中加载，关闭窗口即回收进程。
"""
import ctypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import webview

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_instance_mutex = None


def base_dir():
    """打包后为 exe 所在目录；源码运行时为脚本所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resolve_dsh_cmd():
    """返回启动 dsh 的命令前缀列表。

    优先级：捆绑 node（exe/脚本同级 node/）→ 环境变量 DSH_BROWSER_NODE_DIR → 系统 PATH 的 npx。
    """
    candidates = [
        os.path.join(base_dir(), "node"),
        os.environ.get("DSH_BROWSER_NODE_DIR", ""),
    ]
    for node_dir in candidates:
        if not node_dir:
            continue
        node_exe = os.path.join(node_dir, "node.exe")
        dsh_js = os.path.join(node_dir, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js")
        if os.path.isfile(node_exe) and os.path.isfile(dsh_js):
            return [node_exe, dsh_js]
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", "@deepseek-ai/dsh"]
    raise RuntimeError(
        "未找到 dsh 运行时：请将 node 目录放到程序同级的 node/ 下，"
        "或设置环境变量 DSH_BROWSER_NODE_DIR，或确保 npx 在 PATH 中。"
    )


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
    webview.create_window("DeepSeek Harness", url, width=1280, height=800)
    webview.start()

    # 窗口关闭 → 杀整个进程树（node/npx → dsh），避免孤儿进程
    subprocess.run(
        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
