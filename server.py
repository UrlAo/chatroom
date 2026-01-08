import socket
import threading
import struct

# 保存在线客户端：socket -> username
clients = {}


def recv_all(sock, size):
    data = b''
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            return None
        data += packet
    return data


def recv_message(sock):
    raw_len = recv_all(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack('!I', raw_len)[0]
    return recv_all(sock, msg_len).decode()


def send_message(sock, message):
    data = message.encode()
    length = struct.pack('!I', len(data))
    sock.sendall(length + data)


def broadcast(message, exclude_socket=None):
    for client in clients:
        if client != exclude_socket:
            try:
                data = message.encode()
                length = struct.pack('!I', len(data))
                client.send(length + data)
            except:
                pass


def handle_client(client_socket, client_address):
    try:
        # 1. 接收用户名
        username = recv_message(client_socket)   # 接收用户名
        clients[client_socket] = username   # 保存客户端和用户名的映射
        print(f"{username} 上线了！")

        # 通知其他人
        broadcast(f"【系统】{username} 进入了聊天室", client_socket)

        while True:
            message = client_socket.recv(1024)
            if not message:
                break

            msg = message.decode()
            if msg == "/quit":
                # 客户端主动请求退出
                break
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


def server_console():
    """处理服务器控制台输入的函数"""
    while True:
        command = input("")  # 空提示符，直接等待输入

        # 分割命令和参数
        parts = command.strip().split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        if cmd == "list" or cmd == "online":
            online_users = list(clients.values())
            print(
                f"在线用户 ({len(online_users)}人): {', '.join(online_users) if online_users else '无'}")
        elif cmd == "help":
            print("可用命令:")
            print("  list/online - 查看在线用户")
            print("  count - 查看在线人数")
            print("  status - 查看服务器详细状态")
            print("  kick <用户名> - 踢出指定用户")
            print("  broadcast <消息> - 发送系统广播消息")
            print("  help - 显示此帮助信息")
        elif cmd == "count":
            print(f"当前在线人数: {len(clients)}")
        elif cmd == "status":
            print("服务器状态信息:")
            print(f"  在线人数: {len(clients)}")
            online_users = list(clients.values())
            if online_users:
                print(f"  在线用户: {', '.join(online_users)}")
            else:
                print("  在线用户: 无")
        elif cmd == "kick":
            if args:
                target_user = args[0]  # 目标用户名
                print(f"调试信息: 尝试踢出用户 '{target_user}'")  # 调试信息
                print(f"调试信息: 当前在线用户 {list(clients.values())}")  # 调试信息
                kicked = False  # 标记是否成功踢出用户
                # 使用 list(clients.items()) 创建快照以避免在迭代时修改字典
                for client_socket, username in list(clients.items()):  # 遍历客户端连接
                    # 调试信息
                    print(f"调试信息: 检查用户 '{username}' 与目标 '{target_user}'")
                    if username == target_user:
                        try:
                            # 先向被踢出的用户发送通知
                            try:
                                send_message(client_socket, "【系统】您已被管理员踢出聊天室")
                            except:
                                pass  # 如果发送失败也继续执行
                            # 通知其他用户该用户被踢出
                            broadcast(
                                f"【系统】{username} 被管理员踢出聊天室", client_socket)
                            client_socket.close()  # 关闭客户端连接
                            print(f"已踢出用户: {target_user}")
                            kicked = True
                            break
                        except Exception as e:
                            print(f"踢出用户 {target_user} 时出错: {e}")
                            break
                if not kicked:
                    print(f"用户 {target_user} 不在线或不存在")
            else:
                print("用法: kick <用户名>")
        elif cmd == "broadcast":
            if args:
                message = " ".join(args)
                broadcast(f"【系统广播】{message}")
                print(f"已发送系统广播: {message}")
            else:
                print("用法: broadcast <消息>")
        else:
            print(f"未知命令: {command}。输入 'help' 查看可用命令。")


# =============== 服务器启动 ===============
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("0.0.0.0", 8888))
server_socket.listen(5)

print("聊天室服务器启动，等待客户端连接...")
print("输入 'list', 'count', 'online', 'status', 'kick', 'broadcast' 或 'help' 查看和管理服务器状态")

# 启动服务器控制台线程
console_thread = threading.Thread(target=server_console, daemon=True)
console_thread.start()

while True:
    client_socket, client_address = server_socket.accept()
    threading.Thread(
        target=handle_client,
        args=(client_socket, client_address)
    ).start()
