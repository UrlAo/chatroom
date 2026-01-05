import socket
import threading

# 保存在线客户端：socket -> username
clients = {}

def handle_client(client_socket, client_address):
    try:
        # 1. 接收用户名
        username = client_socket.recv(1024).decode()
        clients[client_socket] = username
        print(f"{username} 上线了")

        # 通知其他人
        broadcast(f"【系统】{username} 进入了聊天室", client_socket)

        while True:
            message = client_socket.recv(1024)
            if not message:
                break

            msg = message.decode()
            # 处理在线用户列表命令
            if msg == "/online":
                online_list = ", ".join(clients.values())
                client_socket.send(f"【在线用户】{online_list}".encode())
            else:
                print(f"{username}：{msg}")
                broadcast(f"{username}：{msg}", client_socket)

    except:
        pass
    finally:
        # 客户端下线
        if client_socket in clients:
            name = clients[client_socket]
            print(f"{name} 下线了")
            broadcast(f"【系统】{name} 离开了聊天室", client_socket)
            del clients[client_socket]

        client_socket.close()

def broadcast(message, exclude_socket=None):
    for client in clients:
        if client != exclude_socket:
            try:
                client.send(message.encode())
            except:
                pass

# ================= 服务器启动 =================
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("127.0.0.1", 8888))
server_socket.listen(5)

print("聊天室服务器启动，等待客户端连接...")

while True:
    client_socket, client_address = server_socket.accept()
    threading.Thread(
        target=handle_client,
        args=(client_socket, client_address)
    ).start()
