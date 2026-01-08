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

#sock 是一个 socket 对象的变量名，代表一个网络连接端点

    
def recv_message(sock):    # 接收消息
    raw_len = recv_all(sock, 4) 
    # 调用 recv_all 函数从 socket 接收 4 个字节的数据
    # 这 4 个字节是消息长度信息（由 send_message 发送的长度前缀）
    # 将接收到的长度字节数据保存到 raw_len 变量
    if not raw_len:
        return None
    msg_len = struct.unpack('!I', raw_len)[0]
    # 使用 struct.unpack 将 4 字节的长度数据解包为整数
    # '!I' 格式：! 表示网络字节序（大端序），I 表示无符号整数
    # [0] 获取解包结果的第一个元素（因为 unpack 返回元组）
    return recv_all(sock, msg_len).decode()
    # 根据解包得到的 msg_len（消息长度），接收对应长度的消息内容
    # 调用 recv_all(sock, msg_len) 确保接收到完整的消息数据
    # 使用 .decode() 将字节数据转换为字符串
# 返回解码后的消息字符串


def send_message(sock, message):    # 发送消息
    data = message.encode()    # 将消息编码为二进制数据
    length = struct.pack('!I', len(data)) # 将数据长度打包成4字节的二进制数据
    sock.sendall(length + data)    # 发送数据长度和数据


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
