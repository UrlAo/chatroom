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
import time
import cv2
import numpy as np
import json
from PIL import Image, ImageTk
import socket as udp_socket_module
from threading import Thread
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
        
        # 添加心跳检测相关变量
        self.last_activity_time = time.time()  # 记录最后一次活动时间
        self.heartbeat_check_interval = 1000  # 每秒检查一次时间（毫秒）
        self.inactive_timeout = 5 * 60  # 5分钟无操作超时（秒）
        self.heartbeat_check_id = None  # 用于存储心跳检查的after ID

        # 存储不同聊天对象的消息（消息格式：字符串或字典{"type": "file", "text": "...", "file_path": "..."})
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
        self.local_video_frame = None  # 新增：存储本地视频帧
        self.video_call_with = None
        self.video_thread = None
        self.audio_thread = None
        self.local_display_thread = None
        self.video_recv_thread = None

        # 线程安全的窗口关闭标志
        self.local_display_stopped = threading.Event()
        self.remote_display_stopped = threading.Event()

        # 视频窗口布局相关属性
        self.main_video_source = 'remote'  # 'remote' 表示主窗口显示远程视频，'local' 表示主窗口显示本地视频
        self.small_video_source = 'local'  # 'local' 表示小窗口显示本地视频，'remote' 表示小窗口显示远程视频
        self.main_window_name = 'Video Call - Main'
        # x, y, width, height for small window
        self.small_window_coords = (10, 10, 240, 180)
        self.small_window_clicked = False

        # UDP视频传输相关属性
        self.udp_socket = None
        self.udp_port = 9999  # 默认UDP端口
        self.remote_udp_port = 9999  # 远程UDP端口
        self.local_udp_port = None  # 本地UDP端口（随机分配）
        self.video_recv_thread = None

        # 多人视频会议相关属性
        self.multi_video_active = False  # 是否正在进行多人视频会议
        self.multi_video_room_id = None  # 多人视频房间ID
        # 参与者信息 {username: {'frame': frame, 'udp_port': port, 'socket': socket, 'thread': thread, 'widget': widget}}
        self.multi_video_participants = {}
        self.multi_video_window = None  # 多人视频窗口
        self.multi_video_frames = {}  # 存储多个参与者的视频帧
        self.camera_enabled = True  # 摄像头是否启用
        self.multi_video_layout = []  # 记录视频窗口布局信息
        self.multi_video_udp_sockets = {}  # 存储每个参与者的UDP套接字 {username: socket}
        self.multi_video_recv_threads = {}  # 存储每个参与者的接收线程 {username: thread}
        self.multi_video_send_socket = None  # 用于发送视频数据的UDP套接字

        # 用户头像映射（用户名 -> 头像信息）
        self.user_avatars = {}
        self.avatar_colors = [
            "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
            "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B739", "#52BE80"
        ]
        self.avatar_counter = 0
        # 头像emoji列表（更美观的选择）

        # 创建界面组件
        self.create_widgets()
        
        # 绑定键盘和鼠标事件以追踪用户活动
        self.bind_user_activity_events()

    def bind_user_activity_events(self):
        """绑定用户活动事件，用于追踪用户操作"""
        # 绑定键盘事件
        self.master.bind("<Key>", self.on_user_activity)
        # 绑定鼠标移动事件
        self.master.bind("<Motion>", self.on_user_activity)
        # 绑定鼠标点击事件
        self.master.bind("<Button-1>", self.on_user_activity)
        self.master.bind("<Button-2>", self.on_user_activity)
        self.master.bind("<Button-3>", self.on_user_activity)
        # 绑定鼠标滚轮事件
        self.master.bind("<MouseWheel>", self.on_user_activity)
        # 绑定焦点事件
        self.master.bind("<FocusIn>", self.on_user_activity)
        self.master.bind("<FocusOut>", self.on_user_activity)

    def on_user_activity(self, event=None):
        """用户活动回调函数，更新最后活动时间"""
        self.last_activity_time = time.time()
        
        # 如果当前显示的是活动超时提醒窗口，则关闭它
        if hasattr(self, 'inactive_warning_window') and self.inactive_warning_window:
            try:
                self.inactive_warning_window.destroy()
                self.inactive_warning_window = None
            except tk.TclError:
                pass  # 窗口可能已经被销毁

    def start_heartbeat_check(self):
        """开始心跳检测"""
        if self.heartbeat_check_id:
            self.master.after_cancel(self.heartbeat_check_id)
        
        self.last_activity_time = time.time()  # 重置最后活动时间
        self.check_inactivity()

    def check_inactivity(self):
        """检查用户是否长时间无操作"""
        if not self.connected:
            return
            
        current_time = time.time()
        elapsed_time = current_time - self.last_activity_time
        
        if elapsed_time >= self.inactive_timeout:
            # 用户长时间无操作，显示提醒窗口
            self.show_inactive_warning()
        else:
            # 继续检查
            self.heartbeat_check_id = self.master.after(
                self.heartbeat_check_interval, 
                self.check_inactivity
            )

    def show_inactive_warning(self):
        """显示长时间无操作提醒窗口"""
        if hasattr(self, 'inactive_warning_window') and self.inactive_warning_window:
            return  # 如果窗口已存在，则不重复创建

        # 创建提醒窗口
        self.inactive_warning_window = tk.Toplevel(self.master)
        self.inactive_warning_window.title("长时间无操作提醒")
        self.inactive_warning_window.geometry("400x150")
        self.inactive_warning_window.resizable(False, False)
        
        # 设置窗口始终置顶
        self.inactive_warning_window.attributes('-topmost', True)
        
        # 居中显示窗口
        self.center_window_on_screen(self.inactive_warning_window)
        
        # 添加提示信息
        warning_label = tk.Label(
            self.inactive_warning_window, 
            text=f"您已经超过{self.inactive_timeout//60}分钟没有操作，\n是否继续保持连接？", 
            font=("Microsoft YaHei", 12),
            wraplength=350
        )
        warning_label.pack(pady=20)
        
        # 添加按钮框架
        button_frame = tk.Frame(self.inactive_warning_window)
        button_frame.pack(pady=10)
        
        # 添加"保持连接"按钮
        keep_connected_btn = tk.Button(
            button_frame,
            text="保持连接",
            command=self.keep_connected,
            font=("Microsoft YaHei", 10),
            bg="#07C160",
            fg="white",
            width=10
        )
        keep_connected_btn.pack(side=tk.LEFT, padx=10)
        
        # 添加"断开连接"按钮
        disconnect_btn = tk.Button(
            button_frame,
            text="断开连接",
            command=self.disconnect_from_server,
            font=("Microsoft YaHei", 10),
            bg="#FF6B6B",
            fg="white",
            width=10
        )
        disconnect_btn.pack(side=tk.LEFT, padx=10)
        
        # 绑定窗口关闭事件，自动选择断开连接
        self.inactive_warning_window.protocol("WM_DELETE_WINDOW", self.disconnect_from_server)
        
        # 当用户进行任何操作时，自动关闭警告窗口
        self.bind_warning_window_events()

    def center_window_on_screen(self, window):
        """将窗口居中显示在屏幕上"""
        window.update_idletasks()
        x = (window.winfo_screenwidth() // 2) - (window.winfo_width() // 2)
        y = (window.winfo_screenheight() // 2) - (window.winfo_height() // 2)
        window.geometry(f"+{x}+{y}")

    def bind_warning_window_events(self):
        """为警告窗口绑定事件，当用户操作时关闭警告"""
        if not hasattr(self, 'inactive_warning_window') or not self.inactive_warning_window:
            return

        # 为警告窗口本身绑定事件
        self.inactive_warning_window.bind("<Key>", self.on_user_activity)
        self.inactive_warning_window.bind("<Button-1>", self.on_user_activity)
        self.inactive_warning_window.bind("<ButtonRelease-1>", self.on_user_activity)
        self.inactive_warning_window.bind("<MouseWheel>", self.on_user_activity)

    def keep_connected(self):
        """用户选择保持连接时的操作"""
        if hasattr(self, 'inactive_warning_window') and self.inactive_warning_window:
            self.inactive_warning_window.destroy()
            self.inactive_warning_window = None
        
        # 更新最后活动时间
        self.last_activity_time = time.time()
        
        # 继续检查后续活动
        self.heartbeat_check_id = self.master.after(
            self.heartbeat_check_interval, 
            self.check_inactivity
        )

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
            "服务器地址", "请输入服务器IP地址:", initialvalue="10.206.183.108")
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
            
            # 开始心跳检测
            self.start_heartbeat_check()

        except Exception as e:
            messagebox.showerror("连接错误", f"无法连接到服务器: {str(e)}")
            if self.client_socket:
                self.client_socket.close()

    def disconnect_from_server(self):
        if not self.connected:
            messagebox.showinfo("信息", "当前未连接到服务器！")
            return

        # 取消心跳检查
        if self.heartbeat_check_id:
            self.master.after_cancel(self.heartbeat_check_id)
            self.heartbeat_check_id = None

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

    def on_closing(self):
        """窗口关闭事件处理"""
        # 取消心跳检查
        if self.heartbeat_check_id:
            self.master.after_cancel(self.heartbeat_check_id)
            self.heartbeat_check_id = None
            
        if self.connected:
            self.disconnect_from_server()
        self.master.destroy()

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

            # 根据当前聊天对象决定发送方式
            if self.current_chat != "聊天室":
                # 私聊文件：格式 @target_user /FILE|filename|filesize|base64data
                private_file_message = f"@{self.current_chat} {file_message}"
                self.send_message_raw(private_file_message)

                # 在私聊对话中添加发送记录
                file_info = {
                    "type": "file",
                    "text": f"[私聊给{self.current_chat}] {self.username}：[文件] {filename} ({self.format_file_size(file_size)})",
                    "file_path": file_path,  # 使用原始文件路径
                    "filename": filename,
                    "sender": self.username
                }
                self.add_message_to_history(self.current_chat, file_info)
            else:
                # 群聊文件
                self.send_message_raw(file_message)

                # 在聊天室中添加发送记录
                file_info = {
                    "type": "file",
                    "text": f"{self.username}：[文件] {filename} ({self.format_file_size(file_size)})",
                    "file_path": file_path,  # 使用原始文件路径
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

                # 检查是否是文件传输消息
                if "/FILE|" in message:
                    # 在主线程中处理文件接收
                    self.master.after(0, self.handle_file_receive, message)
                    # 注意：对于文件消息，已经在handle_file_receive中通过process_received_message进行了处理
                    # 所以这里不再单独处理
                else:
                    # 解析消息类型并处理（非文件消息）
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
            # 由于服务器已修改，不再将文件消息发送回发送者
            # 因此这里接收到的文件消息一定是别人发送的

            # 服务器广播的格式可能是 "username：/FILE|..." 或直接是 "/FILE|..."
            # 提取发送者用户名（如果有）
            sender_name = None
            file_content = file_message

            # 检查是否是私聊消息格式
            is_private_msg = file_message.startswith("[私聊")
            if is_private_msg:
                # 提取私聊来源用户
                sender_start = file_message.find("[私聊来自") + 5  # "[私聊来自"的长度
                if sender_start > 4:
                    sender_end = file_message.find("]", sender_start)
                    if sender_end > sender_start:
                        sender_name = file_message[sender_start:sender_end]
                        # 移除私聊标签，获取实际内容
                        content_after_bracket = file_message[sender_end + 1:].strip()
                        # 检查是否有冒号分隔符
                        if content_after_bracket.startswith(sender_name + "：") or content_after_bracket.startswith(sender_name + ":"):
                            # 移除用户名和冒号部分，获取剩余内容
                            separator_pos = content_after_bracket.find("：")
                            if separator_pos == -1:  # 没找到中文冒号，尝试英文冒号
                                separator_pos = content_after_bracket.find(":")
                            if separator_pos != -1:
                                file_content = content_after_bracket[separator_pos + 1:].strip(
                                )
                        else:
                            file_content = content_after_bracket
            elif "：" in file_message or ":" in file_message:
                # 查找冒号分隔符（中文或英文）
                separator = "：" if "：" in file_message else ":"
                parts_msg = file_message.split(separator, 1)
                if len(parts_msg) == 2:
                    potential_sender = parts_msg[0].strip()
                    # 检查是否是文件消息格式，避免将其他格式的消息误处理
                    if parts_msg[1].strip().startswith("/FILE|"):
                        sender_name = potential_sender
                        file_content = parts_msg[1].strip()
                    else:
                        # 如果第二部分不是文件格式，可能是其他类型的消息
                        sender_name = potential_sender
                        file_content = parts_msg[1].strip()
                else:
                    sender_name = None
                    file_content = file_message
            # 解析文件消息：/FILE|filename|filesize|base64data
            # 使用maxsplit=3确保只分割前3个|，避免文件名中包含|导致的解析错误
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

            # 接收到的文件消息一定是别人发送的，因为服务器不会将文件发回给发送者
            # 所以我们总是接收文件并保存
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
            if is_private_msg and sender_name and sender_name != self.username:
                # 这是私聊文件消息
                chat_target = sender_name
            elif is_private_msg:
                # 即使无法提取发送者姓名，只要是私聊格式的消息，就不应加入聊天室
                # 可能是格式问题，但仍应视为私聊消息
                # 为了安全起见，尝试从原始消息中提取发送者
                if '[私聊来自' in file_message:
                    # 提取私聊来源用户
                    start_idx = file_message.find('[私聊来自') + 5
                    end_idx = file_message.find(']', start_idx)
                    if start_idx > 4 and end_idx > start_idx:
                        extracted_sender = file_message[start_idx:end_idx]
                        if extracted_sender and extracted_sender != self.username:
                            chat_target = extracted_sender
                        else:
                            # 如果仍无法提取，可以忽略此消息或显示错误
                            print(f'无法正确解析私聊文件消息: {file_message}')
                            return  # 避免将无法解析的消息添加到聊天室
                else:
                    # 如果是私聊格式但无法解析，最好忽略
                    print(f'无法解析的私聊文件消息: {file_message}')
                    return  # 避免将无法解析的消息添加到聊天室
            elif sender_name and sender_name != self.username:
                # 如果是群聊中的文件消息
                pass

            # 接收者：保存文件并显示记录
            file_info = {
                "type": "file",
                "text": f"{sender_name}：[文件] {filename} ({file_size_formatted})",
                "file_path": save_path,
                "filename": filename,
                "sender": sender_name or "未知"
            }
            self.add_message_to_history(chat_target, file_info)

            # 显示文件接收成功提示
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
        # 检查是否是UDP端口信息
        elif message.startswith("/UDP_PORT|"):
            # 格式：/UDP_PORT|port_number|ip_address（如果服务器提供IP）
            # 或者：/UDP_PORT|port_number（需要从消息来源获取IP）
            try:
                parts = message.split('|')
                if len(parts) >= 2:
                    udp_port = int(parts[1])

                    # 如果服务器也提供了IP地址
                    if len(parts) >= 3:
                        self.remote_ip = parts[2]
                    else:
                        # 从当前连接获取对方IP（这在P2P情况下可能不准确）
                        # 实际应用中，服务器应该提供对方的公网IP
                        # 这里使用一个默认值，实际部署时需要根据网络环境调整
                        if not hasattr(self, 'remote_ip'):
                            # 在实际应用中，这需要服务器提供正确的IP信息
                            print("警告：服务器未提供对方IP，UDP通信可能失败")

                    self.remote_udp_port = udp_port
                    print(
                        f"设置远程UDP端口: {self.remote_udp_port}, IP: {getattr(self, 'remote_ip', '未知')}")
            except ValueError:
                print(f"UDP端口格式错误: {message}")
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
            self.master.after(0, lambda: messagebox.showinfo(
                "视频通话", f"{caller} 拒绝了您的视频通话请求"))
        elif message.startswith("/VIDEO_CALL_ENDED|"):
            # 视频通话结束
            caller = message.split('|')[1]
            self.master.after(0, lambda: messagebox.showinfo(
                "视频通话", f"{caller} 结束了视频通话"))
            if self.video_call_active:
                self.master.after(0, self.stop_video_call)
        elif message.startswith("/VIDEO_DATA|"):
            # 视频数据
            try:
                parts = message.split('|', 2)  # 最多分割为3部分
                sender = parts[1]
                video_data = parts[2]
                # 在主线程中处理视频数据
                self.master.after(0, self.receive_video_data,
                                  sender, video_data)
            except IndexError:
                print(f"视频数据格式错误: {message}")
        # 检查是否是多人视频会议相关消息
        elif message.startswith("/MULTI_VIDEO_INVITE|"):
            # 多人视频会议邀请
            parts = message.split('|')
            if len(parts) >= 3:
                room_id = parts[1]
                inviter = parts[2]
                # 在聊天室中添加会议邀请消息
                invite_msg = f"{inviter} 发起了一个视频会议，点击进入"
                # 创建可点击的消息
                clickable_msg = {
                    "type": "multi_video_invite",
                    "text": f"【多人视频会议】{invite_msg}",
                    "room_id": room_id,
                    "inviter": inviter
                }
                self.add_message_to_history("聊天室", clickable_msg)
        elif message.startswith("/MULTI_VIDEO_JOIN|"):
            # 有人加入多人视频会议
            parts = message.split('|')
            if len(parts) >= 3:
                room_id = parts[1]
                username = parts[2]
                if self.multi_video_active and self.multi_video_room_id == room_id:
                    # 添加到参与者列表
                    self.multi_video_participants[username] = {
                        'frame': None, 'udp_port': None}
                    print(f"{username} 加入了多人视频会议")
        elif message.startswith("/MULTI_VIDEO_LEAVE|"):
            # 有人离开多人视频会议
            parts = message.split('|')
            if len(parts) >= 3:
                room_id = parts[1]
                username = parts[2]
                if self.multi_video_active and self.multi_video_room_id == room_id:
                    # 从参与者列表中移除
                    if username in self.multi_video_participants:
                        del self.multi_video_participants[username]
                    print(f"{username} 离开了多人视频会议")
        elif message.startswith("/MULTI_VIDEO_DATA|"):
            # 多人视频会议数据
            try:
                parts = message.split('|', 3)  # 分割为4部分：命令|房间ID|发送者|数据
                if len(parts) >= 4:
                    room_id = parts[1]
                    sender = parts[2]
                    video_data = parts[3]
                    # 只处理当前房间的数据
                    if self.multi_video_active and self.multi_video_room_id == room_id:
                        # 在主线程中处理多人视频数据
                        self.master.after(0, self.receive_multi_video_data,
                                          sender, video_data)
            except IndexError:
                print(f"多人视频数据格式错误: {message}")
        elif message.startswith("/CAMERA_STATUS|"):
            # 摄像头状态更新
            # 格式：/CAMERA_STATUS|room_id|username|status
            try:
                parts = message.split('|', 3)
                room_id = parts[1]
                username = parts[2]
                status = parts[3]

                # 只处理当前房间的摄像头状态更新
                if self.multi_video_active and self.multi_video_room_id == room_id:
                    # 更新UI中的摄像头状态显示（例如，显示一个图标表示用户摄像头已关闭）
                    print(f"{username} 摄像头状态更新为: {status}")
                    # 这里可以添加更新UI的代码，比如在用户旁边显示摄像头状态图标
                    # 但不添加到聊天室消息历史中
            except IndexError:
                print(f"摄像头状态格式错误: {message}")
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
        # 修改此行以排除包含UDP_PORT、MULTI_VIDEO_JOIN、MULTI_VIDEO_INVITE和CAMERA_STATUS的消息
        elif not "/UDP_PORT" in message and not "/MULTI_VIDEO_JOIN" in message and not "/MULTI_VIDEO_INVITE" in message and not "/CAMERA_STATUS" in message:
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
        """将消息插入到显示区域（支持文件按钮和微信风格气泡）"""
        # 获取当前时间
        current_time = datetime.now().strftime("%H:%M")

        # 检查是否是多人视频会议邀请消息
        if isinstance(msg, dict) and msg.get("type") == "multi_video_invite":
            # 多人视频会议邀请消息
            text = msg["text"]
            room_id = msg["room_id"]
            inviter = msg["inviter"]
            is_creator = msg.get("is_creator", False)  # 是否为发起者

            # 先插入时间戳（居中）
            timestamp_start = self.messages_display.index(tk.END)
            self.messages_display.insert(
                tk.END, f"{current_time}\n", "timestamp")
            timestamp_end = self.messages_display.index(tk.END + "-1c")
            self.messages_display.tag_add(
                "timestamp", timestamp_start, timestamp_end)

            # 插入邀请消息
            msg_start = self.messages_display.index(tk.END)
            self.messages_display.insert(tk.END, f"{text}")
            msg_end = self.messages_display.index(tk.END + "-1c")

            # 应用系统消息样式
            self.messages_display.tag_add("message_system", msg_start, msg_end)

            # 如果不是发起者（即接收者），则显示点击进入按钮
            if not is_creator or inviter != self.username:  # 如果不是自己发起的会议，则显示按钮
                # 创建点击进入会议室的按钮
                self.messages_display.insert(tk.END, "\n")  # 添加换行
                button_frame = tk.Frame(
                    self.messages_display, bg="#F5F5F5")  # 背景色
                button_frame.columnconfigure(0, weight=1)

                # 创建进入会议室按钮，点击时弹出询问窗口
                join_button = tk.Button(button_frame,
                                        text="点击进入会议",
                                        command=lambda r_id=room_id, i_name=inviter: self.request_join_multi_video_call(
                                            r_id, i_name),
                                        font=("Microsoft YaHei", 10),
                                        bg="#07C160",
                                        fg="white",
                                        relief="flat",
                                        padx=10,
                                        pady=5,
                                        cursor="hand2")
                join_button.grid(row=0, column=0, padx=5, pady=2)

                # 将按钮框架作为窗口插入到文本中
                self.messages_display.window_create(
                    tk.END, window=button_frame)
            else:
                # 如果是发起者，显示会议已创建的信息
                self.messages_display.insert(tk.END, "\n")  # 添加换行
                info_frame = tk.Frame(
                    self.messages_display, bg="#F5F5F5")  # 背景色
                info_frame.columnconfigure(0, weight=1)

                # 创建信息标签
                info_label = tk.Label(info_frame,
                                      text="会议已创建并自动加入",
                                      font=("Microsoft YaHei", 10),
                                      bg="#07C160",
                                      fg="white",
                                      relief="flat")
                info_label.grid(row=0, column=0, padx=5, pady=2)

                # 将信息框架作为窗口插入到文本中
                self.messages_display.window_create(tk.END, window=info_frame)
        elif isinstance(msg, dict) and msg.get("type") == "file":
            # 文件消息
            text = msg["text"]
            file_path = msg.get("file_path", "")
            sender = msg.get("sender", "")
            is_own = (sender.strip() == self.username.strip())

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
                    self.messages_display.insert(
                        tk.END, f"📎 {filename_part}{size_part}")
                    msg_end = self.messages_display.index(tk.END + "-1c")

                    # 应用气泡样式
                    self.messages_display.tag_add(
                        "message_sent", msg_start, msg_end)

                    # 在下一行添加下载按钮
                    self.messages_display.insert(tk.END, "\n")  # 添加换行
                    button_frame = tk.Frame(
                        self.messages_display, bg="#95EC69")  # 绿色背景
                    button_frame.columnconfigure(0, weight=1)

                    download_button = tk.Button(button_frame,
                                                text=f"下载文件: {filename_part}",
                                                command=lambda fp=file_path: self.download_file(
                                                    fp),
                                                font=("Microsoft YaHei", 10),
                                                bg="#FFFFFF",
                                                fg="#000000",
                                                relief="flat",
                                                padx=10,
                                                pady=5,
                                                cursor="hand2")
                    download_button.grid(
                        row=0, column=0, padx=5, pady=2, sticky="e")  # 右对齐

                    # 将按钮框架作为窗口插入到文本中
                    self.messages_display.window_create(
                        tk.END, window=button_frame)
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
                    self.messages_display.insert(
                        tk.END, f"📎 {filename_part}{size_part}")
                    msg_end = self.messages_display.index(tk.END + "-1c")

                    # 应用气泡样式
                    self.messages_display.tag_add(
                        "message_received", msg_start, msg_end)

                    # 在下一行添加下载按钮
                    self.messages_display.insert(tk.END, "\n")  # 添加换行
                    button_frame = tk.Frame(
                        self.messages_display, bg="#FFFFFF")  # 白色背景
                    button_frame.columnconfigure(0, weight=1)

                    download_button = tk.Button(button_frame,
                                                text=f"下载文件: {filename_part}",
                                                command=lambda fp=file_path: self.download_file(
                                                    fp),
                                                font=("Microsoft YaHei", 10),
                                                bg="#E6E6E6",
                                                fg="#000000",
                                                relief="flat",
                                                padx=10,
                                                pady=5,
                                                cursor="hand2")
                    download_button.grid(
                        row=0, column=0, padx=5, pady=2, sticky="w")  # 左对齐

                    # 将按钮框架作为窗口插入到文本中
                    self.messages_display.window_create(
                        tk.END, window=button_frame)

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
                    # 比较时同时去除两端空白字符，提高匹配准确性
                    is_own = (sender.strip() == self.username.strip())

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

    def on_file_link_click(self, event):
        """处理文件链接点击事件（保留原有功能以防需要）"""
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
            self.download_file(file_path)
        else:
            messagebox.showwarning("文件信息缺失", "无法获取文件路径信息，请重新接收文件")

    def download_file(self, file_path):
        """下载文件到本地"""
        if file_path and os.path.exists(file_path):
            # 获取文件扩展名
            _, file_extension = os.path.splitext(file_path)
            file_extension = file_extension.lower()

            # 定义安全的文件类型列表
            safe_extensions = ['.txt', '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.doc', '.docx', '.xls', '.xlsx', '.ppt',
                               '.pptx', '.mp3', '.wav', '.mp4', '.avi', '.mov', '.zip', '.rar', '.7z', '.py', '.js', '.html', '.css', '.json', '.xml']

            # 如果是潜在危险的文件类型，提醒用户
            dangerous_extensions = [
                '.exe', '.bat', '.cmd', '.com', '.scr', '.vbs', '.js', '.msi', '.jar', '.apk']

            if file_extension in dangerous_extensions:
                response = messagebox.askyesno(
                    "安全警告",
                    f"警告：文件 '{os.path.basename(file_path)}' 可能包含恶意代码。\n\n文件类型: {file_extension}\n是否仍要打开？\n\n建议：扫描病毒后再打开。")
                if not response:
                    return  # 用户选择不打开

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
            messagebox.showwarning(
                "文件不存在", f"文件不存在或已被删除:\n{file_path}\n\n可能的原因:\n1. 发送者删除了原文件\n2. 文件传输过程中出现错误\n3. 文件尚未完全下载")

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
        """发起视频通话或多人视频会议"""
        if not self.connected:
            messagebox.showwarning("警告", "未连接到服务器！")
            return

        # 如果当前聊天对象是聊天室，则发起多人视频会议
        if self.current_chat == "聊天室":
            self.initiate_multi_video_call()
        else:
            # 检查是否已经有视频通话正在进行
            if self.video_call_active:
                messagebox.showwarning(
                    "警告", f"您正在与 {self.video_call_with} 进行视频通话！")
                return

            # 检查是否有摄像头
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                messagebox.showerror("错误", "无法打开摄像头！")
                return
            cap.release()

            target_user = self.current_chat
            confirm = messagebox.askyesno(
                "视频通话", f"确定要向 {target_user} 发起视频通话吗？")
            if confirm:
                # 发送视频通话请求
                video_call_request = f"/VIDEO_CALL_REQUEST|{target_user}"
                try:
                    self.send_message_raw(video_call_request)
                    self.add_message_to_history(
                        "聊天室", f"系统: 已向 {target_user} 发起视频通话请求")
                except Exception as e:
                    messagebox.showerror("错误", f"发送视频通话请求失败: {str(e)}")

    def initiate_multi_video_call(self):
        """发起多人视频会议"""
        # 检查是否已经有视频通话正在进行
        if self.video_call_active or self.multi_video_active:
            messagebox.showwarning(
                "警告", "您已经在一个视频通话中！")
            return

        # 检查是否有摄像头
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("错误", "无法打开摄像头！")
            return
        cap.release()

        # 生成随机房间ID
        import random
        room_id = f"multi_{random.randint(1000, 9999)}"
        self.multi_video_room_id = room_id

        # 发送多人视频会议邀请消息
        multi_video_invite = f"/MULTI_VIDEO_INVITE|{room_id}|{self.username}"
        self.send_message_raw(multi_video_invite)

        # 在聊天室中添加会议发起消息（使用结构化消息格式，标记为发起者）
        invite_msg = f"{self.username} 发起了一个视频会议"
        clickable_msg = {
            "type": "multi_video_invite",
            "text": f"【多人视频会议】{invite_msg}",
            "room_id": room_id,
            "inviter": self.username,
            "is_creator": True  # 标记发起者，用于区分显示
        }
        self.add_message_to_history("聊天室", clickable_msg)

        # 自动加入会议
        self.join_multi_video_call(room_id, self.username)

    def create_multi_video_window(self):
        """创建多人视频窗口"""
        if self.multi_video_window is not None and self.multi_video_window.winfo_exists():
            self.multi_video_window.lift()
            return

        # 创建多人视频窗口
        self.multi_video_window = tk.Toplevel(self.master)
        self.multi_video_window.title(f"多人视频会议 - {self.multi_video_room_id}")
        self.multi_video_window.geometry("800x600")

        # 设置窗口关闭事件
        self.multi_video_window.protocol(
            "WM_DELETE_WINDOW", self.leave_multi_video_call)

        # 创建主框架
        main_frame = tk.Frame(self.multi_video_window, bg="#F5F5F5")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 分割主框架为上下两部分
        # 上半部分：自己的主视频窗口
        self.self_video_frame = tk.Frame(
            main_frame, bg="#000000", relief=tk.RAISED, bd=1)
        self.self_video_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建自己的视频标签
        self.self_video_label = tk.Label(self.self_video_frame, text=f"我 ({self.username})", bg="#000000",
                                         fg="white", font=("Microsoft YaHei", 12))
        self.self_video_label.pack(expand=True, fill=tk.BOTH)

        # 存储自己的视频标签引用
        if self.username not in self.multi_video_participants:
            self.multi_video_participants[self.username] = {
                'frame': None, 'udp_port': None, 'widget': self.self_video_label}
        else:
            self.multi_video_participants[self.username]['widget'] = self.self_video_label

        # 立即尝试更新本地视频帧
        self.update_local_video_in_tkinter(self.self_video_label)

        # 下半部分：其他参与者的视频网格
        self.others_video_frame = tk.Frame(main_frame, bg="#F5F5F5")
        self.others_video_frame.pack(
            fill=tk.BOTH, expand=False, padx=5, pady=5)

        # 添加控制按钮
        control_frame = tk.Frame(self.multi_video_window)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # 摄像头开关按钮
        self.camera_toggle_btn = tk.Button(control_frame, text="关闭摄像头", command=self.toggle_camera,
                                           bg="#FF6B6B", fg="white", font=("Microsoft YaHei", 10))
        self.camera_toggle_btn.pack(side=tk.LEFT, padx=5)

        # 刷新视频按钮
        refresh_btn = tk.Button(control_frame, text="刷新视频", command=self.refresh_multi_video,
                                bg="#FFD700", fg="black", font=("Microsoft YaHei", 10))
        refresh_btn.pack(side=tk.LEFT, padx=5)

        # 离开会议按钮
        leave_btn = tk.Button(control_frame, text="离开会议", command=self.leave_multi_video_call,
                              bg="#4ECDC4", fg="white", font=("Microsoft YaHei", 10))
        leave_btn.pack(side=tk.RIGHT, padx=5)

        # 初始化其他参与者的视频布局
        self.update_others_video_layout()

    def receive_video_call_request(self, caller):
        """接收视频通话请求"""
        # 检查是否已经有视频通话正在进行
        if self.video_call_active:
            if self.video_call_with != caller:
                messagebox.showwarning(
                    "警告", f"您正在与 {self.video_call_with} 进行视频通话！")
            return

        # 检查是否有摄像头
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("错误", "无法打开摄像头，无法接受视频通话！")
            # 拒绝视频通话
            reject_msg = f"/VIDEO_CALL_REJECT|{caller}"
            self.send_message_raw(reject_msg)
            return
        cap.release()

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

    def update_local_video(self):
        """更新本地视频画面（现在为空函数，因为使用OpenCV窗口）"""
        # 此函数现在为空，因为视频显示由OpenCV窗口处理
        pass

    def answer_video_call(self):
        """接听视频通话"""
        if self.video_call_with:
            self.start_video_call(self.video_call_with, is_caller=False)

    def end_video_call(self):
        """结束视频通话"""
        if self.video_call_active:
            # 发送结束视频通话消息
            end_msg = f"/VIDEO_CALL_END|{self.video_call_with}"
            try:
                self.send_message_raw(end_msg)
            except Exception as e:
                print(f"发送视频通话结束消息失败: {str(e)}")

            # 停止视频通话
            self.stop_video_call()
            self.add_message_to_history("聊天室", f"系统: 视频通话已结束")

    def start_video_call(self, with_user, is_caller=True):
        """开始视频通话"""
        # 检查是否已经有视频通话正在进行
        if self.video_call_active:
            if self.video_call_with != with_user:
                messagebox.showwarning(
                    "警告", f"您正在与 {self.video_call_with} 进行视频通话！")
            return

        self.video_call_active = True
        self.video_call_with = with_user

        # 打开本地摄像头
        self.local_video_cap = cv2.VideoCapture(0)
        if not self.local_video_cap.isOpened():
            messagebox.showerror("错误", "无法打开本地摄像头！")
            return

        # 设置摄像头参数以减少资源消耗
        self.local_video_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.local_video_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.local_video_cap.set(cv2.CAP_PROP_FPS, 15)

        # 初始化OpenCV视频窗口
        self.initialize_cv2_video_windows()

        # 启动视频传输线程
        self.video_thread = threading.Thread(
            target=self.transmit_video, daemon=True)
        self.video_thread.start()

        self.add_message_to_history("聊天室", f"系统: 与 {with_user} 的视频通话已开始")

    def initialize_cv2_video_windows(self):
        """初始化OpenCV视频窗口"""
        # 标记窗口已初始化
        self.cv2_windows_initialized = True

        # 重置视频源
        self.main_video_source = 'remote'
        self.small_video_source = 'local'

        # 启动组合视频显示线程
        self.combined_display_thread = Thread(
            target=self.display_combined_video, daemon=True)
        self.combined_display_thread.start()

    def initialize_multi_video_display(self):
        """初始化多人视频会议的显示（使用Tkinter）"""
        # 直接更新UI显示，不需要额外线程
        self.update_video_layout()

    def display_combined_video(self):
        """显示组合视频（主视频+小视频）到单个OpenCV窗口"""
        try:
            # 创建主窗口
            cv2.namedWindow(self.main_window_name, cv2.WINDOW_AUTOSIZE)
            # 设置鼠标回调函数，用于检测小窗口点击
            cv2.setMouseCallback(self.main_window_name,
                                 self.on_video_window_click)

            while self.video_call_active:
                # 创建一个黑色画布作为基础
                canvas = np.zeros((480, 640, 3), dtype=np.uint8)

                # 获取主视频帧
                main_frame = None
                if self.main_video_source == 'remote' and self.remote_video_frame is not None:
                    main_frame = self.remote_video_frame.copy()
                elif self.main_video_source == 'local' and self.local_video_cap:
                    ret, main_frame = self.local_video_cap.read()
                    if ret:
                        main_frame = cv2.flip(main_frame, 1)  # 镜像效果
                    else:
                        main_frame = np.zeros(
                            (480, 640, 3), dtype=np.uint8)  # 黑色帧
                else:
                    main_frame = np.zeros((480, 640, 3), dtype=np.uint8)  # 黑色帧

                # 获取小视频帧
                small_frame = None
                small_w, small_h = 240, 180  # 小窗口尺寸
                if self.small_video_source == 'local' and self.local_video_cap:
                    ret, small_frame = self.local_video_cap.read()
                    if ret:
                        small_frame = cv2.flip(small_frame, 1)  # 镜像效果
                        small_frame = cv2.resize(
                            small_frame, (small_w, small_h))
                    else:
                        small_frame = np.zeros(
                            (small_h, small_w, 3), dtype=np.uint8)  # 黑色帧
                elif self.small_video_source == 'remote' and self.remote_video_frame is not None:
                    small_frame = cv2.resize(
                        self.remote_video_frame.copy(), (small_w, small_h))
                else:
                    small_frame = np.zeros(
                        (small_h, small_w, 3), dtype=np.uint8)  # 黑色帧

                # 调整主视频帧大小以适应画布
                main_frame = cv2.resize(main_frame, (640, 480))

                # 将主视频帧放置到画布上
                canvas = main_frame

                # 将小视频帧放置到画布的右上角
                x_offset, y_offset = 20, 20  # 小窗口坐标
                canvas[y_offset:y_offset+small_h,
                       x_offset:x_offset+small_w] = small_frame

                # 在小视频窗口上绘制边框
                cv2.rectangle(canvas, (x_offset, y_offset),
                              (x_offset+small_w, y_offset+small_h), (0, 255, 0), 2)

                # 显示组合视频
                cv2.imshow(self.main_window_name, canvas)

                # 按q键或检测到停止信号退出
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # ESC键
                    break

                # 添加一点延迟以控制帧率
                time.sleep(0.033)  # 约30fps
        except Exception as e:
            print(f"显示组合视频时出错: {e}")
        finally:
            # 设置停止事件
            self.local_display_stopped.set()
            # 不在这里调用destroyAllWindows，避免多线程冲突
            pass

    def on_video_window_click(self, event, x, y, flags, param):
        """处理视频窗口点击事件"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # 检查点击位置是否在小窗口区域内
            small_x, small_y, small_w, small_h = 20, 20, 240, 180  # 小窗口坐标和尺寸
            if small_x <= x <= small_x + small_w and small_y <= y <= small_y + small_h:
                # 点击了小窗口，交换主次窗口的视频源
                self.swap_video_sources()

    def swap_video_sources(self):
        """交换主次窗口的视频源"""
        # 交换视频源
        temp_source = self.main_video_source
        self.main_video_source = self.small_video_source
        self.small_video_source = temp_source
        print(
            f"视频源已交换: 主窗口={self.main_video_source}, 小窗口={self.small_video_source}")

    def stop_video_call(self):
        """停止视频通话"""
        self.video_call_active = False

        # 释放摄像头资源
        if self.local_video_cap:
            self.local_video_cap.release()

        # 等待接收线程结束，确保在UDP套接字关闭前线程已退出
        if self.video_recv_thread and self.video_recv_thread.is_alive():
            self.video_recv_thread.join(timeout=2)

        # 关闭UDP套接字
        if self.udp_socket:
            self.udp_socket.close()

        # 等待显示线程结束
        if hasattr(self, 'combined_display_thread') and self.combined_display_thread and self.combined_display_thread.is_alive():
            # 发送按键事件来中断显示循环
            cv2.destroyAllWindows()
            # 等待线程自然结束，最多等待2秒
            self.combined_display_thread.join(timeout=2)

        # 最后在主线程中清理所有OpenCV窗口
        try:
            cv2.destroyAllWindows()
        except:
            pass

        # 重置变量
        self.local_video_cap = None
        self.video_call_with = None
        self.remote_video_frame = None
        self.local_display_thread = None
        self.combined_display_thread = None
        self.video_recv_thread = None

        # 重置线程停止事件
        self.local_display_stopped.clear()
        self.remote_display_stopped.clear()

        # 重置UDP相关变量
        self.udp_socket = None
        self.remote_ip = None
        self.remote_udp_port = None

    def request_join_multi_video_call(self, room_id, inviter):
        """请求加入多人视频通话，弹出询问窗口"""
        response = messagebox.askyesno(
            "多人视频通话邀请", f"{inviter} 邀请您加入视频会议，是否接受？")
        if response:
            # 接受多人视频通话邀请
            self.join_multi_video_call(room_id, inviter)

    def join_multi_video_call(self, room_id, inviter):
        """加入多人视频会议"""
        # 检查是否已经有视频通话正在进行
        if self.video_call_active or self.multi_video_active:
            messagebox.showwarning(
                "警告", "您已经在一个视频通话中！")
            return

        # 检查是否有摄像头
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("错误", "无法打开摄像头！")
            return
        cap.release()

        # 设置标志位
        self.multi_video_active = True
        self.multi_video_room_id = room_id

        # 打开本地摄像头
        self.local_video_cap = cv2.VideoCapture(0)
        if not self.local_video_cap.isOpened():
            messagebox.showerror("错误", "无法打开本地摄像头！")
            self.multi_video_active = False
            return

        # 设置摄像头参数以减少资源消耗
        self.local_video_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.local_video_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.local_video_cap.set(cv2.CAP_PROP_FPS, 15)

        # 发送加入消息
        join_msg = f"/MULTI_VIDEO_JOIN|{room_id}|{self.username}"
        self.send_message_raw(join_msg)

        # 启动视频传输
        self.start_multi_video_stream()

        # 创建多人视频窗口
        self.create_multi_video_window()

    def start_multi_video_stream(self):
        """开始多人视频流"""
        # 设置UDP套接字
        self.setup_udp_socket()

        # 启动视频传输线程
        self.video_thread = threading.Thread(
            target=self.transmit_multi_video, daemon=True)
        self.video_thread.start()

    def update_local_video(self):
        """更新本地视频画面（现在为空函数，因为使用OpenCV窗口）"""
        # 此函数现在为空，因为视频显示由OpenCV窗口处理
        pass

    def setup_udp_socket(self):
        """设置UDP套接字用于视频传输"""
        # 关闭现有的UDP套接字
        if self.udp_socket:
            self.udp_socket.close()

        # 创建用于发送视频数据的UDP套接字
        self.udp_socket = udp_socket_module.socket(
            udp_socket_module.AF_INET, udp_socket_module.SOCK_DGRAM)
        # 绑定到任意可用端口
        self.udp_socket.bind(('', 0))
        self.local_udp_port = self.udp_socket.getsockname()[1]
        print(f"UDP套接字绑定到端口: {self.local_udp_port}")

        # 为多方视频会议创建专门的发送套接字
        if self.multi_video_send_socket:
            self.multi_video_send_socket.close()
        self.multi_video_send_socket = udp_socket_module.socket(
            udp_socket_module.AF_INET, udp_socket_module.SOCK_DGRAM)
        self.multi_video_send_socket.bind(('', 0))
        print(
            f"多方视频发送套接字绑定到端口: {self.multi_video_send_socket.getsockname()[1]}")

        # 启动接收线程
        self.video_recv_thread = Thread(
            target=self.receive_video_via_udp, daemon=True)
        self.video_recv_thread.start()

    def transmit_video(self):
        """通过UDP传输视频数据"""
        # 设置UDP套接字
        self.setup_udp_socket()

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
                image_data = base64.b64encode(
                    encoded_image.tobytes()).decode('utf-8')

                # 通过UDP发送视频数据
                try:
                    # 发送本地UDP端口给服务器，以便它能转发给对方
                    port_msg = f"/UDP_PORT|{self.local_udp_port}"
                    self.send_message_raw(port_msg)

                    # 通过UDP发送视频数据
                    video_packet = f"{self.username}:{image_data}".encode(
                        'utf-8')
                    # 需要知道对方的IP地址和UDP端口
                    # 通常在建立连接时服务器会提供对方的网络信息
                    if hasattr(self, 'remote_ip') and hasattr(self, 'remote_udp_port') and self.remote_ip and self.remote_udp_port:
                        self.udp_socket.sendto(
                            video_packet, (self.remote_ip, self.remote_udp_port))
                    else:
                        # 如果没有对方的IP信息，回退到TCP发送（保持兼容性）
                        video_data = f"/VIDEO_DATA|{self.video_call_with}|{image_data}"
                        self.send_message_raw(video_data)
                except Exception as e:
                    print(f"发送UDP视频数据失败: {e}, 尝试使用TCP")
                    # 如果UDP失败，回退到TCP发送
                    try:
                        video_data = f"/VIDEO_DATA|{self.video_call_with}|{image_data}"
                        self.send_message_raw(video_data)
                    except Exception as tcp_e:
                        print(f"TCP视频数据发送也失败: {tcp_e}")
                        break

            last_send_time = current_time
            time.sleep(0.033)  # 30fps的延迟

    def transmit_multi_video(self):
        """传输多人视频数据"""
        # 设置UDP套接字
        self.setup_udp_socket()

        last_send_time = time.time()
        SEND_INTERVAL = 0.2  # 限制发送间隔为0.2秒（5fps）

        while self.multi_video_active and self.local_video_cap:
            ret, frame = self.local_video_cap.read()
            if not ret:
                time.sleep(0.033)  # 30fps的延迟
                continue

            current_time = time.time()
            # 控制发送频率
            if current_time - last_send_time < SEND_INTERVAL:
                time.sleep(0.033)  # 30fps的延迟
                continue

            if self.camera_enabled:  # 只在摄像头开启时发送视频
                # 编码帧为JPEG
                # 进一步降低质量以减少带宽
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 40]
                result, encoded_image = cv2.imencode(
                    '.jpg', frame, encode_param)
                if result:
                    # 转换为base64编码并发送
                    image_data = base64.b64encode(
                        encoded_image.tobytes()).decode('utf-8')

                    # 通过TCP发送多人视频数据
                    video_data = f"/MULTI_VIDEO_DATA|{self.multi_video_room_id}|{self.username}|{image_data}"
                    try:
                        # 尝试通过UDP发送（如果服务器支持）
                        # UDP格式: username:image_data
                        udp_packet = f"{self.username}:{image_data}".encode(
                            'utf-8')
                        # 这里需要知道服务器的UDP地址和端口，暂时使用TCP
                        # self.udp_socket.sendto(udp_packet, (server_addr, server_udp_port))

                        # 目前还是使用TCP发送以确保可靠性
                        self.send_message_raw(video_data)
                    except Exception as e:
                        print(f"发送多人视频数据失败: {e}")
                        break

            last_send_time = current_time
            time.sleep(0.033)  # 30fps的延迟

    def receive_video_via_udp(self):
        """通过UDP接收视频数据"""
        try:
            while self.video_call_active or self.multi_video_active:
                try:
                    # 设置短超时以允许定期检查video_call_active状态
                    self.udp_socket.settimeout(0.5)  # 0.5秒超时
                    data, addr = self.udp_socket.recvfrom(65536)  # 接收最大64KB数据
                    if data:
                        try:
                            # 解析数据格式: sender:image_data
                            decoded_data = data.decode('utf-8')
                            parts = decoded_data.split(':', 1)
                            if len(parts) == 2:
                                sender = parts[0]
                                image_data = parts[1]

                                # 解码base64图像数据
                                img_bytes = base64.b64decode(image_data)
                                nparr = np.frombuffer(img_bytes, np.uint8)
                                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                                if frame is not None:
                                    if self.video_call_active:
                                        # 更新远程视频帧（一对一视频通话）
                                        self.remote_video_frame = frame

                                        # 如果启用了OpenCV窗口，则更新远程视频帧
                                        # 远程视频会在display_combined_video函数中显示在组合窗口中
                                        pass
                                    elif self.multi_video_active:
                                        # 更新多人视频会议中的参与者视频帧
                                        self.update_participant_video(
                                            sender, frame)
                        except Exception as e:
                            print(f"UDP视频数据解析错误: {e}")
                            # 尝试解析TCP格式的多人视频数据
                            try:
                                # TCP格式: /MULTI_VIDEO_DATA|room_id|sender|image_data
                                if decoded_data.startswith('/MULTI_VIDEO_DATA|'):
                                    parts = decoded_data.split('|', 3)
                                    if len(parts) >= 4:
                                        room_id = parts[1]
                                        sender = parts[2]
                                        image_data = parts[3]

                                        # 检查是否是当前房间的数据
                                        if self.multi_video_active and self.multi_video_room_id == room_id:
                                            # 解码base64图像数据
                                            img_bytes = base64.b64decode(
                                                image_data)
                                            nparr = np.frombuffer(
                                                img_bytes, np.uint8)
                                            frame = cv2.imdecode(
                                                nparr, cv2.IMREAD_COLOR)

                                            if frame is not None:
                                                # 更新多人视频会议中的参与者视频帧
                                                self.update_participant_video(
                                                    sender, frame)
                            except Exception as tcp_parse_error:
                                print(f"解析TCP格式多人视频数据错误: {tcp_parse_error}")
                except socket.timeout:
                    # 超时是正常的，继续循环检查video_call_active
                    continue
                except Exception as e:
                    if not (self.video_call_active or self.multi_video_active):  # 如果视频通话已停止，则退出循环
                        break
                    print(f"接收UDP视频数据错误: {e}")
        except Exception as e:
            print(f"接收UDP视频时出错: {e}")
        finally:
            # 设置停止事件
            self.remote_display_stopped.set()
            # 不在这里调用destroyAllWindows，避免多线程冲突
            pass

    def receive_video_data(self, sender, image_data):
        """接收并显示远程视频数据（保留TCP方式以备兼容性）"""
        if self.video_call_active:
            try:
                # 解码base64图像数据
                img_bytes = base64.b64decode(image_data)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # 更新远程视频帧
                    self.remote_video_frame = frame

                    # 如果启用了OpenCV窗口，则更新远程视频帧
                    # 远程视频会在display_combined_video函数中显示在组合窗口中
                    pass

            except Exception as e:
                print(f"视频解码错误: {e}")

    def receive_multi_video_data(self, sender, image_data):
        """接收多人视频会议数据"""
        if self.multi_video_active:
            try:
                # 解码base64图像数据
                img_bytes = base64.b64decode(image_data)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # 更新参与者视频帧
                    if sender in self.multi_video_participants:
                        self.multi_video_participants[sender]['frame'] = frame
                        # 更新UI中的视频显示
                        self.update_participant_video(sender, frame)
                    else:
                        # 如果是新参与者，添加到列表
                        self.multi_video_participants[sender] = {
                            'frame': frame, 'udp_port': None, 'widget': None}
                        # 更新布局
                        self.update_video_layout()

            except Exception as e:
                print(f"多人视频解码错误: {e}")

    def toggle_camera(self):
        """切换摄像头状态"""
        self.camera_enabled = not self.camera_enabled
        if self.camera_enabled:
            self.camera_toggle_btn.config(text="关闭摄像头", bg="#FF6B6B")
        else:
            self.camera_toggle_btn.config(text="开启摄像头", bg="#95EC69")

        # 发送摄像头状态更新
        status = "enabled" if self.camera_enabled else "disabled"
        camera_status_msg = f"/CAMERA_STATUS|{self.multi_video_room_id}|{self.username}|{status}"
        self.send_message_raw(camera_status_msg)

    def refresh_multi_video(self):
        """刷新多人视频会议中的视频显示，重新请求所有参与者视频数据"""
        if self.multi_video_active:
            # 重新请求所有参与者列表
            print("正在刷新多人视频会议...")

            # 重新请求加入消息以同步参与者列表
            join_msg = f"/MULTI_VIDEO_JOIN|{self.multi_video_room_id}|{self.username}"
            self.send_message_raw(join_msg)

            # 重新更新视频布局
            self.update_video_layout()

            # 重启视频传输线程
            if self.video_thread and self.video_thread.is_alive():
                self.video_thread.join(timeout=1)

            # 重新启动视频传输
            self.video_thread = threading.Thread(
                target=self.transmit_multi_video, daemon=True)
            self.video_thread.start()

            print("多人视频会议已刷新")

    def leave_multi_video_call(self):
        """离开多人视频会议"""
        if self.multi_video_active:
            # 发送离开消息
            leave_msg = f"/MULTI_VIDEO_LEAVE|{self.multi_video_room_id}|{self.username}"
            self.send_message_raw(leave_msg)

            # 停止视频流
            self.multi_video_active = False

            # 停止摄像头
            if self.local_video_cap:
                self.local_video_cap.release()

            # 关闭UDP套接字
            if self.udp_socket:
                self.udp_socket.close()

            # 关闭多方视频专用的UDP套接字
            if self.multi_video_send_socket:
                self.multi_video_send_socket.close()

            # 关闭所有参与者的UDP套接字
            for sock in self.multi_video_udp_sockets.values():
                try:
                    sock.close()
                except:
                    pass
            self.multi_video_udp_sockets.clear()

            # 停止所有参与者的接收线程
            for thread in self.multi_video_recv_threads.values():
                # 这里不强制停止线程，而是设置标志位让它们自然退出
                pass
            self.multi_video_recv_threads.clear()

            # 销毁视频窗口
            if self.multi_video_window:
                self.multi_video_window.destroy()
                self.multi_video_window = None

            # 重置线程
            if self.video_thread and self.video_thread.is_alive():
                self.video_thread.join(timeout=1)

            # 重置变量
            self.multi_video_room_id = None
            self.multi_video_participants.clear()
            self.multi_video_layout.clear()

            # 通知用户
            self.add_message_to_history("聊天室", f"系统: 您已离开视频会议")

    def start_multi_video_stream(self):
        """开始多人视频流"""
        # 设置UDP套接字
        self.setup_udp_socket()

        # 启动视频传输线程
        self.video_thread = threading.Thread(
            target=self.transmit_multi_video, daemon=True)
        self.video_thread.start()

    def update_video_layout(self):
        """更新视频布局（旧方法，保留向后兼容）"""
        # 为了向后兼容，调用新的布局更新方法
        if hasattr(self, 'others_video_frame'):
            self.update_others_video_layout()
        else:
            # 如果还没有分割框架，则使用旧方法
            if not self.multi_video_window or not self.multi_video_window.winfo_exists():
                return

            # 清空现有视频显示框架
            for child in self.multi_video_window.winfo_children():
                if 'video_frame' in str(child).lower():
                    child.destroy()
                    break

            # 重新创建视频显示框架
            video_frame = tk.Frame(self.multi_video_window, bg="#F5F5F5")
            video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # 计算网格布局
            num_participants = 0
            # 计算实际有多少参与者（包括自己）
            if self.local_video_cap:
                num_participants += 1
            num_participants += len(
                [u for u in self.multi_video_participants if u != self.username])

            # 根据参与者数量计算网格布局
            if num_participants <= 1:
                cols, rows = 1, 1
            elif num_participants <= 2:
                cols, rows = 2, 1
            elif num_participants <= 4:
                cols, rows = 2, 2
            elif num_participants <= 6:
                cols, rows = 3, 2
            elif num_participants <= 9:
                cols, rows = 3, 3
            else:
                cols, rows = 4, (num_participants + 3) // 4

            # 配置网格权重
            for i in range(rows):
                video_frame.grid_rowconfigure(i, weight=1)
            for j in range(cols):
                video_frame.grid_columnconfigure(j, weight=1)

            idx = 0

            # 首先添加自己的视频（如果有摄像头）
            if self.local_video_cap and self.camera_enabled:
                local_frame = tk.Frame(
                    video_frame, bg="#000000", relief=tk.RAISED, bd=1)
                local_frame.grid(row=idx//cols, column=idx %
                                 cols, padx=2, pady=2, sticky="nsew")

                # 创建本地视频标签
                local_label = tk.Label(local_frame, text=f"我 ({self.username})", bg="#000000",
                                       fg="white", font=("Microsoft YaHei", 9))
                local_label.pack(expand=True, fill=tk.BOTH)

                # 存储标签引用
                if self.username not in self.multi_video_participants:
                    self.multi_video_participants[self.username] = {
                        'frame': None, 'udp_port': None, 'widget': local_label}
                else:
                    self.multi_video_participants[self.username]['widget'] = local_label

                # 立即尝试更新本地视频帧
                self.update_local_video_in_tkinter(local_label)
                idx += 1

            # 添加其他参与者的视频
            for username, info in self.multi_video_participants.items():
                if username == self.username:
                    continue

                participant_frame = tk.Frame(
                    video_frame, bg="#000000", relief=tk.RAISED, bd=1)
                participant_frame.grid(row=idx//cols, column=idx %
                                       cols, padx=2, pady=2, sticky="nsew")

                # 创建参与者视频标签
                participant_label = tk.Label(participant_frame, text=username, bg="#000000",
                                             fg="white", font=("Microsoft YaHei", 9))
                participant_label.pack(expand=True, fill=tk.BOTH)

                # 存储标签引用
                info['widget'] = participant_label

                # 如果已有视频帧，立即更新显示
                if info['frame'] is not None:
                    self.update_participant_video_in_tkinter(
                        participant_label, info['frame'])
                idx += 1

    def update_others_video_layout(self):
        """更新其他参与者的视频布局"""
        if not self.others_video_frame:
            return

        # 清空现有的其他参与者视频框架
        for widget in self.others_video_frame.winfo_children():
            widget.destroy()

        # 获取其他参与者列表
        other_participants = [
            u for u in self.multi_video_participants if u != self.username]

        if not other_participants:
            # 如果没有其他参与者，显示提示信息
            hint_label = tk.Label(self.others_video_frame, text="暂无其他参与者",
                                  bg="#F5F5F5", fg="#999999", font=("Microsoft YaHei", 10))
            hint_label.pack(expand=True, fill=tk.BOTH)
            return

        # 计算网格布局
        num_participants = len(other_participants)
        if num_participants <= 2:
            cols, rows = num_participants, 1
        elif num_participants <= 4:
            cols, rows = 2, 2
        elif num_participants <= 6:
            cols, rows = 3, 2
        elif num_participants <= 9:
            cols, rows = 3, 3
        else:
            cols, rows = 4, (num_participants + 3) // 4

        # 配置网格权重
        for i in range(rows):
            self.others_video_frame.grid_rowconfigure(i, weight=1)
        for j in range(cols):
            self.others_video_frame.grid_columnconfigure(j, weight=1)

        # 创建其他参与者的视频网格
        for idx, username in enumerate(other_participants):
            info = self.multi_video_participants[username]
            row_idx = idx // cols
            col_idx = idx % cols

            participant_frame = tk.Frame(
                self.others_video_frame, bg="#000000", relief=tk.RAISED, bd=1)
            participant_frame.grid(row=row_idx, column=col_idx,
                                   padx=2, pady=2, sticky="nsew")

            # 创建参与者视频标签
            participant_label = tk.Label(participant_frame, text=username, bg="#000000",
                                         fg="white", font=("Microsoft YaHei", 8))
            participant_label.pack(expand=True, fill=tk.BOTH)

            # 存储标签引用
            info['widget'] = participant_label

            # 如果已有视频帧，立即更新显示
            if info['frame'] is not None:
                self.update_participant_video_in_tkinter(
                    participant_label, info['frame'])

    def update_local_video_in_tkinter(self, widget):
        """在Tkinter标签中更新本地视频"""
        if self.local_video_cap and self.camera_enabled:
            ret, frame = self.local_video_cap.read()
            if ret:
                # 调整帧大小以适应显示区域
                resized_frame = cv2.resize(frame, (240, 180))
                # 转换颜色格式从BGR到RGB
                rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                # 转换为Tkinter兼容的PhotoImage格式
                img = Image.fromarray(rgb_frame)
                photo = ImageTk.PhotoImage(image=img)

                # 更新视频显示
                widget.configure(image=photo, text="")
                widget.image = photo  # 保持引用，防止被垃圾回收

                # 每30毫秒更新一次本地视频
                widget.after(
                    30, lambda: self.update_local_video_in_tkinter(widget))

    def update_participant_video_in_tkinter(self, widget, frame):
        """在Tkinter标签中更新参与者视频"""
        # 调整帧大小以适应显示区域
        resized_frame = cv2.resize(frame, (240, 180))
        # 转换颜色格式从BGR到RGB
        rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        # 转换为Tkinter兼容的PhotoImage格式
        img = Image.fromarray(rgb_frame)
        photo = ImageTk.PhotoImage(image=img)

        # 更新视频显示
        widget.configure(image=photo, text="")
        widget.image = photo  # 保持引用，防止被垃圾回收

    def update_participant_video(self, username, frame):
        """更新特定参与者的视频显示"""
        try:
            # 更新参与者的视频帧数据
            if username in self.multi_video_participants:
                self.multi_video_participants[username]['frame'] = frame
                # 如果widget存在，立即更新显示
                widget = self.multi_video_participants[username].get('widget')
                if widget:
                    self.update_participant_video_in_tkinter(widget, frame)
            else:
                # 如果是新参与者，添加到列表
                self.multi_video_participants[username] = {
                    'frame': frame, 'udp_port': None, 'widget': None}
                # 更新布局
                self.update_video_layout()

        except Exception as e:
            print(f"更新参与者视频失败: {e}")


def main():

    root = tk.Tk()
    app = ChatClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
