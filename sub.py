import curio
from curioredis.connection import Connection


async def main():
    sock = await curio.open_connection("127.0.0.1", 6379)
    conn = Connection(sock)
    await conn.send_command("SUBSCRIBE", "test")
    while True:
        res = await conn.recv_response()
        print(res)


curio.run(main)
