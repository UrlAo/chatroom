import subprocess
import sys
import os
import time

python_exe = sys.executable
base_dir = os.path.dirname(os.path.abspath(__file__))

server_path = os.path.join(base_dir, "gui_server.py")
client_path = os.path.join(base_dir, "gui_client.py")

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW

# 1️⃣ 启动服务器（无终端）
subprocess.Popen(
    [python_exe, server_path],
    creationflags=CREATE_NO_WINDOW
)

time.sleep(2)

# 2️⃣ 启动 3 个客户端（无终端）
for _ in range(2):
    subprocess.Popen(
        [python_exe, client_path],
        creationflags=CREATE_NO_WINDOW
    )
    time.sleep(1)
