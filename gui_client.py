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
import cv2
import numpy as np
import json
try:
    import pygame
    pygame.mixer.init()
except ImportError:
    pygame = None


class ChatClientGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("聊天室客户端")
        self.master.geometry("900x700")
        # 设置微信风格配色
        self.master.configure(bg="#F5F5F5")

        # 设置连接变量
        self.client_socket = None
        self.connected = False
        self.current_chat = "聊天室"  # 当前聊天对象，默认为公共聊天室
        self.username = ""  # 初始化用户名

        # 存储不同聊天对象的消息（消息格式：字符串或字典{"type": "file", "text": "...", "file_path": "..."}）
        self.chat_history = {"聊天室": []}

        # 创建文件存储目录
        self.files_dir = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "received_files")
        if not os.path.exists(self.files_dir):
            os.makedirs(self.files_dir)

        # 文件路径映射（tag_id -> file_path）
        self.file_path_map = {}
        self.file_tag_counter = 0
        
        # 视频通话相关属性
        self.video_call_active = False
        self.local_video_cap = None
        self.remote_video_frame = None
        self.local_video_window = None
        self.remote_video_window = None
        self.video_call_with = None
        self.video_thread = None
        self.audio_thread = None
        
        # 用户头像映射（用户名 -> 头像信息）
        self.user_avatars = {}
        self.avatar_colors = [
            "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
            "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B739", "#52BE80"
        ]
        self.avatar_counter = 0
        # 头像emoji列表（更美观的选择）
        self.avatar_emojis = ["👤", "👨", "👩", "🧑",
                              "👨‍💼", "👩‍💼", "👨‍🎓", "👩‍🎓", "👨‍🔬", "👩‍🔬"]

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
        
        # 视频通话菜单
        video_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视频通话", menu=video_menu)
        video_menu.add_command(
            label="发起视频通话", command=self.initiate_video_call)
        video_menu.add_command(
            label="接听视频通话", command=self.answer_video_call)
        video_menu.add_command(
            label="挂断视频通话", command=self.end_video_call)

        # 配置主窗口的行和列权重，使其可缩放
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_rowconfigure(1, weight=0)  # 状态栏行不扩展
        self.master.grid_columnconfigure(0, weight=1)

        # 主框架（左右分栏）
        main_frame = tk.PanedWindow(
            self.master, orient=tk.HORIZONTAL, bg="#F5F5F5", sashwidth=2)
        main_frame.grid(row=0, column=0, sticky="nsew")

        # 配置主框架权重
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        # 左侧框架（用户列表）
        left_frame = tk.Frame(main_frame, bg="#EDEDED", width=250)
        main_frame.add(left_frame, width=250, minsize=180)

        # 配置左侧框架权重
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # 用户列表标题栏
        title_frame = tk.Frame(left_frame, bg="#393939", height=50)
        title_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        title_frame.grid_propagate(False)

        title_label = tk.Label(title_frame, text="聊天", font=("Microsoft YaHei", 14, "bold"),
                               fg="white", bg="#393939")
        title_label.pack(pady=15)

        # 用户列表框（美化样式）
        listbox_frame = tk.Frame(left_frame, bg="#EDEDED")
        listbox_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # 配置列表框框架权重
        listbox_frame.grid_rowconfigure(0, weight=1)
        listbox_frame.grid_columnconfigure(0, weight=1)

        self.users_listbox = tk.Listbox(listbox_frame,
                                        font=("Microsoft YaHei", 11),
                                        bg="white",
                                        fg="#333333",
                                        selectbackground="#C7E0F4",
                                        selectforeground="#333333",
                                        borderwidth=0,
                                        highlightthickness=0,
                                        activestyle="none")
        self.users_listbox.grid(row=0, column=0, sticky="nsew")

        # 添加"聊天室"选项
        self.users_listbox.insert(tk.END, "💬 聊天室")

        # 绑定点击事件
        self.users_listbox.bind("<<ListboxSelect>>", self.select_chat_target)

        # 刷新按钮
        self.refresh_button = tk.Button(
            left_frame, text="刷新用户", command=self.request_user_list)
        self.refresh_button.grid(
            row=2, column=0, pady=(5, 0), padx=0, sticky="ew")

        # 配置刷新按钮所在行的权重
        left_frame.grid_rowconfigure(2, weight=0)

        # 右侧框架（聊天区域）
        right_frame = tk.Frame(main_frame, bg="#F5F5F5")
        main_frame.add(right_frame)

        # 配置右侧框架权重
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # 聊天头部（类似微信）
        header_frame = tk.Frame(right_frame, bg="#393939", height=60)
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_propagate(False)

        self.current_chat_label = tk.Label(header_frame,
                                           text="聊天室",
                                           font=("Microsoft YaHei",
                                                 14, "bold"),
                                           fg="white",
                                           bg="#393939")
        self.current_chat_label.pack(pady=18)

        # 创建聊天内容容器（包含消息显示和输入区域）
        chat_content_frame = tk.Frame(right_frame, bg="#F5F5F5")
        chat_content_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # 配置聊天内容框架权重
        chat_content_frame.grid_rowconfigure(0, weight=1)  # 消息显示区域扩展
        chat_content_frame.grid_rowconfigure(1, weight=0)  # 输入框不扩展
        chat_content_frame.grid_columnconfigure(0, weight=1)

        # 消息显示区域（微信风格背景）
        self.messages_display = scrolledtext.ScrolledText(
            chat_content_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=20,
            bg="#F5F5F5",
            fg="#333333",
            font=("Microsoft YaHei", 11),
            borderwidth=0,
            highlightthickness=0,
            padx=15,
            pady=10,
            spacing1=5,
            spacing2=2,
            spacing3=5
        )
        self.messages_display.grid(
            row=0, column=0, sticky="nsew", padx=0, pady=0)

        # 输入区域（微信风格）
        input_frame = tk.Frame(chat_content_frame, bg="#F5F5F5")
        input_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        # 配置输入框框架权重
        chat_content_frame.grid_rowconfigure(1, weight=0)  # 输入框不扩展

        # 配置输入框架的行权重
        input_frame.grid_rowconfigure(0, weight=1)
        input_frame.grid_columnconfigure(0, weight=1)

        # 输入框容器
        input_container = tk.Frame(input_frame, bg="white", relief="flat")
        input_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 配置输入容器权重
        input_container.grid_rowconfigure(0, weight=1)
        input_container.grid_columnconfigure(0, weight=1)

        self.message_entry = tk.Entry(input_container,
                                      font=("Microsoft YaHei", 11),
                                      bg="white",
                                      fg="#333333",
                                      borderwidth=0,
                                      highlightthickness=1,
                                      highlightcolor="#07C160",
                                      highlightbackground="#E0E0E0",
                                      relief="flat")
        self.message_entry.grid(
            row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 配置输入框权重
        input_container.grid_columnconfigure(0, weight=1)

        self.message_entry.bind("<Return>", self.send_message)

        # 按钮框架
        button_frame = tk.Frame(input_container, bg="white")
        button_frame.grid(row=0, column=1, sticky="ns", padx=5, pady=5)

        self.send_file_button = tk.Button(
            button_frame,
            text="📎",
            command=self.send_file,
            font=("Microsoft YaHei", 14),
            bg="white",
            fg="#666666",
            activebackground="#F0F0F0",
            activeforeground="white",
            borderwidth=0,
            relief="flat",
            cursor="hand2",
            width=3,
            height=1
        )
        self.send_file_button.pack(side=tk.LEFT, padx=2)
        
        self.video_call_button = tk.Button(
            button_frame,
            text="🎥",
            command=self.initiate_video_call,
            font=("Microsoft YaHei", 14),
            bg="white",
            fg="#666666",
            activebackground="#F0F0F0",
            activeforeground="white",
            borderwidth=0,
            relief="flat",
            cursor="hand2",
            width=3,
            height=1
        )
        self.video_call_button.pack(side=tk.LEFT, padx=2)

        self.send_button = tk.Button(
            button_frame,
            text="发送",
            command=self.send_message,
            font=("Microsoft YaHei", 11),
            bg="#07C160",
            fg="white",
            activebackground="#06AD56",
            activeforeground="white",
            borderwidth=0,
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=5
        )
        self.send_button.pack(side=tk.LEFT, padx=2)

        # 配置消息样式tag
        # 发送的消息（右侧，微信绿色背景）
        self.messages_display.tag_config("message_sent",
                                         background="#95EC69",
                                         foreground="#000000",
                                         lmargin1=200,  # 左边距，控制消息整体位置
                                         lmargin2=200,  # 左边距，控制消息整体位置
                                         rmargin=20,   # 右边距
                                         spacing1=0,
                                         spacing2=0,
                                         spacing3=0,
                                         relief="flat",
                                         borderwidth=8,
                                         wrap="word",
                                         justify="right")

        # 接收的消息（左侧，微信白色背景）
        self.messages_display.tag_config("message_received",
                                         background="#FFFFFF",
                                         foreground="#000000",
                                         lmargin1=20,   # 左边距
                                         lmargin2=20,   # 左边距
                                         rmargin=200,  # 右边距，控制消息整体位置
                                         spacing1=0,
                                         spacing2=0,
                                         spacing3=0,
                                         relief="flat",
                                         borderwidth=8,
                                         wrap="word",
                                         justify="left")

        # 用户名样式
        self.messages_display.tag_config("username",
                                         font=("Microsoft YaHei", 10, "bold"),
                                         foreground="#000000")

        # 发送消息的用户名（右侧）
        self.messages_display.tag_config("username_sent",
                                         font=("Microsoft YaHei", 10, "bold"),
                                         foreground="#000000",
                                         lmargin1=200,  # 左边距，控制用户名整体位置
                                         lmargin2=200,  # 左边距，控制用户名整体位置
                                         rmargin=20,   # 右边距
                                         spacing1=0,
                                         spacing2=0,
                                         spacing3=0,
                                         justify="right")

        # 接收消息的用户名（左侧）
        self.messages_display.tag_config("username_received",
                                         font=("Microsoft YaHei", 10, "bold"),
                                         foreground="#000000",
                                         lmargin1=20,   # 左边距
                                         lmargin2=20,   # 左边距
                                         rmargin=200,  # 右边距，控制用户名整体位置
                                         spacing1=0,
                                         spacing2=0,
                                         spacing3=0,
                                         justify="left")

        # 系统消息（居中，灰色）
        self.messages_display.tag_config("message_system",
                                         foreground="#999999",
                                         justify="center",
                                         font=("Microsoft YaHei", 9),
                                         lmargin1=50,
                                         lmargin2=50,
                                         rmargin=50)

        # 时间戳样式（居中，小字体）
        self.messages_display.tag_config("timestamp",
                                         foreground="#999999",
                                         justify="center",
                                         font=("Microsoft YaHei", 9),
                                         lmargin1=0,
                                         lmargin2=0,
                                         rmargin=0,
                                         spacing1=5,
                                         spacing2=2,
                                         spacing3=5)

        # 文件链接样式
        self.messages_display.tag_config("file_link",
                                         foreground="#576B95",
                                         underline=True)
        # 绑定点击事件和鼠标悬停事件
        self.messages_display.tag_bind(
            "file_link", "<Button-1>", self.on_file_link_click)
        self.messages_display.tag_bind(
            "file_link", "<Enter>", self.on_file_link_enter)
        self.messages_display.tag_bind(
            "file_link", "<Leave>", self.on_file_link_leave)

        # 状态栏（微信风格）
        self.status_bar = tk.Label(
            self.master,
            text="● 未连接",
            font=("Microsoft YaHei", 9),
            bg="#F5F5F5",
            fg="#999999",
            bd=0,
            relief="flat",
            anchor=tk.W,
            padx=10,
            pady=5
        )
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        # 绑定窗口关闭事件
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 绑定窗口大小调整事件，确保响应式布局
        self.master.bind("<Configure>", self.on_window_resize)

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

            # 注意：发送时不要立即添加到历史记录，因为实际的可点击文件会在接收阶段生成
            # 当服务器将文件广播回来时，handle_file_receive 方法会处理并创建正确的文件链接

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

                # 检查是否是文件传输消息
                if "/FILE|" in message:
                    # 在主线程中处理文件接收
                    self.master.after(0, self.handle_file_receive, message)
                # 解析消息类型并处理（包括文件消息在内的所有消息）
                self.process_received_message(message)

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
                self.add_message_to_history(
                    "聊天室", f"系统: 文件大小不匹配 (期望: {file_size}, 实际: {len(file_data)})")
                return

            # 检查是否是自己的文件（服务器会广播给所有客户端，包括发送者）
            is_own_file = sender_name and sender_name == getattr(
                self, 'username', None)

            # 显示接收提示
            sender_info = f"{sender_name} 发送了" if sender_name else "收到"
            file_size_formatted = self.format_file_size(file_size)

            # 自动保存文件到固定目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 处理文件名，避免冲突
            name, ext = os.path.splitext(filename)
            safe_filename = f"{timestamp}_{name}{ext}"
            save_path = os.path.join(self.files_dir, safe_filename)

            # 保存文件
            with open(save_path, 'wb') as f:
                f.write(file_data)

            # 确定聊天目标（群聊或私聊）
            chat_target = "聊天室"
            if sender_name and sender_name != self.username:
                # 如果是私聊，可能需要检查消息来源
                # 这里暂时都放到聊天室，可以根据实际需求调整
                pass

            if is_own_file:
                # 如果是自己的文件，也要显示为可点击的文件消息
                file_info = {
                    "type": "file",
                    "text": f"{self.username}：[文件] {filename} ({file_size_formatted})",
                    "file_path": save_path,
                    "filename": filename,
                    "sender": self.username
                }
                self.add_message_to_history(chat_target, file_info)
            else:
                # 其他用户发送的文件，自动保存并显示
                file_info = {
                    "type": "file",
                    "text": f"{sender_name}：[文件] {filename} ({file_size_formatted})",
                    "file_path": save_path,
                    "filename": filename,
                    "sender": sender_name or "未知"
                }
                self.add_message_to_history(chat_target, file_info)
                
                # 显示文件接收成功提示
                if not is_own_file:
                    print(f"文件已保存至: {save_path}")  # 控制台输出，便于调试

        except Exception as e:
            error_msg = f"接收文件时出错: {str(e)}"
            self.add_message_to_history("聊天室", f"系统: {error_msg}")
            messagebox.showerror("接收文件错误", error_msg)

    def process_received_message(self, message):
        """处理接收到的消息"""
        # 检查是否是用户列表消息
        if message.startswith("/USERLIST|"):
            # 解析用户列表：/USERLIST|user1|user2|user3
            parts = message.split("|")
            if len(parts) >= 1:
                users = [user for user in parts[1:] if user]  # 排除空字符串
                # 在主线程中更新用户列表
                self.master.after(0, self.update_users_list, users)
        # 检查是否是视频通话相关消息
        elif message.startswith("/VIDEO_CALL_INVITE|"):
            # 视频通话邀请
            caller = message.split('|')[1]
            self.master.after(0, self.receive_video_call_request, caller)
        elif message.startswith("/VIDEO_CALL_START|"):
            # 视频通话开始
            caller = message.split('|')[1]
            self.master.after(0, self.start_video_call, caller, False)
        elif message.startswith("/VIDEO_CALL_REJECTED|"):
            # 视频通话被拒绝
            caller = message.split('|')[1]
            self.master.after(0, lambda: messagebox.showinfo("视频通话", f"{caller} 拒绝了您的视频通话请求"))
        elif message.startswith("/VIDEO_CALL_ENDED|"):
            # 视频通话结束
            caller = message.split('|')[1]
            self.master.after(0, lambda: messagebox.showinfo("视频通话", f"{caller} 结束了视频通话"))
            if self.video_call_active:
                self.master.after(0, self.stop_video_call)
        elif message.startswith("/VIDEO_DATA|"):
            # 视频数据
            try:
                parts = message.split('|', 2)  # 最多分割为3部分
                sender = parts[1]
                video_data = parts[2]
                # 在主线程中处理视频数据
                self.master.after(0, self.receive_video_data, sender, video_data)
            except IndexError:
                print(f"视频数据格式错误: {message}")
        # 检查是否是系统消息（如用户上下线通知）
        elif message.startswith("【系统】"):
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
        if "已连接" in status_text or "连接" in status_text:
            self.status_bar.config(text=f"● {status_text}", fg="#07C160")
        else:
            self.status_bar.config(text=f"● {status_text}", fg="#999999")

    def select_chat_target(self, event):
        """选择聊天对象"""
        selection = self.users_listbox.curselection()
        if selection:
            target = self.users_listbox.get(selection[0])
            # 移除emoji前缀
            if target.startswith("💬 "):
                target = target.replace("💬 ", "")
            elif target.startswith("👤 "):
                target = target.replace("👤 ", "")
            if target != self.current_chat:
                self.current_chat = target
                self.current_chat_label.config(text=target)
                self.refresh_message_display()

    def request_user_list(self):
        """请求服务器发送最新的用户列表"""
        if self.connected:
            try:
                # 发送特殊消息请求用户列表
                self.send_message_raw("/REQUEST_USERLIST")
            except Exception as e:
                messagebox.showerror("错误", f"请求用户列表失败: {str(e)}")
        else:
            messagebox.showwarning("警告", "未连接到服务器！")

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

    def get_user_display_name(self, username):
        """获取用户显示名称"""
        return username

    def insert_message_to_display(self, msg):
        """将消息插入到显示区域（支持文件链接和微信风格气泡）"""
        # 获取当前时间
        current_time = datetime.now().strftime("%H:%M")

        if isinstance(msg, dict) and msg.get("type") == "file":
            # 文件消息
            text = msg["text"]
            file_path = msg.get("file_path", "")
            sender = msg.get("sender", "")
            is_own = (sender == self.username)

            # 提取文件名部分
            if "[文件]" in text:
                parts = text.split("[文件]")
                prefix = parts[0].replace(f"{sender}：", "").replace(
                    f"{sender} 发送了", "").strip()
                filename_part = parts[1].split(" (")[0]
                size_part = " (" + " (".join(parts[1].split(" (")[1:])

                # 先插入时间戳（居中）
                timestamp_start = self.messages_display.index(tk.END)
                self.messages_display.insert(
                    tk.END, f"{current_time}\n", "timestamp")
                timestamp_end = self.messages_display.index(tk.END + "-1c")
                self.messages_display.tag_add(
                    "timestamp", timestamp_start, timestamp_end)

                # 插入用户名和消息（在同一行）
                username_display = self.get_user_display_name(sender)
                username_tag = "username_sent" if is_own else "username_received"
                message_text = f"📎 {filename_part}{size_part}"

                if is_own:
                    # 我发送的文件消息（右侧对齐）
                    # 插入用户名
                    username_start = self.messages_display.index(tk.END)
                    self.messages_display.insert(
                        tk.END, f"{username_display}: ", "username_sent")
                    username_end = self.messages_display.index(tk.END + "-1c")
                    self.messages_display.tag_add(
                        "username_sent", username_start, username_end)
                    # 插入消息内容
                    msg_start = self.messages_display.index(tk.END)
                    self.messages_display.insert(tk.END, message_text)
                    msg_end = self.messages_display.index(tk.END + "-1c")
                    # 应用气泡样式
                    self.messages_display.tag_add(
                        "message_sent", msg_start, msg_end)
                    # 添加文件链接（找到文件名部分，跳过📎 emoji和空格）
                    # message_text格式: "📎 {filename_part}{size_part}"
                    # 计算文件名在文本中的位置
                    emoji_len = 2  # 📎 emoji通常占2个字符位置
                    space_len = 1  # 空格
                    filename_start_in_text = emoji_len + space_len
                    filename_end_in_text = message_text.find(" (")
                    if filename_end_in_text < 0:
                        filename_end_in_text = len(message_text)

                    # 计算在Text widget中的实际位置
                    file_start = self.messages_display.index(
                        f"{msg_start}+{filename_start_in_text}c")
                    filename_length = filename_end_in_text - filename_start_in_text
                    file_end = self.messages_display.index(
                        f"{file_start}+{filename_length}c")

                    tag_id = f"file_tag_{self.file_tag_counter}"
                    self.file_tag_counter += 1
                    self.file_path_map[tag_id] = file_path
                    self.messages_display.tag_add(
                        "file_link", file_start, file_end)
                    self.messages_display.tag_add(tag_id, file_start, file_end)
                else:
                    # 其他人发送的文件消息（左侧对齐）
                    # 插入用户名
                    username_start = self.messages_display.index(tk.END)
                    self.messages_display.insert(
                        tk.END, f"{username_display}: ", "username_received")
                    username_end = self.messages_display.index(tk.END + "-1c")
                    self.messages_display.tag_add(
                        "username_received", username_start, username_end)
                    # 插入消息内容
                    msg_start = self.messages_display.index(tk.END)
                    self.messages_display.insert(tk.END, message_text)
                    msg_end = self.messages_display.index(tk.END + "-1c")
                    # 应用气泡样式
                    self.messages_display.tag_add(
                        "message_received", msg_start, msg_end)
                    # 添加文件链接（找到文件名部分，跳过📎 emoji和空格）
                    # message_text格式: "📎 {filename_part}{size_part}"
                    # 计算文件名在文本中的位置
                    emoji_len = 2  # 📎 emoji通常占2个字符位置
                    space_len = 1  # 空格
                    filename_start_in_text = emoji_len + space_len
                    filename_end_in_text = message_text.find(" (")
                    if filename_end_in_text < 0:
                        filename_end_in_text = len(message_text)

                    # 计算在Text widget中的实际位置
                    file_start = self.messages_display.index(
                        f"{msg_start}+{filename_start_in_text}c")
                    filename_length = filename_end_in_text - filename_start_in_text
                    file_end = self.messages_display.index(
                        f"{file_start}+{filename_length}c")

                    tag_id = f"file_tag_{self.file_tag_counter}"
                    self.file_tag_counter += 1
                    self.file_path_map[tag_id] = file_path
                    self.messages_display.tag_add(
                        "file_link", file_start, file_end)
                    self.messages_display.tag_add(tag_id, file_start, file_end)

            else:
                self.messages_display.insert(tk.END, text + "\n")
        else:
            # 普通文本消息
            text = msg if isinstance(msg, str) else str(msg)

            # 判断消息类型
            if text.startswith("系统:") or text.startswith("【系统】") or text.startswith("【系统广播】"):
                # 系统消息（不需要时间戳和头像）
                self.messages_display.insert(
                    tk.END, f"{text}\n", "message_system")
            elif ":" in text or "：" in text:
                # 确定使用哪种冒号
                separator = "：" if "：" in text else ":"
                # 解析发送者和消息内容
                parts = text.split(separator, 1)
                if len(parts) == 2:
                    sender = parts[0].strip()
                    content = parts[1].strip()
                    is_own = (sender == self.username)

                    # 先插入时间戳（居中）
                    timestamp_start = self.messages_display.index(tk.END)
                    self.messages_display.insert(
                        tk.END, f"{current_time}\n", "timestamp")
                    timestamp_end = self.messages_display.index(tk.END + "-1c")
                    self.messages_display.tag_add(
                        "timestamp", timestamp_start, timestamp_end)

                    # 插入用户名和消息（在同一行）
                    username_display = self.get_user_display_name(sender)
                    username_tag = "username_sent" if is_own else "username_received"

                    if is_own:
                        # 我发送的消息（右侧对齐）
                        # 插入用户名
                        username_start = self.messages_display.index(tk.END)
                        self.messages_display.insert(
                            tk.END, f"{username_display}: ", "username_sent")
                        username_end = self.messages_display.index(
                            tk.END + "-1c")
                        self.messages_display.tag_add(
                            "username_sent", username_start, username_end)
                        # 插入消息内容
                        msg_start = self.messages_display.index(tk.END)
                        self.messages_display.insert(tk.END, content)
                        msg_end = self.messages_display.index(tk.END + "-1c")
                        # 应用气泡样式
                        self.messages_display.tag_add(
                            "message_sent", msg_start, msg_end)
                    else:
                        # 其他人发送的消息（左侧对齐）
                        # 插入用户名
                        username_start = self.messages_display.index(tk.END)
                        self.messages_display.insert(
                            tk.END, f"{username_display}: ", "username_received")
                        username_end = self.messages_display.index(
                            tk.END + "-1c")
                        self.messages_display.tag_add(
                            "username_received", username_start, username_end)
                        # 插入消息内容
                        msg_start = self.messages_display.index(tk.END)
                        self.messages_display.insert(tk.END, content)
                        msg_end = self.messages_display.index(tk.END + "-1c")
                        # 应用气泡样式
                        self.messages_display.tag_add(
                            "message_received", msg_start, msg_end)
                else:
                    self.messages_display.insert(tk.END, f"{text}\n")
            else:
                self.messages_display.insert(tk.END, f"{text}\n")

        # 消息之间添加空行
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

        if file_path:
            if os.path.exists(file_path):
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
                messagebox.showwarning("文件不存在", f"文件不存在或已被删除:\n{file_path}\n\n可能的原因:\n1. 发送者删除了原文件\n2. 文件传输过程中出现错误\n3. 文件尚未完全下载")
        else:
            messagebox.showwarning("文件信息缺失", "无法获取文件路径信息，请重新接收文件")

    def update_users_list(self, users_list):
        """更新用户列表"""
        # 清空当前列表（保留"聊天室"选项）
        self.users_listbox.delete(0, tk.END)
        self.users_listbox.insert(tk.END, "💬 聊天室")

        # 添加在线用户（排除自己）
        for user in users_list:
            if user != self.username:  # 不显示自己
                self.users_listbox.insert(tk.END, f"👤 {user}")

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

    def on_window_resize(self, event):
        # 仅处理根窗口的resize事件，避免组件resize事件重复触发
        if event.widget == self.master:
            # 更新界面布局
            self.master.update_idletasks()
    
    def initiate_video_call(self):
        """发起视频通话"""
        if not self.connected:
            messagebox.showwarning("警告", "未连接到服务器！")
            return
        
        # 检查是否已经有视频通话正在进行
        if self.video_call_active:
            messagebox.showwarning("警告", f"您正在与 {self.video_call_with} 进行视频通话！")
            return
        
        # 检查是否有摄像头
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("错误", "无法打开摄像头！")
            return
        cap.release()
        
        # 选择要呼叫的用户
        if self.current_chat == "聊天室":
            messagebox.showinfo("提示", "请选择一个用户进行视频通话")
            return
        
        target_user = self.current_chat
        confirm = messagebox.askyesno("视频通话", f"确定要向 {target_user} 发起视频通话吗？")
        if confirm:
            # 发送视频通话请求
            video_call_request = f"/VIDEO_CALL_REQUEST|{target_user}"
            self.send_message_raw(video_call_request)
            self.add_message_to_history("聊天室", f"系统: 已向 {target_user} 发起视频通话请求")
    
    def receive_video_call_request(self, caller):
        """接收视频通话请求"""
        response = messagebox.askyesno("视频通话请求", f"{caller} 邀请您进行视频通话，是否接受？")
        if response:
            # 接受视频通话
            accept_msg = f"/VIDEO_CALL_ACCEPT|{caller}"
            self.send_message_raw(accept_msg)
            self.start_video_call(caller, is_caller=False)
        else:
            # 拒绝视频通话
            reject_msg = f"/VIDEO_CALL_REJECT|{caller}"
            self.send_message_raw(reject_msg)
    
    def answer_video_call(self):
        """接听视频通话"""
        if self.video_call_with:
            self.start_video_call(self.video_call_with, is_caller=False)
    
    def end_video_call(self):
        """结束视频通话"""
        if self.video_call_active:
            # 发送结束视频通话消息
            end_msg = f"/VIDEO_CALL_END|{self.video_call_with}"
            self.send_message_raw(end_msg)
            
            # 停止视频通话
            self.stop_video_call()
            self.add_message_to_history("聊天室", f"系统: 视频通话已结束")
    
    def start_video_call(self, with_user, is_caller=True):
        """开始视频通话"""
        # 检查是否已经有视频通话正在进行
        if self.video_call_active:
            if self.video_call_with != with_user:
                messagebox.showwarning("警告", f"您正在与 {self.video_call_with} 进行视频通话！")
            return
        
        self.video_call_active = True
        self.video_call_with = with_user
        
        # 打开本地摄像头
        self.local_video_cap = cv2.VideoCapture(0)
        if not self.local_video_cap.isOpened():
            messagebox.showerror("错误", "无法打开本地摄像头！")
            self.video_call_active = False
            return
        
        # 设置摄像头参数以减少资源消耗
        self.local_video_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.local_video_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.local_video_cap.set(cv2.CAP_PROP_FPS, 15)
        
        # 创建视频通话窗口
        self.create_video_call_window(is_caller)
        
        # 启动视频传输线程
        self.video_thread = threading.Thread(target=self.transmit_video, daemon=True)
        self.video_thread.start()
        
        self.add_message_to_history("聊天室", f"系统: 与 {with_user} 的视频通话已开始")
    
    def stop_video_call(self):
        """停止视频通话"""
        self.video_call_active = False
        
        # 释放摄像头资源
        if self.local_video_cap:
            self.local_video_cap.release()
        
        # 关闭视频窗口
        if self.local_video_window:
            self.local_video_window.destroy()
        if self.remote_video_window:
            self.remote_video_window.destroy()
        
        # 重置变量
        self.local_video_cap = None
        self.local_video_window = None
        self.remote_video_window = None
        self.video_call_with = None
    
    def create_video_call_window(self, is_caller):
        """创建视频通话窗口"""
        # 本地视频窗口
        self.local_video_window = tk.Toplevel(self.master)
        self.local_video_window.title("本地视频")
        self.local_video_window.geometry("300x200")
        self.local_video_window.protocol("WM_DELETE_WINDOW", self.end_video_call)
        
        self.local_video_label = tk.Label(self.local_video_window)
        self.local_video_label.pack(fill=tk.BOTH, expand=True)
        
        # 远程视频窗口
        self.remote_video_window = tk.Toplevel(self.master)
        self.remote_video_window.title(f"远程视频 - {self.video_call_with}")
        self.remote_video_window.geometry("400x300")
        self.remote_video_window.protocol("WM_DELETE_WINDOW", self.end_video_call)
        
        self.remote_video_label = tk.Label(self.remote_video_window)
        self.remote_video_label.pack(fill=tk.BOTH, expand=True)
        
        # 开始更新视频帧
        self.update_local_video()
    
    def update_local_video(self):
        """更新本地视频画面"""
        if self.video_call_active and self.local_video_cap:
            ret, frame = self.local_video_cap.read()
            if ret:
                # 调整帧大小以适应显示区域
                frame = cv2.resize(frame, (300, 200))
                # 翻转帧（镜像效果）
                frame = cv2.flip(frame, 1)
                
                # 转换颜色空间从BGR到RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 将numpy数组转换为图像
                h, w = frame_rgb.shape[:2]
                img = tk.PhotoImage(width=w, height=h)
                
                # 逐像素设置图像（这是简化实现，实际应用中可能需要更高效的方法）
                for y in range(min(h, 300)):
                    for x in range(min(w, 300)):
                        r, g, b = frame_rgb[y, x]
                        hex_color = f"#{r:02x}{g:02x}{b:02x}"
                        img.put(hex_color, (x, y))
                
                self.local_video_label.img = img  # 保持引用防止被垃圾回收
                self.local_video_label.configure(image=img)
                
                # 每30毫秒更新一次
                self.local_video_window.after(30, self.update_local_video)
    
    def transmit_video(self):
        """传输视频数据"""
        last_send_time = time.time()
        SEND_INTERVAL = 0.2  # 限制发送间隔为0.2秒（5fps）
        
        while self.video_call_active and self.local_video_cap:
            ret, frame = self.local_video_cap.read()
            if not ret:
                time.sleep(0.033)  # 30fps的延迟
                continue
                
            current_time = time.time()
            # 控制发送频率
            if current_time - last_send_time < SEND_INTERVAL:
                time.sleep(0.033)  # 30fps的延迟
                continue
                
            # 编码帧为JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 40]  # 进一步降低质量以减少带宽
            result, encoded_image = cv2.imencode('.jpg', frame, encode_param)
            if result:
                # 转换为base64编码并发送
                image_data = base64.b64encode(encoded_image.tobytes()).decode('utf-8')
                video_data = f"/VIDEO_DATA|{self.video_call_with}|{image_data}"
                
                try:
                    # 发送视频数据
                    self.send_message_raw(video_data)
                except Exception as e:
                    print(f"发送视频数据失败: {e}")
                    break
                    
            last_send_time = current_time
            time.sleep(0.033)  # 30fps的延迟
    
    def receive_video_data(self, sender, image_data):
        """接收并显示远程视频数据"""
        if hasattr(self, 'remote_video_label') and self.video_call_active:
            try:
                # 解码base64图像数据
                img_bytes = base64.b64decode(image_data)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    # 调整帧大小以适应显示区域
                    frame = cv2.resize(frame, (400, 300))
                    
                    # 转换颜色空间从BGR到RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # 将numpy数组转换为图像
                    h, w = frame_rgb.shape[:2]
                    img = tk.PhotoImage(width=w, height=h)
                    
                    # 逐像素设置图像
                    for y in range(min(h, 300)):
                        for x in range(min(w, 400)):
                            r, g, b = frame_rgb[y, x]
                            hex_color = f"#{r:02x}{g:02x}{b:02x}"
                            img.put(hex_color, (x, y))
                    
                    self.remote_video_label.img = img  # 保持引用防止被垃圾回收
                    self.remote_video_label.configure(image=img)
            except Exception as e:
                print(f"视频解码错误: {e}")


def main():

    root = tk.Tk()
    app = ChatClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
