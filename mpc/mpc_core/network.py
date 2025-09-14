# mpc_core/network.py
import asyncio
import pickle

class Party:
    """一个参与方，负责发送/接收 shares"""
    def __init__(self, id, port, peers):
        self.id = id
        self.port = port
        self.peers = peers  # {party_id: port}
        self.data = {}

    async def handler(self, reader, writer):
        raw = await reader.read(4096)
        msg = pickle.loads(raw)
        self.data[msg['from']] = msg['data']
        writer.close()

    async def run_server(self):
        server = await asyncio.start_server(self.handler, "127.0.0.1", self.port)
        async with server:
            await server.serve_forever()

    async def send(self, peer_id, data):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.peers[peer_id])
        msg = {'from': self.id, 'data': data}
        writer.write(pickle.dumps(msg))
        await writer.drain()
        writer.close()

async def run_server(party: Party):
    await party.run_server()

async def run_client(party: Party, peer_id: int, data):
    await party.send(peer_id, data)
