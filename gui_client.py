import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import socket
import threading
import struct


class ChatClientGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("聊天室客户端")
        self.master.geometry("600x500")

        # 设置连接变量
        self.client_socket = None
        self.connected = False

        # 创建界面组件
        self.create_widgets()

    def create_widgets(self):
        # 创建菜单栏
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        # 连接菜单
        connection_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="连接", menu=connection_menu)
        connection_menu.add_command(
            label="连接到服务器", command=self.connect_to_server)
        connection_menu.add_command(
            label="断开连接", command=self.disconnect_from_server)

        # 主框架
        main_frame = tk.Frame(self.master)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 消息显示区域
        self.messages_label = tk.Label(main_frame, text="聊天消息:")
        self.messages_label.pack(anchor="w")

        self.messages_display = scrolledtext.ScrolledText(   # 消息显示区域
            main_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=20
        )
        self.messages_display.pack(
            fill=tk.BOTH, expand=True, pady=(0, 10))  # 消息显示区域

        # 输入区域
        input_frame = tk.Frame(main_frame)
        input_frame.pack(fill=tk.X)

        self.message_label = tk.Label(input_frame, text="输入消息:")
        self.message_label.pack(anchor="w")

        self.message_entry = tk.Entry(input_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X,
                                expand=True, padx=(0, 5))
        self.message_entry.bind("<Return>", self.send_message)

        self.send_button = tk.Button(
            input_frame, text="发送", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT)

        # 状态栏
        self.status_bar = tk.Label(
            self.master,
            text="未连接",
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.master.config(cursor="arrow")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 绑定窗口关闭事件
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def connect_to_server(self):
        if self.connected:
            messagebox.showwarning("警告", "已经连接到服务器！")
            return

        # 获取用户名
        username = simpledialog.askstring("用户名", "请输入您的用户名:")
        if not username:
            return

        # 获取服务器地址和端口
        server_ip = simpledialog.askstring(
            "服务器地址", "请输入服务器IP地址:", initialvalue="127.0.0.1")
        if not server_ip:
            return

        try:
            server_port_str = simpledialog.askstring(
                "服务器端口", "请输入服务器端口号:", initialvalue="8888")
            if not server_port_str:
                return
            server_port = int(server_port_str)
        except ValueError:
            messagebox.showerror("错误", "无效的端口号！")
            return

        try:
            # 创建连接
            self.client_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((server_ip, server_port))

            # 保存用户名
            self.username = username
            # 发送用户名
            self.send_message_raw(username)

            self.connected = True   # ★关键：一定要在启动线程前

            # 启动接收线程
            self.receive_thread = threading.Thread(
                target=self.receive_messages, daemon=True)
            self.receive_thread.start()

            self.update_status(
                f"已连接到 {server_ip}:{server_port} - 用户名: {username}")
            self.append_message("系统: 已成功连接到聊天室")

        except Exception as e:
            messagebox.showerror("连接错误", f"无法连接到服务器: {str(e)}")
            if self.client_socket:
                self.client_socket.close()

    def disconnect_from_server(self):
        if not self.connected:
            messagebox.showinfo("信息", "当前未连接到服务器！")
            return

        try:
            # 发送退出消息
            self.send_message_raw("/quit")
        except:
            pass
        finally:
            self.connected = False
            if self.client_socket:
                self.client_socket.close()
            self.update_status("已断开连接")
            self.append_message("系统: 已断开与聊天室的连接")

    def send_message(self, event=None):  # 发送消息
        if not self.connected:
            messagebox.showwarning("警告", "未连接到服务器！")
            return

        message = self.message_entry.get().strip()  # 获取输入消息并去除首尾空格
        if message:
            try:
                # 在本地显示自己的消息
                self.append_message(f"{self.username}：{message}")

                self.send_message_raw(message)
                self.message_entry.delete(0, tk.END)

                # 如果是退出命令，断开连接
                if message.lower() == "offline":
                    self.disconnect_from_server()

            except Exception as e:
                messagebox.showerror("发送错误", f"发送消息失败: {str(e)}")

    def send_message_raw(self, message):  # 发送原始消息
        """发送原始消息到服务器"""
        data = message.encode()
        length = struct.pack('!I', len(data))
        self.client_socket.send(length + data)
        # self 代表类的当前实例（对象）
        # 它是类中方法的第一个参数，指向调用该方法的具体对象

    def receive_messages(self):
        """接收来自服务器的消息"""
        while self.connected:
            try:
                # 接收消息长度
                raw_len = self.recv_all(4)
                if not raw_len:
                    self.append_message("系统: 服务器连接已关闭")
                    break

                msg_len = struct.unpack('!I', raw_len)[0]

                # 接收消息内容
                message = self.recv_all(msg_len).decode()

                # 在主线程中更新UI
                self.master.after(0, self.append_message, message, False)

            except Exception as e:
                if self.connected:
                    error_msg = f"接收消息时出错: {str(e)} (类型: {type(e).__name__})"
                    self.append_message(f"系统: {error_msg}")
                    self.master.after(0, self.handle_connection_error, str(e))
                break

    def recv_all(self, size):
        """接收指定长度的数据"""
        data = b''
        while len(data) < size:
            packet = self.client_socket.recv(size - len(data))
            if not packet:
                return None
            data += packet
        return data

    def append_message(self, message, is_debug=False):
        """在消息显示区域追加消息"""
        self.messages_display.config(state=tk.NORMAL)
        self.messages_display.insert(tk.END, message + "\n")
        self.messages_display.see(tk.END)  # 自动滚动到底部
        self.messages_display.config(state=tk.DISABLED)

    def handle_connection_error(self, error_msg):
        """处理连接错误"""
        self.connected = False
        self.update_status("连接已断开")
        self.append_message(f"系统: 连接错误 - {error_msg}")
        messagebox.showerror("连接错误", f"与服务器的连接已断开: {error_msg}")

    def update_status(self, status_text):
        """更新状态栏"""
        self.status_bar.config(text=status_text)

    def on_closing(self):
        """窗口关闭事件处理"""
        if self.connected:
            self.disconnect_from_server()
        self.master.destroy()


def main():
    root = tk.Tk()
    app = ChatClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
