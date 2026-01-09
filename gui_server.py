import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import socket
import threading
import struct


class ChatServerGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("聊天室服务器")
        self.master.geometry("600x500")

        # 服务器状态变量
        self.server_socket = None
        self.running = False
        self.clients = {}  # 存储客户端连接：socket -> username

        # 创建界面组件
        self.create_widgets()

    def create_widgets(self):
        # 创建菜单栏
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        # 服务器菜单
        server_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="服务器", menu=server_menu)
        server_menu.add_command(
            label="启动服务器", command=self.start_server)
        server_menu.add_command(
            label="停止服务器", command=self.stop_server)

        # 主框架
        main_frame = tk.Frame(self.master)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 消息显示区域
        self.messages_label = tk.Label(main_frame, text="服务器日志:")
        self.messages_label.pack(anchor="w")

        self.messages_display = scrolledtext.ScrolledText(   # 消息显示区域
            main_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=15
        )
        self.messages_display.pack(
            fill=tk.BOTH, expand=True, pady=(0, 10))  # 消息显示区域

        # 客户端列表区域
        self.clients_label = tk.Label(main_frame, text="在线用户:")
        self.clients_label.pack(anchor="w")

        self.clients_listbox = tk.Listbox(main_frame, height=6)
        self.clients_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 控制按钮区域
        control_frame = tk.Frame(main_frame)
        control_frame.pack(fill=tk.X)

        self.kick_button = tk.Button(
            control_frame, text="踢出选中用户", command=self.kick_selected_user)
        self.kick_button.pack(side=tk.LEFT, padx=(0, 5))

        self.broadcast_button = tk.Button(
            control_frame, text="发送系统广播", command=self.send_broadcast)
        self.broadcast_button.pack(side=tk.LEFT)

        # 状态栏
        self.status_bar = tk.Label(
            self.master,
            text="服务器未启动",
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.master.config(cursor="arrow")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 绑定窗口关闭事件
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start_server(self):
        if self.running:
            messagebox.showwarning("警告", "服务器已经在运行！")
            return

        # 获取端口号
        port_str = simpledialog.askstring(
            "服务器端口", "请输入服务器端口号:", initialvalue="8888")
        if not port_str:
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("错误", "无效的端口号！")
            return

        try:
            # 创建服务器套接字
            self.server_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", port))
            self.server_socket.listen(5)

            self.running = True

            # 启动服务器监听线程
            self.server_thread = threading.Thread(
                target=self.accept_clients, daemon=True)
            self.server_thread.start()

            self.update_status(f"服务器正在运行，端口: {port}")
            self.append_message("系统: 服务器已启动，等待客户端连接...")

        except Exception as e:
            messagebox.showerror("启动错误", f"无法启动服务器: {str(e)}")
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            self.running = False

    def stop_server(self):
        if not self.running:
            messagebox.showinfo("信息", "服务器未运行！")
            return

        try:
            self.running = False

            # 关闭所有客户端连接
            for client_socket in list(self.clients.keys()):
                try:
                    client_socket.close()
                except:
                    pass

            # 清空客户端列表
            self.clients.clear()
            self.update_client_list()

            # 关闭服务器套接字
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None

            self.update_status("服务器已停止")
            self.append_message("系统: 服务器已停止")

        except Exception as e:
            messagebox.showerror("停止错误", f"停止服务器时出错: {str(e)}")

    def accept_clients(self):
        """接受客户端连接"""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()

                # 启动处理客户端的线程
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()

            except Exception as e:
                if self.running:  # 如果服务器仍在运行，则显示错误
                    self.append_message(f"接受连接时出错: {str(e)}")
                break

    def handle_client(self, client_socket, client_address):
        """处理单个客户端"""
        try:
            # 1. 接收用户名
            username = self.recv_message(client_socket)
            if not username:
                client_socket.close()
                return

            # 保存客户端和用户名的映射
            self.clients[client_socket] = username

            # 更新客户端列表
            self.master.after(0, self.update_client_list)

            self.append_message(
                f"{username} ({client_address[0]}:{client_address[1]}) 上线了！")

            # 通知其他人
            self.broadcast(f"【系统】{username} 进入了聊天室", client_socket)

            # 循环接收消息
            while self.running:
                msg = self.recv_message(client_socket)
                if not msg or msg == "/quit":
                    break

                # 检查是否是私聊消息（格式：@用户名 消息内容）
                if msg.startswith('@'):
                    # 解析私聊消息
                    parts = msg.split(' ', 1)
                    if len(parts) >= 2:
                        target_user = parts[0][1:]  # 移除@符号
                        private_msg = parts[1]

                        # 检查目标用户是否存在
                        target_exists = any(
                            u == target_user for u in self.clients.values())
                        if target_exists:
                            # 发送给目标用户
                            sender_msg = f"[私聊给{target_user}] {username}：{private_msg}"
                            receiver_msg = f"[私聊来自{username}] {username}：{private_msg}"

                            # 发送给发送者
                            self.send_to_user(username, sender_msg)
                            # 发送给接收者
                            self.send_to_user(target_user, receiver_msg)

                            self.append_message(
                                f"{username} 私聊 {target_user}：{private_msg}")
                        else:
                            # 目标用户不存在，发送错误消息给发送者
                            error_msg = f"【系统】错误：用户 {target_user} 不在线"
                            self.send_to_user(username, error_msg)
                            self.append_message(
                                f"{username} 尝试私聊 {target_user}（用户不在线）")
                    else:
                        # 格式不正确，当作普通消息处理
                        self.append_message(f"{username}：{msg}")
                        self.broadcast(f"{username}：{msg}", client_socket)
                else:
                    # 普通群聊消息
                    self.append_message(f"{username}：{msg}")
                    self.broadcast(f"{username}：{msg}", client_socket)

        except Exception as e:
            if self.running:
                self.append_message(f"处理客户端 {client_address} 时出错: {str(e)}")

        finally:
            # 客户端下线
            if client_socket in self.clients:
                username = self.clients[client_socket]
                del self.clients[client_socket]

                # 更新客户端列表
                self.master.after(0, self.update_client_list)

                self.append_message(f"{username} 下线了")
                self.broadcast(f"【系统】{username} 离开了聊天室", client_socket)

            client_socket.close()

    def recv_all(self, sock, size):
        """接收指定长度的数据"""
        data = b''
        while len(data) < size:
            packet = sock.recv(size - len(data))
            if not packet:
                return None
            data += packet
        return data

    def recv_message(self, sock):
        """接收消息"""
        raw_len = self.recv_all(sock, 4)
        if not raw_len:
            return None
        msg_len = struct.unpack('!I', raw_len)[0]
        return self.recv_all(sock, msg_len).decode()

    def send_message(self, sock, message):
        """发送消息"""
        data = message.encode()
        length = struct.pack('!I', len(data))
        sock.sendall(length + data)

    def send_to_user(self, target_username, message):
        """发送消息给指定用户"""
        for client_socket, username in self.clients.items():
            if username == target_username:
                try:
                    data = message.encode()
                    length = struct.pack('!I', len(data))
                    client_socket.send(length + data)
                    return True
                except:
                    return False
        return False

    def broadcast(self, message, exclude_socket=None):
        """广播消息给所有客户端"""
        disconnected_clients = []

        for client in self.clients:
            if client != exclude_socket:
                try:
                    data = message.encode()
                    length = struct.pack('!I', len(data))
                    client.send(length + data)
                except:
                    # 记录断开的客户端，稍后清理
                    disconnected_clients.append(client)

        # 清理断开的连接
        for client in disconnected_clients:
            if client in self.clients:
                username = self.clients[client]
                del self.clients[client]
                self.append_message(f"{username} 因发送消息失败而断开连接")

        # 更新客户端列表
        if disconnected_clients:
            self.master.after(0, self.update_client_list)

    def update_client_list(self):
        """更新客户端列表显示"""
        self.clients_listbox.delete(0, tk.END)
        for username in self.clients.values():
            self.clients_listbox.insert(tk.END, username)

    def kick_selected_user(self):
        """踢出选中的用户"""
        selection = self.clients_listbox.curselection()
        if not selection:
            messagebox.showinfo("信息", "请选择要踢出的用户！")
            return

        selected_username = self.clients_listbox.get(selection[0])

        # 找到对应的客户端套接字
        client_socket_to_kick = None
        for client_socket, username in self.clients.items():
            if username == selected_username:
                client_socket_to_kick = client_socket
                break

        if client_socket_to_kick:
            try:
                # 向被踢出的用户发送通知
                self.send_message(client_socket_to_kick, "【系统】您已被管理员踢出聊天室")
            except:
                pass  # 如果发送失败也继续执行

            # 通知其他用户该用户被踢出
            self.broadcast(
                f"【系统】{selected_username} 被管理员踢出聊天室", client_socket_to_kick)

            # 关闭客户端连接
            client_socket_to_kick.close()

            self.append_message(f"已踢出用户: {selected_username}")

    def send_broadcast(self):
        """发送系统广播"""
        message = simpledialog.askstring("系统广播", "请输入要广播的消息:")
        if message:
            broadcast_msg = f"【系统广播】{message}"
            self.broadcast(broadcast_msg)
            self.append_message(f"系统广播: {message}")

    def append_message(self, message):
        """在消息显示区域追加消息"""
        self.messages_display.config(state=tk.NORMAL)
        self.messages_display.insert(tk.END, message + "\n")
        self.messages_display.see(tk.END)  # 自动滚动到底部
        self.messages_display.config(state=tk.DISABLED)

    def update_status(self, status_text):
        """更新状态栏"""
        self.status_bar.config(text=status_text)

    def on_closing(self):
        """窗口关闭事件处理"""
        if self.running:
            self.stop_server()
        self.master.destroy()


def main():
    root = tk.Tk()
    app = ChatServerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
