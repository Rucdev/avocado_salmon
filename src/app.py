import streamlit as st
import time
import paramiko
import json

# デバイス情報のサンプル（IPアドレス、ユーザー名、パスワード）
with open("device_map.json") as f:
    devices = json.load(f)
SHELL_RETURN_BYTES = 65535

avatar_map = {"me": "👦"}


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
    print(f"send command: {command}")
    shell.send(f"{command}\n")
    time.sleep(1)
    output = shell.recv(SHELL_RETURN_BYTES)
    return output.decode()


def main():
    # チャットの通し番号
    if "stream_serial" not in st.session_state:
        st.session_state.stream_serial = 0

    # サイドバーでデバイス選択
    st.sidebar.title("デバイス選択")
    selected_device_name = st.sidebar.selectbox(
        "デバイスを選択してください", [d["name"] for d in devices]
    )

    # 選択されたデバイスの情報取得
    selected_device = next(d for d in devices if d["name"] == selected_device_name)

    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {"me": {"log": []}}
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

    user_msg = st.chat_input("ここにメッセージを入力")
    serial = st.session_state.stream_serial

    # チャットをコマンドとして送信
    if user_msg:
        st.session_state.chat_sessions["me"]["log"].append(
            {"serial": serial, "msg": user_msg}
        )
        serial += 1
        for device_name, chat_session in st.session_state.chat_sessions.items():
            shell = chat_session.get("shell")
            if shell:
                result = send_command(shell, user_msg)
                # 最初はこちらが入れたコマンドで、最後はプロンプトになるので除外
                result_lines = result.splitlines()
                response = result_lines[1:-1]
                prompt = result_lines[-1]

                st.session_state.chat_sessions[device_name]["log"].append(
                    {"serial": serial, "msg": "  \n".join(response)}
                )
                serial += 1
                st.session_state.chat_sessions[device_name]["log"].append(
                    {"serial": serial, "msg": prompt}
                )
                serial += 1
    st.session_state.stream_serial = serial

    # チャットセッションを一本化して表示
    chat_log = []
    for device_name, chat_session in st.session_state.chat_sessions.items():
        chat_log.extend(
            [
                {
                    "name": device_name,
                    "msg": log.get("msg"),
                    "serial": log.get("serial"),
                }
                for log in chat_session["log"]
            ]
        )
    chat_log.sort(key=lambda x: x["serial"])
    print(chat_log)
    for log in chat_log:
        with st.chat_message(log["name"], avatar=avatar_map.get(log["name"], "🦖")):
            st.write(log["msg"])


if __name__ == "__main__":
    main()
