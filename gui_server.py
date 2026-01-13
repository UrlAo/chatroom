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
        self.video_calls = {}  # 存储视频通话配对：username -> partner_username

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
            # 修改此处，使用"0.0.0.0"而不是特定IP
            self.server_socket.bind(("192.168.110.107", port))
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

            # 保存客户端和用户名的映射，去除可能的空白字符
            self.clients[client_socket] = username.strip()

            # 更新客户端列表
            self.master.after(0, self.update_client_list)

            self.append_message(
                f"{username} ({client_address[0]}:{client_address[1]}) 上线了！")

            # 通知其他人
            self.broadcast(f"【系统】{username} 进入了聊天室", client_socket)

            # 向新连接的客户端发送当前在线用户列表
            current_users = list(self.clients.values())
            user_list_msg = "/USERLIST|" + "|".join(current_users)
            self.send_message(client_socket, user_list_msg)

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
                elif msg.startswith('/FILE|'):
                    # 处理文件传输消息
                    # 首先验证文件消息格式是否正确
                    file_parts = msg.split("|", 3)  # 只分割前3个|
                    if len(file_parts) != 4 or file_parts[0] != "/FILE":
                        # 文件格式不正确
                        error_msg = f"【系统】错误：文件格式不正确"
                        self.send_to_user(username, error_msg)
                        self.append_message(
                            f"{username} 发送的文件格式不正确")
                        continue

                    # 检查是否是私聊文件消息
                    if msg.startswith('@'):
                        # 私聊文件消息格式：@target_user /FILE|filename|filesize|base64data
                        parts = msg.split(' ', 1)
                        if len(parts) == 2:
                            target_user = parts[0][1:].strip()  # 移除@符号并去除多余空格
                            # 对file_content再次使用maxsplit确保正确解析
                            file_parts = parts[1].split("|", 3)  # 只分割前3个|
                            if len(file_parts) == 4 and file_parts[0] == "/FILE":
                                file_content = parts[1]  # 保持原始格式用于转发
                                # 检查目标用户是否存在
                                target_exists = any(
                                    u == target_user for u in self.clients.values())
                                if target_exists:
                                    # 发送给目标用户私聊文件消息
                                    sender_msg = f"[私聊给{target_user}] {username}：{file_content}"
                                    receiver_msg = f"[私聊来自{username}] {username}：{file_content}"

                                    # 发送给发送者确认消息
                                    self.send_to_user(username, sender_msg)
                                    # 发送给接收者文件消息
                                    self.send_to_user(
                                        target_user, receiver_msg)

                                    self.append_message(
                                        f"{username} 私聊发送文件给 {target_user}")
                                else:
                                    # 目标用户不存在，发送错误消息给发送者
                                    error_msg = f"【系统】错误：用户 {target_user} 不在线"
                                    self.send_to_user(username, error_msg)
                                    self.append_message(
                                        f"{username} 尝试私聊发送文件给 {target_user}（用户不在线）")
                            else:
                                # 文件格式不正确，发送错误消息给发送者
                                error_msg = f"【系统】错误：文件格式不正确"
                                self.send_to_user(username, error_msg)
                                self.append_message(
                                    f"{username} 发送的文件格式不正确")
                    else:
                        # 群聊文件消息
                        # 格式：/FILE|filename|filesize|base64data
                        self.append_message(f"{username} 发送了一个文件")
                        # 广播文件消息给其他客户端（不包括发送者）
                        self.broadcast(f"{username}：{msg}", client_socket)
                elif msg.startswith('/VIDEO_CALL_REQUEST|'):
                    # 处理视频通话请求
                    # 格式：/VIDEO_CALL_REQUEST|target_user
                    try:
                        target_user = msg.split('|')[1]
                        # 检查目标用户是否存在
                        target_exists = any(
                            u == target_user for u in self.clients.values())
                        if target_exists:
                            # 发送给目标用户视频通话请求
                            sent = self.send_to_user(
                                target_user, f"/VIDEO_CALL_INVITE|{username}")
                            if sent:
                                self.append_message(
                                    f"{username} 请求与 {target_user} 进行视频通话")
                            else:
                                # 发送失败，通知发起者
                                error_msg = f"【系统】错误：无法连接到 {target_user}"
                                self.send_to_user(username, error_msg)
                                self.append_message(
                                    f"向 {target_user} 发送视频通话请求失败")
                        else:
                            # 目标用户不存在，发送错误消息给发起者
                            error_msg = f"【系统】错误：用户 {target_user} 不在线"
                            self.send_to_user(username, error_msg)
                            self.append_message(
                                f"{username} 尝试视频通话 {target_user}（用户不在线）")
                    except Exception as e:
                        self.append_message(f"处理视频通话请求时出错: {str(e)}")
                elif msg.startswith('/VIDEO_CALL_ACCEPT|'):
                    # 处理视频通话接受
                    # 格式：/VIDEO_CALL_ACCEPT|target_user
                    try:
                        target_user = msg.split('|')[1]
                        # 通知发起者对方接受了视频通话
                        sent = self.send_to_user(
                            target_user, f"/VIDEO_CALL_START|{username}")
                        if sent:
                            # 记录视频通话配对关系
                            self.video_calls[username] = target_user
                            self.video_calls[target_user] = username
                            self.append_message(
                                f"{target_user} 接受了 {username} 的视频通话")
                        else:
                            # 发送失败，通知接受者
                            error_msg = f"【系统】错误：无法通知 {target_user} 视频通话已被接受"
                            self.send_to_user(username, error_msg)
                            self.append_message(f"通知 {target_user} 视频通话接受失败")
                    except Exception as e:
                        self.append_message(f"处理视频通话接受时出错: {str(e)}")
                elif msg.startswith('/VIDEO_CALL_REJECT|'):
                    # 处理视频通话拒绝
                    # 格式：/VIDEO_CALL_REJECT|target_user
                    try:
                        target_user = msg.split('|')[1]
                        # 通知发起者对方拒绝了视频通话
                        sent = self.send_to_user(
                            target_user, f"/VIDEO_CALL_REJECTED|{username}")
                        if sent:
                            self.append_message(
                                f"{target_user} 拒绝了 {username} 的视频通话")
                        else:
                            # 发送失败，通知拒绝者
                            error_msg = f"【系统】错误：无法通知 {target_user} 视频通话已被拒绝"
                            self.send_to_user(username, error_msg)
                            self.append_message(f"通知 {target_user} 视频通话拒绝失败")
                    except Exception as e:
                        self.append_message(f"处理视频通话拒绝时出错: {str(e)}")
                elif msg.startswith('/VIDEO_CALL_END|'):
                    # 处理视频通话结束
                    # 格式：/VIDEO_CALL_END|target_user
                    try:
                        target_user = msg.split('|')[1]
                        # 通知对方视频通话已结束
                        sent = self.send_to_user(
                            target_user, f"/VIDEO_CALL_ENDED|{username}")
                        if sent:
                            # 清除视频通话配对关系
                            if username in self.video_calls:
                                del self.video_calls[username]
                            if target_user in self.video_calls:
                                del self.video_calls[target_user]
                            self.append_message(
                                f"{username} 与 {target_user} 的视频通话已结束")
                        else:
                            # 发送失败，通知发起结束者
                            error_msg = f"【系统】错误：无法通知 {target_user} 视频通话已结束"
                            self.send_to_user(username, error_msg)
                            self.append_message(f"通知 {target_user} 视频通话结束失败")
                    except Exception as e:
                        self.append_message(f"处理视频通话结束时出错: {str(e)}")
                elif msg.startswith('/VIDEO_DATA|'):
                    # 处理视频数据
                    # 格式：/VIDEO_DATA|target_user|video_data
                    try:
                        parts = msg.split('|', 2)  # 最多分割为3部分
                        target_user = parts[1]
                        video_data = parts[2]
                        # 转发视频数据给目标用户
                        video_forward = f"/VIDEO_DATA|{username}|{video_data}"
                        self.send_to_user(target_user, video_forward)
                        # 服务器不记录视频数据，以保护隐私
                    except IndexError:
                        self.append_message(f"视频数据格式错误: {username}")
                elif msg.startswith('/MULTI_VIDEO_INVITE|'):
                    # 处理多人视频会议邀请
                    # 格式：/MULTI_VIDEO_INVITE|room_id|inviter
                    try:
                        parts = msg.split('|', 2)
                        room_id = parts[1]
                        inviter = parts[2]

                        # 广播邀请给所有用户（除了发起者）
                        invite_msg = f"/MULTI_VIDEO_INVITE|{room_id}|{inviter}"
                        self.broadcast(invite_msg, client_socket)

                        self.append_message(f"{inviter} 发起了多人视频会议，邀请所有在线用户")
                    except IndexError:
                        self.append_message(f"多人视频邀请格式错误: {username}")
                elif msg.startswith('/MULTI_VIDEO_JOIN|'):
                    # 处理多人视频会议加入
                    # 格式：/MULTI_VIDEO_JOIN|room_id|username
                    try:
                        parts = msg.split('|', 2)
                        room_id = parts[1]
                        joining_user = parts[2]

                        # 广播给同一房间的其他参与者
                        join_msg = f"/MULTI_VIDEO_JOIN|{room_id}|{joining_user}"
                        # 只发送给同一房间的其他用户
                        for client_sock, user_name in self.clients.items():
                            if user_name != joining_user:  # 不发送给发起者
                                self.send_message(client_sock, join_msg)

                        self.append_message(f"{joining_user} 加入了多人视频会议")
                    except IndexError:
                        self.append_message(f"多人视频加入格式错误: {username}")
                elif msg.startswith('/MULTI_VIDEO_LEAVE|'):
                    # 处理多人视频会议离开
                    # 格式：/MULTI_VIDEO_LEAVE|room_id|username
                    try:
                        parts = msg.split('|', 2)
                        room_id = parts[1]
                        leaving_user = parts[2]

                        # 广播给同一房间的其他参与者
                        leave_msg = f"/MULTI_VIDEO_LEAVE|{room_id}|{leaving_user}"
                        # 只发送给同一房间的其他用户
                        for client_sock, user_name in self.clients.items():
                            if user_name != leaving_user:  # 不发送给离开者
                                self.send_message(client_sock, leave_msg)

                        self.append_message(f"{leaving_user} 离开了多人视频会议")
                    except IndexError:
                        self.append_message(f"多人视频离开格式错误: {username}")
                elif msg.startswith('/MULTI_VIDEO_DATA|'):
                    # 处理多人视频数据
                    # 格式：/MULTI_VIDEO_DATA|room_id|sender|video_data
                    try:
                        parts = msg.split('|', 3)  # 分割为4部分
                        room_id = parts[1]
                        sender = parts[2]
                        video_data = parts[3]

                        # 转发给同一房间的其他参与者
                        video_forward = f"/MULTI_VIDEO_DATA|{room_id}|{sender}|{video_data}"
                        # 只转发给房间内的其他用户
                        for client_sock, user_name in self.clients.items():
                            if user_name != sender:  # 不转发给自己
                                self.send_message(client_sock, video_forward)

                        # 服务器不记录视频数据，以保护隐私
                    except IndexError:
                        self.append_message(f"多人视频数据格式错误: {username}")
                elif msg.startswith('/CAMERA_STATUS|'):
                    # 处理摄像头状态更新
                    # 格式：/CAMERA_STATUS|room_id|username|status
                    try:
                        parts = msg.split('|', 3)
                        room_id = parts[1]
                        user_name = parts[2]
                        status = parts[3]

                        # 转发给同一房间的其他参与者
                        status_msg = f"/CAMERA_STATUS|{room_id}|{user_name}|{status}"
                        for client_sock, client_user_name in self.clients.items():
                            if client_user_name != user_name:  # 不转发给状态更改者
                                self.send_message(client_sock, status_msg)

                        # 不在聊天室显示摄像头状态更新，只在服务器后台记录
                        # self.append_message(f"{user_name} 摄像头状态变为: {status}")
                    except IndexError:
                        self.append_message(f"摄像头状态格式错误: {username}")
                elif msg == '/REQUEST_USERLIST':
                    # 处理用户列表请求
                    current_users = list(self.clients.values())
                    user_list_msg = "/USERLIST|" + "|".join(current_users)
                    self.send_message(client_socket, user_list_msg)
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

                # 检查用户是否正在进行视频通话
                if username in self.video_calls:
                    # 通知视频通话伙伴用户已下线
                    partner = self.video_calls[username]
                    offline_msg = f"/VIDEO_CALL_ENDED|{username} (已离线)"
                    self.send_to_user(partner, offline_msg)
                    # 清除视频通话配对
                    del self.video_calls[username]
                    if partner in self.video_calls:
                        del self.video_calls[partner]
                    self.append_message(f"{username} 下线，已通知视频通话伙伴 {partner}")

                del self.clients[client_socket]

                # 更新客户端列表
                self.master.after(0, self.update_client_list)

                # 通知其他客户端更新用户列表
                current_users = list(self.clients.values())
                user_list_msg = "/USERLIST|" + "|".join(current_users)
                self.broadcast(user_list_msg, client_socket)

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
