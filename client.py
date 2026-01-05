import socket
import threading
import struct
import os
#我是张东健
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

def receive_thread(sock):
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
client_socket.connect(("192.168.110.64", 8888))

# 发送用户名
send_message(client_socket, username)

print("已进入聊天室，输入消息并回车发送")
print("输入/online 查看当前在线用户。")

# 启动接收线程
threading.Thread(
    target=receive_thread,
    args=(client_socket,),
    daemon=True
).start()

# 发送消息
while True:
    msg = input()
    client_socket.send(msg.encode())