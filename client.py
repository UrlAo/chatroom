import socket
import threading

def receive_message(client_socket):
    while True:
        try:
            message = client_socket.recv(1024)
            if message:
                print(message.decode())
        except:
            break

# ================= 客户端启动 =================
username = input("请输入你的用户名：")

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect(("127.0.0.1", 8888))

# 发送用户名
client_socket.send(username.encode())

print("已进入聊天室，输入消息并回车发送")
print("输入 /online 查看当前在线用户")

# 启动接收线程
thread = threading.Thread(
    target=receive_message,
    args=(client_socket,)
)
thread.daemon = True
thread.start()

# 发送消息
while True:
    msg = input()
    client_socket.send(msg.encode())
