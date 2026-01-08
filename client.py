import socket
import threading
import struct


def recv_all(sock, size):  # 接收指定长度的数据
    data = b''              # 接收的数据
    while len(data) < size:     # 当接收到的数据长度小于指定长度时，继续接收
        packet = sock.recv(size - len(data))      # 接收数据包
        if not packet:
            return None
        data += packet
    return data


def recv_message(sock):    # 接收消息
    raw_len = recv_all(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack('!I', raw_len)[0]
    return recv_all(sock, msg_len).decode()

    
def recv_message(sock):    # 接收消息
    raw_len = recv_all(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack('!I', raw_len)[0]
    return recv_all(sock, msg_len).decode()


def send_message(sock, message):    # 发送消息
    data = message.encode()
    length = struct.pack('!I', len(data))
    sock.sendall(length + data)


def receive_thread(sock):     # 接收线程
    while True:
        try:
            msg = recv_message(sock)
            if msg:
                print(msg)
            else:
                break
        except:
            break


# =============== 客户端启动 ===================
username = input("请输入你的用户名：")

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect(("127.0.0.1", 8888))    # 连接服务器

# 发送用户名
send_message(client_socket, username)

print("已进入聊天室，输入消息并回车发送")


# 启动接收线程
threading.Thread(
    target=receive_thread,
    args=(client_socket,),
    daemon=True
).start()

# 发送消息
while True:
    msg = input()
    if msg.lower() == "offline":
        send_message(client_socket, "/quit")  # 发送一个特殊消息通知服务器要退出
        break
    send_message(client_socket, msg)

# 关闭连接
client_socket.close()
print("已退出聊天室")
