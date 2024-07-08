import uuid
import socket
import threading


class Netcat:
    def __init__(self, socket_timeout=2):
        self.clients = {}
        self.connect_socket = None
        self.listener_socket = None
        self.listener_thread = None
        self.listener_running = False
        self.socket_timeout = socket_timeout

    def connect(self, ip,  port):
        self.connect_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            uid = str(uuid.uuid4())
            self.connect_socket.connect((ip, port))
            self.clients[uid] = self.connect_socket
            self.send(uid, b"client hello")
            return uid
        except Exception as e:
            print(f"[ERROR] {e}")
            return None

    def _listen_for_connections(self):
        if not self.listener_socket:
            return

        self.listener_socket.settimeout(self.socket_timeout)

        while self.listener_running:
            try:
                client_socket, client_addr = self.listener_socket.accept()
            except socket.timeout:
                continue

            uid = str(uuid.uuid4())
            self.clients[uid] = client_socket

            # Wait for client hello
            response = self.recv(uid).decode().strip()
            if response != "client hello":
                raise "Protocol error: Didnt not recieve a client hello."

            print(f"[INFO] Accepted connection from {client_addr}")

        self.listener_socket.settimeout(0)
        print("[INFO] listener has stopped.")
        self.listener_socket = None

    def listen(self, port_number=4444, max_clients=5):
        if not self.listener_running:
            # Create the socket server
            self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener_socket.bind(("0.0.0.0", port_number))
            self.listener_socket.listen(max_clients)
            self.listener_running = True
            # Start the server thread
            self.listener_thread = threading.Thread(target=self._listen_for_connections)
            self.listener_thread.daemon = True
            self.listener_thread.start()

            print(f"[INFO] Listening on 0.0.0.0:{port_number}")

        return self.listener_running

    def close(self):
        for uid in self.clients:
            try:
                self.clients[uid].close()
            except Exception as e:
                print(f"[ERROR] Error closing connection: {e}")
                continue

        if self.connect_socket:
            try:
                self.connect_socket.close()
            except Exception as e:
                print(f"[ERROR] Error closing main connection: {e}")
            self.connect_socket = None

        self.clients = {}

        if self.listener_running:
            self.listener_running = False

        if self.listener_thread:
            self.listener_thread.join()

        self.listener_thread = None

        if self.listener_socket:
            try:
                self.listener_socket.close()
            except Exception as e:
                print(f"[ERROR] Error closing listener connection: {e}")

        self.listener_socket = None

    def close_conn(self, uid):
        if uid in self.clients:
            self.clients[uid].close()

    def send(self, uid, message: bytes):
        connection = self.clients[uid]
        if connection:
            if not message.endswith(b"\n"):
                message = message + b"\n"

            try:
                # Send the message length want wait for conformation of recv
                connection.send(str(len(message)).encode())

                if connection.recv(2) != b"ok":
                    raise "Protocol error: Did not receive ok from to confirm message length"

                connection.sendall(message)
            except Exception as e:
                print(f"[ERROR] Error sending message: {e}")

    def recv(self, uid, msg_size=1024):
        response = b""

        if uid not in self.clients:
            print(uid)
            print("unknown uid")
            return response

        connection = self.clients[uid]

        if not connection:
            return response

        try:
            # Get the message length and confirm we received the length
            try:
                message_len = int(connection.recv(msg_size).decode().strip())
            except ValueError:
                return response

            connection.send(b"ok")

            # receive the message
            chunk = connection.recv(message_len)
            response += chunk

            while len(response) != message_len:
                chunk = connection.recv(message_len)
                if not chunk:
                    break
                response += chunk

        except Exception as e:
            print(f"[ERROR] Error receiving message: {e}")

        return response

