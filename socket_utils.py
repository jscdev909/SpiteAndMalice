import socket
import struct

HEADER_SIZE = 4

def recv_all(sock: socket.socket, n: int):
    raw_data = b''
    while len(raw_data) < n:
        packet = sock.recv(n - len(raw_data))
        if not packet:
            return None
        raw_data += packet
    return raw_data

def receive_message(sock: socket.socket) -> str:
    raw_msg_len = recv_all(sock, HEADER_SIZE)
    if not raw_msg_len:
        return ""
    msg_len = struct.unpack("!I", raw_msg_len)[0]
    payload = recv_all(sock, msg_len)
    if not payload:
        return ""
    data = payload.decode()

    return data

def send_message(sock: socket.socket, message: str) -> None:
    sock.sendall(struct.pack("!I", len(message)) + message.encode())