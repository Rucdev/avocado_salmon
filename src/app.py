import streamlit as st
import time
import paramiko
import json
import sqlite3
import os
from datetime import datetime
import re

# データベースファイルのパス
DB_PATH = "db.sqlite3"

# デバイス情報のサンプル（IPアドレス、ユーザー名、パスワード）
with open("src/device_map.json") as f:
    devices = json.load(f)
SHELL_RETURN_BYTES = 65535

avatar_map = {"user": "👦"}


def init_database():
    """
    SQLiteデータベースの初期化とテーブル作成
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # DEVICEテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS DEVICE (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ip_address TEXT NOT NULL,
        port INTEGER NOT NULL DEFAULT 22,
        username TEXT NOT NULL,
        password TEXT NOT NULL
    )
    ''')

    # ROOMテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ROOM (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )
    ''')

    # SESSIONテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS SESSION (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER NOT NULL,
        room_id INTEGER NOT NULL,
        FOREIGN KEY (device_id) REFERENCES DEVICE(id),
        FOREIGN KEY (room_id) REFERENCES ROOM(id)
    )
    ''')

    # CHATテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS CHAT (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES SESSION(id)
    )
    ''')

    # デバイスマップからデバイスをインポート（既存のものは更新）
    for device in devices:
        cursor.execute('''
        SELECT id FROM DEVICE WHERE name = ?
        ''', (device["name"],))
        
        device_data = (
            device["name"], 
            device["host"], 
            22, 
            device["username"], 
            device["password"]
        )
        
        if cursor.fetchone():
            cursor.execute('''
            UPDATE DEVICE 
            SET ip_address = ?, port = ?, username = ?, password = ?
            WHERE name = ?
            ''', (device["host"], 22, device["username"], device["password"], device["name"]))
        else:
            cursor.execute('''
            INSERT INTO DEVICE (name, ip_address, port, username, password)
            VALUES (?, ?, ?, ?, ?)
            ''', device_data)

    # デフォルトのルームが存在しない場合は作成
    cursor.execute('SELECT id FROM ROOM WHERE name = ?', ('デフォルト',))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO ROOM (name) VALUES (?)', ('デフォルト',))

    conn.commit()
    conn.close()


def get_devices_from_db():
    """
    データベースからデバイス情報を取得
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, ip_address, port, username, password FROM DEVICE')
    devices_db = [
        {
            "id": row[0],
            "name": row[1],
            "host": row[2],
            "port": row[3],
            "username": row[4],
            "password": row[5],
            "avatar": next((d["avatar"] for d in devices if d["name"] == row[1]), "🦖")
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return devices_db


def get_rooms_from_db():
    """
    データベースからルーム情報を取得
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM ROOM')
    rooms = [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
    conn.close()
    return rooms


def create_room(room_name):
    """
    新しいルームを作成
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO ROOM (name) VALUES (?)', (room_name,))
    room_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return room_id


def get_or_create_session(device_id, room_id):
    """
    デバイスとルームのセッションを取得または作成
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM SESSION WHERE device_id = ? AND room_id = ?', (device_id, room_id))
    session = cursor.fetchone()
    
    if session:
        session_id = session[0]
    else:
        cursor.execute('INSERT INTO SESSION (device_id, room_id) VALUES (?, ?)', (device_id, room_id))
        session_id = cursor.lastrowid
        conn.commit()
    
    conn.close()
    return session_id


def save_chat_message(session_id, message):
    """
    チャットメッセージをデータベースに保存
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO CHAT (session_id, message) VALUES (?, ?)', (session_id, message))
    conn.commit()
    conn.close()


def get_chat_history(room_id):
    """
    指定されたルームのチャット履歴を取得
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ルーム内のすべてのセッションとそれに関連するチャットを取得
    cursor.execute('''
    SELECT c.id, s.id, d.name, c.message, c.created_at, d.id
    FROM CHAT c
    JOIN SESSION s ON c.session_id = s.id
    JOIN DEVICE d ON s.device_id = d.id
    WHERE s.room_id = ?
    ORDER BY c.created_at
    ''', (room_id,))
    
    chat_history = [
        {
            "chat_id": row[0],
            "session_id": row[1],
            "device_name": row[2],
            "message": row[3],
            "created_at": row[4],
            "device_id": row[5]
        }
        for row in cursor.fetchall()
    ]
    
    conn.close()
    return chat_history


def get_shell(host, username, password):
    """
    指定されたデバイスに接続し、SSHシェルを取得
    """
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(host, username=username, password=password)
    shell = ssh_client.invoke_shell()
    time.sleep(2)
    shell.recv(SHELL_RETURN_BYTES)
    return ssh_client, shell


def send_command(shell, command):
    """
    シェルにコマンドを送信し、結果を取得
    """
    print(f"send command: {command}")
    shell.send(f"{command}\n")
    time.sleep(1)
    output = shell.recv(SHELL_RETURN_BYTES)
    return output.decode()


def parse_command(message):
    """
    メッセージを解析し、メンションとコマンドを抽出
    @デバイス名 コマンド の形式の場合はユニキャスト、それ以外はブロードキャスト
    """
    mention_pattern = r'^@(\S+)\s+(.+)$'
    match = re.match(mention_pattern, message)
    
    if match:
        # ユニキャストメッセージ
        target_device = match.group(1)
        command = match.group(2)
        return {"type": "unicast", "target": target_device, "command": command}
    else:
        # ブロードキャストメッセージ
        return {"type": "broadcast", "command": message}


@st.dialog("デバイスの招待")
def show_invite_modal():
    """デバイス招待用のモーダル画面を表示"""
    # 現在のルームID
    current_room_id = st.session_state.current_room_id
    
    # データベースからデバイス一覧を取得
    devices_db = get_devices_from_db()
    
    # 既に招待済みのデバイスを除外
    invited_device_ids = [session["device_id"] for session in st.session_state.active_sessions]
    available_devices = [d for d in devices_db if d["id"] not in invited_device_ids]
    
    if not available_devices:
        st.warning("招待可能なデバイスがありません")
        return
    
    selected_device_name = st.selectbox(
        "チャットに招待するデバイスを選択", 
        [d["name"] for d in available_devices]
    )

    if st.button("招待する"):
        if selected_device_name:
            device = next(
                (d for d in available_devices if d["name"] == selected_device_name), 
                None
            )
            if device:
                with st.spinner(f"{selected_device_name}を招待中..."):
                    # SSHセッションを確立
                    ssh_client, shell = get_shell(
                        device["host"],
                        device["username"],
                        device["password"],
                    )
                    
                    # セッションをデータベースに記録
                    session_id = get_or_create_session(device["id"], current_room_id)
                    
                    # アクティブセッションに追加
                    st.session_state.active_sessions.append({
                        "session_id": session_id,
                        "device_id": device["id"],
                        "device_name": device["name"],
                        "ssh_client": ssh_client,
                        "shell": shell,
                        "avatar": device.get("avatar", "🦖"),
                    })
                    
                    # 接続メッセージをチャット履歴に追加
                    welcome_msg = f"{device['name']}がチャットに参加しました"
                    save_chat_message(session_id, welcome_msg)
                    
                st.success(f"{selected_device_name}をチャットに招待しました")
                time.sleep(1)
                st.rerun()


@st.dialog("新規ルーム作成")
def show_create_room_modal():
    """新規ルーム作成用のモーダル画面を表示"""
    room_name = st.text_input("ルーム名")
    
    if st.button("作成"):
        if room_name:
            # 新しいルームをデータベースに作成
            room_id = create_room(room_name)
            st.success(f"ルーム「{room_name}」を作成しました")
            
            # 新しいルームに切り替え
            st.session_state.current_room_id = room_id
            st.session_state.active_sessions = []
            
            time.sleep(1)
            st.rerun()


def main():
    # データベースの初期化
    init_database()
    
    # セッション状態の初期化
    if "current_room_id" not in st.session_state:
        # デフォルトルームのIDを取得
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM ROOM WHERE name = ?', ('デフォルト',))
        default_room = cursor.fetchone()
        conn.close()
        
        if default_room:
            st.session_state.current_room_id = default_room[0]
        else:
            # デフォルトルームがない場合は作成
            st.session_state.current_room_id = create_room("デフォルト")
    
    if "active_sessions" not in st.session_state:
        st.session_state.active_sessions = []
    
    # ユーザーセッションの初期化（ユーザー自身もデバイスとして扱う）
    if not any(s["device_name"] == "user" for s in st.session_state.active_sessions):
        # ユーザーデバイスの存在確認
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM DEVICE WHERE name = ?', ('user',))
        user_device = cursor.fetchone()
        
        if not user_device:
            # ユーザーデバイスがない場合は作成
            cursor.execute('''
            INSERT INTO DEVICE (name, ip_address, port, username, password)
            VALUES (?, ?, ?, ?, ?)
            ''', ('user', '127.0.0.1', 22, 'user', 'password'))
            user_device_id = cursor.lastrowid
            conn.commit()
        else:
            user_device_id = user_device[0]
        
        # ユーザーセッションの作成
        session_id = get_or_create_session(user_device_id, st.session_state.current_room_id)
        
        # アクティブセッションに追加
        st.session_state.active_sessions.append({
            "session_id": session_id,
            "device_id": user_device_id,
            "device_name": "user",
            "ssh_client": None,
            "shell": None,
            "avatar": "👦",
        })
        
        conn.close()
    
    # サイドバーの設定
    st.sidebar.title("ルーム管理")
    
    # ルーム一覧を表示
    rooms = get_rooms_from_db()
    room_names = [room["name"] for room in rooms]
    current_room_name = next((r["name"] for r in rooms if r["id"] == st.session_state.current_room_id), "不明")
    
    st.sidebar.subheader(f"現在のルーム: {current_room_name}")
    
    # ルーム切り替え
    selected_room = st.sidebar.selectbox("ルームを選択", room_names, index=room_names.index(current_room_name))
    if st.sidebar.button("ルームに移動"):
        selected_room_id = next((r["id"] for r in rooms if r["name"] == selected_room), None)
        if selected_room_id and selected_room_id != st.session_state.current_room_id:
            # アクティブなSSHセッションをクローズ
            for session in st.session_state.active_sessions:
                if session.get("ssh_client"):
                    session["ssh_client"].close()
            
            # ルームを切り替え
            st.session_state.current_room_id = selected_room_id
            st.session_state.active_sessions = []
            
            # ユーザーセッションを初期化
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM DEVICE WHERE name = ?', ('user',))
            user_device_id = cursor.fetchone()[0]
            session_id = get_or_create_session(user_device_id, selected_room_id)
            
            st.session_state.active_sessions.append({
                "session_id": session_id,
                "device_id": user_device_id,
                "device_name": "user",
                "ssh_client": None,
                "shell": None,
                "avatar": "👦",
            })
            
            conn.close()
            st.rerun()
    
    # 新規ルーム作成ボタン
    if st.sidebar.button("新規ルーム作成"):
        show_create_room_modal()
    
    # デバイス管理
    st.sidebar.title("デバイス管理")
    if st.sidebar.button("デバイスを招待"):
        show_invite_modal()
    
    # 参加中のデバイス表示と削除
    st.sidebar.title("参加中のデバイス")
    for session in st.session_state.active_sessions:
        device_name = session["device_name"]
        st.sidebar.text(f"・{device_name}")
        
        if device_name != "user":
            if st.sidebar.button(f"{device_name}の削除", key=f"remove_{device_name}"):
                # SSHセッションを終了する
                if session.get("ssh_client"):
                    session["ssh_client"].close()
                
                # アクティブセッションから削除
                st.session_state.active_sessions = [
                    s for s in st.session_state.active_sessions if s["device_name"] != device_name
                ]
                
                st.sidebar.success(f"{device_name}をチャットから削除しました")
                st.rerun()
    
    # チャット履歴の表示
    st.title(f"チャットルーム: {current_room_name}")
    
    # データベースからチャット履歴を取得
    chat_history = get_chat_history(st.session_state.current_room_id)
    
    # チャット履歴を表示
    for chat in chat_history:
        device_name = chat["device_name"]
        message = chat["message"]
        
        # アバターの取得
        avatar = "👦" if device_name == "user" else next(
            (s["avatar"] for s in st.session_state.active_sessions if s["device_name"] == device_name),
            next((d["avatar"] for d in devices if d["name"] == device_name), "🦖")
        )
        
        with st.chat_message(device_name, avatar=avatar):
            st.write(message)
    
    # メッセージ入力
    user_msg = st.chat_input("ここにメッセージを入力")
    
    # チャットをコマンドとして送信
    if user_msg:
        # ユーザーのセッションIDを取得
        user_session = next((s for s in st.session_state.active_sessions if s["device_name"] == "user"), None)
        if user_session:
            # ユーザーメッセージをデータベースに保存
            save_chat_message(user_session["session_id"], user_msg)
            
            # コマンドの解析
            parsed_cmd = parse_command(user_msg)
            
            if parsed_cmd["type"] == "unicast":
                # ユニキャストメッセージ
                target_device = parsed_cmd["target"]
                command = parsed_cmd["command"]
                
                # 対象デバイスのセッションを検索
                target_session = next(
                    (s for s in st.session_state.active_sessions if s["device_name"] == target_device),
                    None
                )
                
                if target_session and target_session.get("shell"):
                    # コマンドを送信
                    result = send_command(target_session["shell"], command)
                    
                    # 結果を処理
                    result_lines = result.splitlines()
                    response = result_lines[1:-1]
                    prompt = result_lines[-1]
                    
                    # レスポンスをデータベースに保存
                    if response:
                        save_chat_message(
                            target_session["session_id"],
                            "  \n".join(response)
                        )
                    
                    # プロンプトをデータベースに保存
                    save_chat_message(target_session["session_id"], prompt)
                else:
                    # 対象デバイスが見つからない場合
                    error_msg = f"エラー: デバイス '{target_device}' は見つかりません"
                    save_chat_message(user_session["session_id"], error_msg)
            else:
                # ブロードキャストメッセージ
                command = parsed_cmd["command"]
                
                # すべてのアクティブなデバイスにコマンドを送信
                for session in st.session_state.active_sessions:
                    if session["device_name"] != "user" and session.get("shell"):
                        # コマンドを送信
                        result = send_command(session["shell"], command)
                        
                        # 結果を処理
                        result_lines = result.splitlines()
                        response = result_lines[1:-1]
                        prompt = result_lines[-1]
                        
                        # レスポンスをデータベースに保存
                        if response:
                            save_chat_message(
                                session["session_id"],
                                "  \n".join(response)
                            )
                        
                        # プロンプトをデータベースに保存
                        save_chat_message(session["session_id"], prompt)
            
            # 画面を更新
            st.rerun()


if __name__ == "__main__":
    main()
