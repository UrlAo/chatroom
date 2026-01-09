import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, filedialog
import socket
import threading
import struct
import os
import base64
import subprocess
import platform
from datetime import datetime


class ChatClientGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("聊天室客户端")
        self.master.geometry("800x600")

        # 设置连接变量
        self.client_socket = None
        self.connected = False
        self.current_chat = "聊天室"  # 当前聊天对象，默认为公共聊天室
        self.username = ""  # 初始化用户名

        # 存储不同聊天对象的消息（消息格式：字符串或字典{"type": "file", "text": "...", "file_path": "..."}）
        self.chat_history = {"聊天室": []}
        
        # 创建文件存储目录
        self.files_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "received_files")
        if not os.path.exists(self.files_dir):
            os.makedirs(self.files_dir)
        
        # 文件路径映射（tag_id -> file_path）
        self.file_path_map = {}
        self.file_tag_counter = 0

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

        # 主框架（左右分栏）
        main_frame = tk.PanedWindow(self.master, orient=tk.HORIZONTAL)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧框架（用户列表）
        left_frame = tk.Frame(main_frame)
        main_frame.add(left_frame, width=200)

        # 用户列表标签
        users_label = tk.Label(left_frame, text="在线用户:")
        users_label.pack(anchor="w")

        # 用户列表框
        self.users_listbox = tk.Listbox(left_frame)
        self.users_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 添加“聊天室”选项
        self.users_listbox.insert(tk.END, "聊天室")

        # 绑定点击事件
        self.users_listbox.bind("<<ListboxSelect>>", self.select_chat_target)

        # 右侧框架（聊天区域）
        right_frame = tk.Frame(main_frame)
        main_frame.add(right_frame)

        # 当前聊天对象标签
        self.current_chat_label = tk.Label(right_frame, text="当前聊天: 聊天室")
        self.current_chat_label.pack(anchor="w")

        # 消息显示区域
        self.messages_display = scrolledtext.ScrolledText(
            right_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=20
        )
        self.messages_display.pack(
            fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 配置文件链接的tag样式
        self.messages_display.tag_config("file_link", foreground="blue", underline=True)
        # 绑定点击事件和鼠标悬停事件
        self.messages_display.tag_bind("file_link", "<Button-1>", self.on_file_link_click)
        self.messages_display.tag_bind("file_link", "<Enter>", self.on_file_link_enter)
        self.messages_display.tag_bind("file_link", "<Leave>", self.on_file_link_leave)

        # 输入区域
        input_frame = tk.Frame(right_frame)
        input_frame.pack(fill=tk.X)

        self.message_label = tk.Label(input_frame, text="输入消息:")
        self.message_label.pack(anchor="w")

        self.message_entry = tk.Entry(input_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X,
                                expand=True, padx=(0, 5))
        self.message_entry.bind("<Return>", self.send_message)

        # 按钮框架
        button_frame = tk.Frame(input_frame)
        button_frame.pack(side=tk.RIGHT)
        
        self.send_button = tk.Button(
            button_frame, text="发送", command=self.send_message)
        self.send_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.send_file_button = tk.Button(
            button_frame, text="发送文件", command=self.send_file)
        self.send_file_button.pack(side=tk.LEFT)

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
            self.add_message_to_history("聊天室", "系统: 已成功连接到聊天室")

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
            self.add_message_to_history("聊天室", "系统: 已断开与聊天室的连接")

    def send_message(self, event=None):  # 发送消息
        if not self.connected:
            messagebox.showwarning("警告", "未连接到服务器！")
            return

        message = self.message_entry.get().strip()  # 获取输入消息并去除首尾空格
        if message:
            try:
                # 在本地显示自己的消息
                self.add_message_to_history("聊天室", f"{self.username}：{message}")

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
        self.client_socket.sendall(length + data)
        # self 代表类的当前实例（对象）
        # 它是类中方法的第一个参数，指向调用该方法的具体对象
    
    def send_file(self):
        """发送文件功能"""
        if not self.connected:
            messagebox.showwarning("警告", "未连接到服务器！")
            return
        
        # 选择文件
        file_path = filedialog.askopenfilename(
            title="选择要发送的文件",
            filetypes=[("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # 读取文件
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # 获取文件名（不包含路径）
            filename = os.path.basename(file_path)
            file_size = len(file_data)
            
            # 将文件数据编码为base64
            file_data_base64 = base64.b64encode(file_data).decode('utf-8')
            
            # 构建文件传输消息：/FILE|filename|filesize|base64data
            file_message = f"/FILE|{filename}|{file_size}|{file_data_base64}"
            
            # 发送文件消息
            self.send_message_raw(file_message)
            
            # 保存发送的文件路径（用于后续点击打开）
            file_info = {
                "type": "file",
                "text": f"{self.username}：[文件] {filename} ({self.format_file_size(file_size)})",
                "file_path": file_path,
                "filename": filename,
                "sender": self.username
            }
            self.add_message_to_history("聊天室", file_info)
            
        except Exception as e:
            messagebox.showerror("发送文件错误", f"发送文件失败: {str(e)}")
    
    def format_file_size(self, size):
        """格式化文件大小显示"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"

    def receive_messages(self):
        """接收来自服务器的消息"""
        while self.connected:
            try:
                # 接收消息长度
                raw_len = self.recv_all(4)
                if not raw_len:
                    self.add_message_to_history("聊天室", "系统: 服务器连接已关闭")
                    break

                msg_len = struct.unpack('!I', raw_len)[0]

                # 接收消息内容
                message = self.recv_all(msg_len).decode()

                # 解析消息类型并处理
                self.process_received_message(message)
                # 检查是否是文件传输消息
                # 可能是直接 "/FILE|..." 或 "username：/FILE|..."
                if "/FILE|" in message:
                    # 在主线程中处理文件接收
                    self.master.after(0, self.handle_file_receive, message)
                # 注意：process_received_message 已经处理了消息添加到历史记录

            except Exception as e:
                if self.connected:
                    error_msg = f"接收消息时出错: {str(e)} (类型: {type(e).__name__})"
                    self.add_message_to_history("聊天室", f"系统: {error_msg}")
                    self.master.after(0, self.handle_connection_error, str(e))
                break
    
    def handle_file_receive(self, file_message):
        """处理接收到的文件"""
        try:
            # 服务器广播的格式可能是 "username：/FILE|..." 或直接是 "/FILE|..."
            # 提取发送者用户名（如果有）
            sender_name = None
            file_content = file_message
            
            if "：" in file_message or ":" in file_message:
                # 查找冒号分隔符（中文或英文）
                separator = "：" if "：" in file_message else ":"
                parts_msg = file_message.split(separator, 1)
                if len(parts_msg) == 2:
                    sender_name = parts_msg[0].strip()
                    file_content = parts_msg[1].strip()
            
            # 解析文件消息：/FILE|filename|filesize|base64data
            if not file_content.startswith("/FILE|"):
                self.add_message_to_history("聊天室", "系统: 文件消息格式错误")
                return
            
            parts = file_content.split("|", 3)
            if len(parts) != 4:
                self.add_message_to_history("聊天室", "系统: 文件消息格式错误")
                return
            
            command, filename, file_size_str, file_data_base64 = parts
            
            # 解析文件大小
            try:
                file_size = int(file_size_str)
            except ValueError:
                self.add_message_to_history("聊天室", "系统: 文件大小格式错误")
                return
            
            # 解码base64数据
            try:
                file_data = base64.b64decode(file_data_base64)
            except Exception as e:
                self.add_message_to_history("聊天室", f"系统: 文件数据解码失败: {str(e)}")
                return
            
            # 验证文件大小
            if len(file_data) != file_size:
                self.add_message_to_history("聊天室", f"系统: 文件大小不匹配 (期望: {file_size}, 实际: {len(file_data)})")
                return
            
            # 检查是否是自己的文件（服务器会广播给所有客户端，包括发送者）
            is_own_file = sender_name and sender_name == getattr(self, 'username', None)
            
            # 自动保存文件到固定目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 处理文件名，避免冲突
            name, ext = os.path.splitext(filename)
            safe_filename = f"{timestamp}_{name}{ext}"
            save_path = os.path.join(self.files_dir, safe_filename)
            
            # 保存文件
            with open(save_path, 'wb') as f:
                f.write(file_data)
            
            # 显示接收提示
            sender_info = f"{sender_name} 发送了" if sender_name else "收到"
            file_size_formatted = self.format_file_size(file_size)
            
            # 确定聊天目标（群聊或私聊）
            chat_target = "聊天室"
            if sender_name and sender_name != self.username:
                # 如果是私聊，可能需要检查消息来源
                # 这里暂时都放到聊天室，可以根据实际需求调整
                pass
            
            if is_own_file:
                # 如果是自己的文件，显示提示并保存文件信息
                file_info = {
                    "type": "file",
                    "text": f"{self.username}：[文件] {filename} ({file_size_formatted})",
                    "file_path": save_path,
                    "filename": filename,
                    "sender": self.username
                }
                self.add_message_to_history(chat_target, file_info)
            else:
                # 其他用户发送的文件
                file_info = {
                    "type": "file",
                    "text": f"{sender_info}文件 {filename} ({file_size_formatted})",
                    "file_path": save_path,
                    "filename": filename,
                    "sender": sender_name or "未知"
                }
                self.add_message_to_history(chat_target, file_info)
            
        except Exception as e:
            error_msg = f"接收文件时出错: {str(e)}"
            self.add_message_to_history("聊天室", f"系统: {error_msg}")
            messagebox.showerror("接收文件错误", error_msg)

    def process_received_message(self, message):
        """处理接收到的消息"""
        # 检查是否是系统消息（如用户上下线通知）
        if message.startswith("【系统】"):
            # 系统消息添加到聊天室
            self.add_message_to_history("聊天室", message)
        elif message.startswith("[私聊"):
            # 私聊消息
            # 提取发送者用户名
            sender_start = message.find("[私聊来自") + 5  # "[私聊来自"的长度
            if sender_start > 4:  # 确保找到了标记
                sender_end = message.find("]", sender_start)
                if sender_end > sender_start:
                    sender = message[sender_start:sender_end]
                    # 添加到该用户的私聊历史
                    self.add_message_to_history(sender, message)
        elif message.startswith("【系统广播】"):
            # 系统广播消息，添加到所有聊天（包括私聊）
            # 添加到聊天室
            self.add_message_to_history("聊天室", message)
            # 添加到所有私聊对话
            for chat_target in self.chat_history:
                if chat_target != "聊天室":
                    self.add_message_to_history(chat_target, message)
        else:
            # 普通群聊消息
            self.add_message_to_history("聊天室", message)

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
        self.add_message_to_history("聊天室", f"系统: 连接错误 - {error_msg}")
        messagebox.showerror("连接错误", f"与服务器的连接已断开: {error_msg}")

    def update_status(self, status_text):
        """更新状态栏"""
        self.status_bar.config(text=status_text)

    def select_chat_target(self, event):
        """选择聊天对象"""
        selection = self.users_listbox.curselection()
        if selection:
            target = self.users_listbox.get(selection[0])
            if target != self.current_chat:
                self.current_chat = target
                self.current_chat_label.config(text=f"当前聊天: {target}")
                self.refresh_message_display()

    def refresh_message_display(self):
        """刷新消息显示区域"""
        # 清空当前显示和文件路径映射
        self.messages_display.config(state=tk.NORMAL)
        self.messages_display.delete(1.0, tk.END)
        # 清空文件路径映射（刷新时重建）
        self.file_path_map.clear()
        self.file_tag_counter = 0

        # 获取当前聊天对象的历史消息
        if self.current_chat in self.chat_history:
            for msg in self.chat_history[self.current_chat]:
                self.insert_message_to_display(msg)

        # 滚动到底部
        self.messages_display.see(tk.END)
        self.messages_display.config(state=tk.DISABLED)

    def insert_message_to_display(self, msg):
        """将消息插入到显示区域（支持文件链接）"""
        if isinstance(msg, dict) and msg.get("type") == "file":
            # 文件消息，显示为可点击的链接
            text = msg["text"]
            file_path = msg.get("file_path", "")
            # 提取文件名部分，使其可点击
            # 格式可能是："username：[文件] filename (size)" 或 "系统: 收到文件 filename (size)"
            # 找到文件名位置
            if "[文件]" in text:
                parts = text.split("[文件]")
                prefix = parts[0] + "[文件] "
                filename_part = parts[1].split(" (")[0]  # 提取文件名（去掉大小部分）
                size_part = " (" + " (".join(parts[1].split(" (")[1:])  # 提取大小部分
                
                # 插入前缀
                self.messages_display.insert(tk.END, prefix)
                # 插入可点击的文件名
                start_pos = self.messages_display.index(tk.END + "-1c")
                self.messages_display.insert(tk.END, filename_part)
                end_pos = self.messages_display.index(tk.END + "-1c")
                # 生成唯一的tag ID
                tag_id = f"file_tag_{self.file_tag_counter}"
                self.file_tag_counter += 1
                # 存储文件路径映射
                self.file_path_map[tag_id] = file_path
                # 应用tag
                self.messages_display.tag_add("file_link", start_pos, end_pos)
                self.messages_display.tag_add(tag_id, start_pos, end_pos)
                # 插入大小部分
                self.messages_display.insert(tk.END, size_part)
            else:
                # 如果格式不匹配，直接显示文本
                self.messages_display.insert(tk.END, text)
        else:
            # 普通文本消息
            text = msg if isinstance(msg, str) else str(msg)
            self.messages_display.insert(tk.END, text)
        
        self.messages_display.insert(tk.END, "\n")
    
    def add_message_to_history(self, chat_target, message):
        """添加消息到历史记录"""
        if chat_target not in self.chat_history:
            self.chat_history[chat_target] = []
        self.chat_history[chat_target].append(message)

        # 如果当前正在查看这个聊天对象，则更新显示
        if self.current_chat == chat_target:
            self.messages_display.config(state=tk.NORMAL)
            self.insert_message_to_display(message)
            self.messages_display.see(tk.END)
            self.messages_display.config(state=tk.DISABLED)
    
    def on_file_link_enter(self, event):
        """鼠标进入文件链接区域"""
        self.messages_display.config(cursor="hand2")
    
    def on_file_link_leave(self, event):
        """鼠标离开文件链接区域"""
        self.messages_display.config(cursor="")
    
    def on_file_link_click(self, event):
        """处理文件链接点击事件"""
        # 获取点击位置的索引
        index = self.messages_display.index(f"@{event.x},{event.y}")
        
        # 查找该位置的所有tag
        tags = self.messages_display.tag_names(index)
        
        # 查找文件路径tag
        file_path = None
        for tag in tags:
            if tag.startswith("file_tag_"):
                file_path = self.file_path_map.get(tag)
                break
        
        if file_path and os.path.exists(file_path):
            # 使用系统默认程序打开文件
            try:
                if platform.system() == 'Windows':
                    os.startfile(file_path)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', file_path])
                else:  # Linux
                    subprocess.run(['xdg-open', file_path])
            except Exception as e:
                messagebox.showerror("打开文件错误", f"无法打开文件: {str(e)}")
        else:
            if file_path:
                messagebox.showwarning("文件不存在", f"文件不存在或已被删除:\n{file_path}")

    def update_users_list(self, users_list):
        """更新用户列表"""
        # 清空当前列表（保留“聊天室”选项）
        self.users_listbox.delete(0, tk.END)
        self.users_listbox.insert(tk.END, "聊天室")

        # 添加在线用户（排除自己）
        for user in users_list:
            if user != self.username:  # 不显示自己
                self.users_listbox.insert(tk.END, user)

    def send_message(self, event=None):  # 发送消息
        if not self.connected:
            messagebox.showwarning("警告", "未连接到服务器！")
            return

        message = self.message_entry.get().strip()  # 获取输入消息并去除首尾空格
        if message:
            try:
                # 如果当前聊天对象是“聊天室”，则发送群聊消息
                if self.current_chat == "聊天室":
                    # 在本地显示自己的消息
                    self.add_message_to_history(
                        "聊天室", f"{self.username}：{message}")

                    self.send_message_raw(message)
                else:
                    # 发送私聊消息
                    private_message = f"@{self.current_chat} {message}"
                    # 在本地显示私聊消息
                    self.add_message_to_history(
                        self.current_chat, f"[私聊给{self.current_chat}] {self.username}：{message}")

                    self.send_message_raw(private_message)

                self.message_entry.delete(0, tk.END)

                # 如果是退出命令，断开连接
                if message.lower() == "offline":
                    self.disconnect_from_server()

            except Exception as e:
                messagebox.showerror("发送错误", f"发送消息失败: {str(e)}")

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
