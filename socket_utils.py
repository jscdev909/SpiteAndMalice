HEADER_SIZE = 4

def recv_all(sock: socket.socket, n: int):
    raw_data = b''
    while len(raw_data) < n:
        packet = sock.recv(n - len(raw_data))
        if not packet:
            return None
        raw_data += packet
    return raw_data