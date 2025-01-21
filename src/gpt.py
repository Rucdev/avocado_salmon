import streamlit as st
import paramiko
from threading import Thread
from queue import Queue
import time
import json

# デバイス情報のサンプル（IPアドレス、ユーザー名、パスワード）
devices = json.loads("device_map.json")
SHELL_RETURN_BYTES = 65535


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
    コマンドをシェルに送信し、結果を取得
    """
    shell.send(f"{command}\n")
    time.sleep(1)  # 応答待ち
    output = shell.recv(SHELL_RETURN_BYTES)
    return output.decode()

def main():
    # セッション状態の初期化
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}  # 各デバイスのチャットセッションを管理

    st.title("SSH Chatroom Manager")

    # サイドバーでデバイス選択
    st.sidebar.title("デバイス選択")
    selected_device_name = st.sidebar.selectbox("デバイスを選択してください", [d["name"] for d in devices])

    # 選択されたデバイスの情報取得
    selected_device = next(d for d in devices if d["name"] == selected_device_name)

    # チャットセッションを作成
    if selected_device_name not in st.session_state.chat_sessions:
        # 新しいセッションを初期化
        ssh_client, shell = get_shell(
            selected_device["host"],
            selected_device["username"],
            selected_device["password"],
        )
        st.session_state.chat_sessions[selected_device_name] = {
            "ssh_client": ssh_client,
            "shell": shell,
            "log": [],
        }

    # 現在のセッションを取得
    session = st.session_state.chat_sessions[selected_device_name]
    shell = session["shell"]

    # チャットインターフェイス
    st.subheader(f"チャットルーム: {selected_device_name}")

    # ユーザーの入力
    user_msg = st.chat_input("ここにメッセージを入力")
    if user_msg:
        # 入力を表示
        st.chat_message("me").write(user_msg)

        # シェルにコマンドを送信
        res = send_command(shell, user_msg)

        # ログに保存
        session["log"].append({"name": "me", "msg": user_msg})
        session["log"].append({"name": "bot", "msg": res})

    # チャットログの表示
    for chat in session["log"]:
        with st.chat_message(chat["name"]):
            if chat["name"] == "bot":
                st.code(chat["msg"])
            else:
                st.write(chat["msg"])

    # セッションを閉じるボタン
    if st.sidebar.button("セッションを閉じる"):
        shell.close()
        session["ssh_client"].close()
        del st.session_state.chat_sessions[selected_device_name]
        st.sidebar.success(f"{selected_device_name} のセッションを終了しました。")

if __name__ == "__main__":
    main()
