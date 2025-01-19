import streamlit as st
import time
import paramiko

SHELL_RETURN_BYTES = 65535


def get_shell():
    device_params = dict(
        hostname="192.168.37.126",
        port=22,
        username="tk-ix",
        password="for_ansible",
        look_for_keys=False,
        allow_agent=False,
    )
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(**device_params)
    shell = ssh_client.invoke_shell()
    time.sleep(2)
    shell.recv(SHELL_RETURN_BYTES)
    return shell


def send_command(shell, command):
    print(f"send command: {command}")
    shell.send(f"{command}\n")
    time.sleep(1)
    output = shell.recv(SHELL_RETURN_BYTES)
    print(output)
    return output.decode()

def main():
    if "chat_log" not in st.session_state:
        st.session_state.chat_log = []
    user_msg = st.chat_input("ここにメッセージを入力")
    if "shell" in st.session_state:
        shell = st.session_state.shell
    else:
        shell = get_shell()
        st.session_state.shell = shell

    if user_msg:
        for chat in st.session_state.chat_log:
            with st.chat_message(chat["name"]):
                st.write(chat["msg"])

        with st.chat_message("me"):
            st.write(user_msg)

        res = send_command(shell, user_msg)
        with st.chat_message("bot"):
            res_area = st.empty()
            res_area.code(res)

        st.session_state.chat_log.append({"name": "me", "msg": user_msg})
        st.session_state.chat_log.append({"name": "bot", "msg": res})


if __name__ == "__main__":
    main()
