import hashlib
import json
import time
import zlib
import os
import socket
import threading
import queue
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
try:
    from blake3 import blake3
    BLAKE3_BACKEND = 'blake3'
except ImportError:
    from hashlib import blake2b as _blake2b

    class _B2:

        def __init__(self, data=b''):
            self._data = data

        def digest(self, length=32):
            return _blake2b(self._data, digest_size=length).digest()

    def blake3(data=b''):
        return _B2(data)
    BLAKE3_BACKEND = 'blake2b-fallback'
'\nCYTHAN MAINNET\nExperimental standalone proof-of-work blockchain.\n\nP2P:\n    0.0.0.0:8443\n\nLOCAL CONTROL:\n    127.0.0.1:8444\n\nPython:\n    3.10+\n\nDependency:\n    pip install blake3\n'
NETWORK = 'CYTHAN-MAINNET'
VERSION = '1.0.0'
CHAIN_ID = 'CYTHAN-01'
P2P_PROTOCOL = 'CYTHAN/1'
CYTHANX_MINING_PROTOCOL = 'CYTHANX-MINING/1'
CYTHANX_MINING_METHODS = (
    'mining.subscribe',
    'mining.authorize',
    'mining.notify',
    'mining.set_target',
    'mining.submit',
    'mining.ping',
)
DATA_DIR = Path('data/cythan_mainnet')
CHAIN_FILE = DATA_DIR / 'chain.json'
STATE_FILE = DATA_DIR / 'state.json'
P2P_HOST = '0.0.0.0'
P2P_PORT = 8443
CONTROL_HOST = '127.0.0.1'
CONTROL_PORT = 8444
TARGET_BLOCK_TIME = 60
BLOCK_INTERVAL = TARGET_BLOCK_TIME
DIFFICULTY_WINDOW = 60
INITIAL_REWARD = 50
HALVING_INTERVAL = 210000
MAX_MONEY = 10500000
SCRYPT_N = 1024
SCRYPT_R = 1
SCRYPT_P = 1
SCRYPT_DKLEN = 32
INITIAL_TARGET = int('0000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', 16)
MAX_TARGET = INITIAL_TARGET
VECTOR_KEY = b'CYTHAN-MAINNET-V1'
CYTHAN_ADDRESS_VERSION = b'<'
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
MINER_ADDRESS = 'CYTHAN-MINER'
RUNNING = True

# Optional Stratum pool configuration. Values are prompted at startup unless
# supplied through environment variables. Passwords are never written to chain state.
POOL_ENABLED = os.getenv("CYTHANX_POOL_ENABLED", "1").lower() not in {"0", "false", "no"}
POOL_URL = os.getenv("CYTHANX_POOL_URL", "")
POOL_USER = os.getenv("CYTHANX_POOL_USER", "")
POOL_PASS = os.getenv("CYTHANX_POOL_PASS", "")
MINER_THREADS = max(1, int(os.getenv("CYTHANX_THREADS", str(max(1, os.cpu_count() or 1)))))
KEEPALIVE = os.getenv("CYTHANX_KEEPALIVE", "1").lower() not in {"0", "false", "no"}
DRAGONFLY_WORKER = os.getenv("CYTHANX_DRAGONFLY_WORKER", "1").lower() not in {"0", "false", "no"}
POOL_TIMEOUT = float(os.getenv("CYTHANX_POOL_TIMEOUT", "15"))

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def double_sha256(data: bytes) -> bytes:
    return sha256(sha256(data))

def blake3_256(data: bytes) -> bytes:
    return blake3(data).digest(length=32)

def scrypt256(data: bytes, salt: bytes | None=None) -> bytes:
    if salt is None:
        salt = data
    return hashlib.scrypt(password=data, salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)

def pbkdf2_sha512(data: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha512', data, salt, 2048, 64)

def joaat(data: bytes) -> int:
    h = 0
    for byte in data:
        h = h + byte & 4294967295
        h = h + (h << 10 & 4294967295) & 4294967295
        h ^= h >> 6
    h = h + (h << 3 & 4294967295) & 4294967295
    h ^= h >> 11
    h = h + (h << 15 & 4294967295) & 4294967295
    return h & 4294967295

def cythan_vector() -> dict:
    vector = blake3_256(b'CYTHAN|VECTOR|' + CHAIN_ID.encode() + b'|' + VECTOR_KEY)
    return {'vector': vector, 'joaat': joaat(vector)}

def cythanize(payload: bytes, previous: bytes=b'\x00' * 32) -> dict:
    vector_data = cythan_vector()
    vector = vector_data['vector']
    vector_joaat = vector_data['joaat']
    joaat_bytes = vector_joaat.to_bytes(4, 'big')
    state = blake3_256(b'CYTHAN|STATE|' + payload + previous + vector + joaat_bytes)
    sha_state = double_sha256(b'CYTHAN|SHA256|' + state)
    scrypt_state = scrypt256(b'CYTHAN|SCRYPT|' + sha_state)
    commitment = blake3_256(b'CYTHAN|COMMITMENT|' + vector + joaat_bytes + state + sha_state + scrypt_state)
    return {'vector': vector.hex(), 'joaat': f'{vector_joaat:08x}', 'state': state.hex(), 'sha256': sha_state.hex(), 'scrypt': scrypt_state.hex(), 'commitment': commitment.hex()}

def transmogrify(payload: bytes, previous: bytes=b'\x00' * 32) -> dict:
    first = cythanize(payload, previous)
    transformed = canonical({'type': 'CYTHAN-TRANSMOGRIFICATION', 'network': NETWORK, 'chain_id': CHAIN_ID, 'input': payload.hex(), 'cythan': first})
    second = cythanize(transformed, bytes.fromhex(first['commitment']))
    return {'type': 'TRANSMOGRIFIED-CYTHAN', 'input': payload.hex(), 'first': first, 'final': second}

def joatt(payload: bytes, previous_state: bytes=b'\x00' * 32) -> dict:
    b3_state = blake3_256(b'JOATT|BLAKE3|' + CHAIN_ID.encode() + previous_state + payload)
    root = double_sha256(b'JOATT|ROOT|' + previous_state + b3_state + payload)
    pbkdf = pbkdf2_sha512(root, b'JOATT|PBKDF2|' + CHAIN_ID.encode())
    scrypt_state = scrypt256(pbkdf, salt=b'JOATT|SCRYPT|' + CHAIN_ID.encode())
    mixed = blake3_256(b'JOATT|MIX|' + b3_state + root + pbkdf + scrypt_state)
    checksum = blake3_256(b'JOATT|CHECKSUM|' + mixed + root + scrypt_state)[:4]
    identifier64 = blake3_256(b'JOATT|ID64|' + checksum + mixed + previous_state)[:8]
    adler = zlib.adler32(mixed) & 4294967295
    state256 = blake3_256(b'JOATT|STATE256|' + b3_state + root + pbkdf + scrypt_state + mixed + checksum + identifier64 + adler.to_bytes(4, 'big'))
    return {'blake3': b3_state.hex(), 'root': root.hex(), 'pbkdf2': pbkdf.hex(), 'scrypt': scrypt_state.hex(), 'mix': mixed.hex(), 'checksum': checksum.hex(), 'identifier64': identifier64.hex(), 'adler32': f'{adler:08x}', 'state256': state256.hex()}

def base58_encode(data: bytes) -> str:
    number = int.from_bytes(data, 'big')
    encoded = ''
    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    zeroes = len(data) - len(data.lstrip(b'\x00'))
    return '1' * zeroes + encoded

def base58_decode(value: str) -> bytes:
    number = 0
    for char in value:
        if char not in BASE58_ALPHABET:
            raise ValueError('invalid Base58 character')
        number = number * 58 + BASE58_ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, 'big') if number else b''
    zeroes = len(value) - len(value.lstrip('1'))
    return b'\x00' * zeroes + raw

def address_checksum(payload: bytes) -> bytes:
    return blake3_256(b'CYTHAN|ADDRESS|' + payload)[:4]

def address_from_pubkey(pubkey: bytes) -> str:
    digest = hashlib.sha256(pubkey).digest()
    ripemd = hashlib.new('ripemd160')
    ripemd.update(digest)
    key_hash = ripemd.digest()
    payload = CYTHAN_ADDRESS_VERSION + key_hash
    return base58_encode(payload + address_checksum(payload))

def validate_address(address: str) -> bool:
    try:
        raw = base58_decode(address)
        if len(raw) != 25:
            return False
        payload = raw[:-4]
        checksum = raw[-4:]
        if payload[:1] != CYTHAN_ADDRESS_VERSION:
            return False
        return checksum == address_checksum(payload)
    except Exception:
        return False

def transaction_id(transaction: dict) -> str:
    body = dict(transaction)
    body.pop('txid', None)
    return double_sha256(canonical(body)).hex()

def make_transaction(sender: str, recipient: str, amount: int) -> dict:
    if amount <= 0:
        raise ValueError('amount must be positive')
    if not validate_address(recipient):
        raise ValueError('invalid recipient address')
    tx = {'sender': sender, 'recipient': recipient, 'amount': amount, 'timestamp': time.time()}
    tx['txid'] = transaction_id(tx)
    return tx

@dataclass
class Block:
    height: int
    timestamp: int
    previous_hash: str
    transactions: list
    target: str
    cythan_commitment: str
    joatt_state: str
    joatt_identifier: str
    nonce: int = 0
    hash: str = ''

    def header(self) -> dict:
        return {'height': self.height, 'timestamp': self.timestamp, 'previous_hash': self.previous_hash, 'transactions': self.transactions, 'target': self.target, 'cythan_commitment': self.cythan_commitment, 'joatt_state': self.joatt_state, 'joatt_identifier': self.joatt_identifier, 'nonce': self.nonce}

    def hash_bytes(self) -> bytes:
        header = canonical(self.header())
        return scrypt256(header, salt=header)

    def calculate_hash(self) -> str:
        return self.hash_bytes().hex()

    def mine(self) -> bool:
        target = int(self.target, 16)
        while RUNNING:
            digest = self.hash_bytes()
            if int.from_bytes(digest, 'big') <= target:
                self.hash = digest.hex()
                return True
            self.nonce += 1
        return False

class CythanMainnet:

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.chain: list[Block] = []
        self.pending: list[dict] = []
        if CHAIN_FILE.exists():
            self.load()
            if not self.validate():
                raise RuntimeError('stored chain validation failed')
            print('[CHAIN] loaded')
        else:
            self.create_genesis()

    @property
    def latest(self) -> Block:
        return self.chain[-1]

    def current_target(self) -> int:
        if len(self.chain) <= 1:
            return INITIAL_TARGET
        if len(self.chain) - 1 < DIFFICULTY_WINDOW:
            return int(self.latest.target, 16)
        window = self.chain[-DIFFICULTY_WINDOW:]
        actual = max(1, window[-1].timestamp - window[0].timestamp)
        expected = TARGET_BLOCK_TIME * (DIFFICULTY_WINDOW - 1)
        ratio = actual / expected
        ratio = max(0.25, min(4.0, ratio))
        old_target = int(self.latest.target, 16)
        new_target = int(old_target * ratio)
        return max(1, min(MAX_TARGET, new_target))

    def block_reward(self, height: int) -> int:
        halvings = height // HALVING_INTERVAL
        if halvings >= 63:
            return 0
        return INITIAL_REWARD >> halvings

    def create_genesis(self):
        payload = canonical({'network': NETWORK, 'version': VERSION, 'chain_id': CHAIN_ID, 'message': 'CYTHAN MAINNET GENESIS', 'timestamp': 0, 'supply': 0, 'consensus': 'SCRYPT'})
        cythan = cythanize(payload)
        transformed = transmogrify(payload, bytes.fromhex(cythan['commitment']))
        state = joatt(canonical(transformed))
        block = Block(height=0, timestamp=0, previous_hash='00' * 32, transactions=[{'type': 'GENESIS', 'network': NETWORK, 'chain_id': CHAIN_ID, 'message': 'CYTHAN MAINNET GENESIS'}], target=f'{INITIAL_TARGET:064x}', cythan_commitment=transformed['final']['commitment'], joatt_state=state['state256'], joatt_identifier=state['identifier64'])
        block.hash = block.calculate_hash()
        self.chain = [block]
        self.save()
        self.save_state(state)
        print('[GENESIS]', block.hash)

    def balance(self, address: str) -> int:
        total = 0
        for block in self.chain:
            for tx in block.transactions:
                if tx.get('type') == 'MINING_REWARD':
                    if tx.get('recipient') == address:
                        total += tx['amount']
                    continue
                if tx.get('sender') == address:
                    total -= tx['amount']
                if tx.get('recipient') == address:
                    total += tx['amount']
        return total

    def validate_transactions(self, transactions: list, height: int) -> bool:
        reward_count = 0
        for tx in transactions:
            if tx.get('type') == 'MINING_REWARD':
                reward_count += 1
                if reward_count > 1:
                    return False
                if tx.get('sender') != NETWORK:
                    return False
                if tx.get('amount') != self.block_reward(height):
                    return False
                continue
            sender = tx.get('sender')
            recipient = tx.get('recipient')
            amount = tx.get('amount')
            if not isinstance(sender, str):
                return False
            if not isinstance(recipient, str):
                return False
            if not validate_address(recipient):
                return False
            if not isinstance(amount, int):
                return False
            if amount <= 0:
                return False
        return True

    def build_state(self, transactions):
        previous_commitment = bytes.fromhex(self.latest.cythan_commitment)
        previous_state = bytes.fromhex(self.latest.joatt_state)
        payload = canonical({'height': len(self.chain), 'previous_hash': self.latest.hash, 'transactions': transactions, 'network': NETWORK, 'chain_id': CHAIN_ID})
        first = cythanize(payload, previous_commitment)
        transformed = transmogrify(payload, bytes.fromhex(first['commitment']))
        state_payload = canonical({'transformed': transformed, 'previous_hash': self.latest.hash, 'height': len(self.chain)})
        state = joatt(state_payload, previous_state)
        return (transformed['final'], state)

    def mine_block(self) -> bool:
        height = len(self.chain)
        reward = self.block_reward(height)
        transactions = list(self.pending)
        transactions.append({'type': 'MINING_REWARD', 'sender': NETWORK, 'recipient': MINER_ADDRESS, 'amount': reward, 'timestamp': int(time.time())})
        if not self.validate_transactions(transactions, height):
            raise RuntimeError('invalid transaction set')
        cythan, state = self.build_state(transactions)
        target = self.current_target()
        block = Block(height=height, timestamp=int(time.time()), previous_hash=self.latest.hash, transactions=transactions, target=f'{target:064x}', cythan_commitment=cythan['commitment'], joatt_state=state['state256'], joatt_identifier=state['identifier64'])
        print(f'[MINING] height={height} target={block.target}')
        started = time.monotonic()
        if not block.mine():
            return False
        elapsed = time.monotonic() - started
        self.chain.append(block)
        self.pending.clear()
        self.save()
        self.save_state(state)
        print(f'[BLOCK] {block.height} nonce={block.nonce} time={elapsed:.3f}s')
        print('[HASH]', block.hash)
        return True

    def validate(self) -> bool:
        if not self.chain:
            return False
        genesis = self.chain[0]
        if genesis.height != 0:
            return False
        if genesis.previous_hash != '00' * 32:
            return False
        if genesis.hash != genesis.calculate_hash():
            return False
        for index in range(1, len(self.chain)):
            current = self.chain[index]
            previous = self.chain[index - 1]
            if current.height != index:
                return False
            if current.previous_hash != previous.hash:
                return False
            if current.hash != current.calculate_hash():
                return False
            if int(current.hash, 16) > int(current.target, 16):
                return False
            if not self.validate_transactions(current.transactions, current.height):
                return False
        return True

    def save(self):
        data = {'network': NETWORK, 'version': VERSION, 'chain_id': CHAIN_ID, 'protocol': P2P_PROTOCOL, 'chain': [asdict(block) for block in self.chain]}
        temporary = CHAIN_FILE.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temporary.replace(CHAIN_FILE)

    def save_state(self, state):
        data = {'network': NETWORK, 'chain_id': CHAIN_ID, 'timestamp': time.time(), 'state': state}
        temporary = STATE_FILE.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temporary.replace(STATE_FILE)

    def load(self):
        data = json.loads(CHAIN_FILE.read_text(encoding='utf-8'))
        if data.get('network') != NETWORK:
            raise RuntimeError('network mismatch')
        if data.get('chain_id') != CHAIN_ID:
            raise RuntimeError('chain ID mismatch')
        self.chain = [Block(**block) for block in data['chain']]


def _prompt_pool_config():
    """Resolve configuration without blocking unattended/Termux launches."""
    global POOL_ENABLED, POOL_URL, POOL_USER, POOL_PASS, MINER_THREADS, KEEPALIVE
    if not POOL_ENABLED:
        return
    interactive = bool(getattr(__import__('sys').stdin, 'isatty', lambda: False)())
    if not POOL_URL and interactive:
        POOL_URL = input("Pool URL/host (blank = local mining): ").strip()
    if not POOL_URL:
        POOL_ENABLED = False
        print("[POOL] no endpoint configured; starting local CYTHANX mining.")
        return
    if not POOL_USER and interactive:
        POOL_USER = input("Pool user: ").strip()
    if not POOL_PASS and interactive:
        import getpass
        POOL_PASS = getpass.getpass("Pool password: ")
    if "CYTHANX_THREADS" not in os.environ and interactive:
        raw = input(f"Mining threads [{MINER_THREADS}]: ").strip()
        if raw:
            MINER_THREADS = max(1, int(raw))
    if "CYTHANX_KEEPALIVE" not in os.environ and interactive:
        raw = input(f"Pool keepalive [{'yes' if KEEPALIVE else 'no'}]: ").strip().lower()
        if raw:
            KEEPALIVE = raw in {"y", "yes", "1", "true", "on"}


def _parse_pool_endpoint(url):
    value = (url or "").strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    if "/" in value:
        value = value.split("/", 1)[0]
    host, sep, port = value.partition(":")
    return host, int(port or 3333)


class DragonflyWorker:
    """Threaded CYTHANX worker used by the mainnet mining path."""
    def __init__(self, chain, worker_id, stop_event):
        self.chain = chain
        self.worker_id = worker_id
        self.stop_event = stop_event

    def mine(self):
        while not self.stop_event.is_set():
            height = len(self.chain.chain)
            reward = self.chain.block_reward(height)
            transactions = list(self.chain.pending)
            transactions.append({
                "type": "MINING_REWARD",
                "sender": NETWORK,
                "recipient": MINER_ADDRESS,
                "amount": reward,
                "timestamp": int(time.time()),
            })
            if not self.chain.validate_transactions(transactions, height):
                raise RuntimeError("invalid transaction set")
            cythan, state = self.chain.build_state(transactions)
            target = self.chain.current_target()
            block = Block(
                height=height,
                timestamp=int(time.time()),
                previous_hash=self.chain.latest.hash,
                transactions=transactions,
                target=f"{target:064x}",
                cythan_commitment=cythan["commitment"],
                joatt_state=state["state256"],
                joatt_identifier=state["identifier64"],
            )
            # Split nonce space between Dragonfly workers.
            nonce = self.worker_id
            while nonce <= 0xFFFFFFFF and not self.stop_event.is_set():
                block.nonce = nonce
                digest = bytes.fromhex(block.calculate_hash())
                if int.from_bytes(digest, "big") <= target:
                    return block, state
                nonce += MINER_THREADS
        return None, None


@dataclass
class CYTHANXJob:
    """Canonical pool job understood by CYTHANX Dragonfly workers."""
    job_id: str
    height: int
    previous_hash: str
    transactions: list
    target: str
    cythan_commitment: str
    joatt_state: str
    joatt_identifier: str
    timestamp: int
    share_target: str | None = None
    clean_jobs: bool = True

    @classmethod
    def from_notify(cls, params):
        # job_id, height, previous_hash, transactions, target,
        # cythan_commitment, joatt_state, joatt_identifier, timestamp,
        # share_target, clean_jobs
        if len(params) < 9:
            raise ValueError("CYTHANX mining.notify requires at least 9 parameters")
        return cls(
            job_id=str(params[0]),
            height=int(params[1]),
            previous_hash=str(params[2]),
            transactions=list(params[3]),
            target=str(params[4]),
            cythan_commitment=str(params[5]),
            joatt_state=str(params[6]),
            joatt_identifier=str(params[7]),
            timestamp=int(params[8]),
            share_target=str(params[9]) if len(params) > 9 and params[9] else None,
            clean_jobs=bool(params[10]) if len(params) > 10 else True,
        )


class PoolStratumClient:
    """Universal JSON-line pool adapter with CYTHANX consensus protection.

    Modes: auto, cythanx, stratum-v1. The transport can speak ordinary
    Stratum-V1 JSON-RPC, but a job is executable only when it contains the
    CYTHANX consensus fields required by ``CYTHANXJob.from_notify``.
    Bitcoin/RandomX/etc. jobs are never translated into CYTHANX work.

    Wire contract:
      mining.subscribe -> ["CYTHANX-MINING/1", worker_name]
      mining.authorize -> [user, password]
      mining.notify -> [job_id, height, previous_hash, transactions,
                        target, cythan_commitment, joatt_state,
                        joatt_identifier, timestamp, share_target, clean_jobs]
      mining.set_target -> [share_target]
      mining.submit -> [user, job_id, nonce, hash]
      mining.ping -> []

    A CYTHANX pool must construct jobs from the same Block.header() fields
    and Scrypt PoW implemented in this miner. This client deliberately does
    not translate Bitcoin, RandomX, or other algorithms into CYTHANX work.
    """

    def __init__(self, url, user, password, keepalive=True, worker_name=None, protocol=None):
        self.url = url
        self.user = user
        self.password = password
        self.keepalive = keepalive
        self.worker_name = worker_name or f"dragonfly-{os.getpid()}"
        self.protocol = (protocol or POOL_PROTOCOL).lower()
        self.detected_protocol = None
        self.sock = None
        self.file = None
        self.request_id = 0
        self.jobs = queue.Queue()
        self.stop_event = threading.Event()
        self.share_target = None
        self._reader_thread = None
        self._send_lock = threading.Lock()

    def connect(self):
        host, port = _parse_pool_endpoint(self.url)
        self.sock = socket.create_connection((host, port), timeout=POOL_TIMEOUT)
        self.sock.settimeout(POOL_TIMEOUT)
        self.file = self.sock.makefile("rwb", buffering=0)
        self.request_id = 1
        subscribe_protocol = CYTHANX_MINING_PROTOCOL if self.protocol != "stratum-v1" else "EthereumStratum/1.0.0"
        self._send({
            "id": self.request_id,
            "method": "mining.subscribe",
            "params": [subscribe_protocol, self.worker_name],
        })
        reply = self._read()
        if isinstance(reply, dict) and reply.get("error"):
            if self.protocol == "auto" and subscribe_protocol != "EthereumStratum/1.0.0":
                self.close()
                raise RuntimeError(f"CYTHANX protocol rejected by pool; retry with CYTHANX_POOL_PROTOCOL=stratum-v1 only if the pool documents CYTHANX job extensions: {reply['error']}")
            raise RuntimeError(f"pool subscribe failed: {reply['error']}")

        self.request_id += 1
        self._send({
            "id": self.request_id,
            "method": "mining.authorize",
            "params": [self.user, self.password],
        })
        reply = self._read()
        if isinstance(reply, dict) and reply.get("error"):
            raise RuntimeError(f"pool authorization failed: {reply['error']}")

        self.detected_protocol = self.protocol if self.protocol != "auto" else "cythanx"
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="cythanx-pool-reader",
            daemon=True,
        )
        self._reader_thread.start()
        print(f"[POOL] protocol={self.detected_protocol} connected {host}:{port} user={self.user}")

    def _send(self, payload):
        if not self.file:
            raise ConnectionError("pool is not connected")
        data = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
        with self._send_lock:
            self.file.write(data)

    def _read(self):
        if not self.file:
            raise ConnectionError("pool is not connected")
        line = self.file.readline()
        if not line:
            raise ConnectionError("pool disconnected")
        return json.loads(line.decode())

    def _reader_loop(self):
        while not self.stop_event.is_set():
            try:
                message = self._read()
                method = message.get("method") if isinstance(message, dict) else None
                params = message.get("params", []) if isinstance(message, dict) else []
                if method == "mining.notify":
                    job = CYTHANXJob.from_notify(params)
                    if job.clean_jobs:
                        self._drain_jobs()
                    if self.share_target and not job.share_target:
                        job.share_target = self.share_target
                    self.jobs.put(job)
                elif method == "mining.set_target":
                    if params:
                        self.share_target = str(params[0])
                elif method == "mining.ping":
                    self._send({"id": message.get("id"), "result": True, "error": None})
                elif "error" in message and message.get("error"):
                    print(f"[POOL] message error: {message['error']}")
            except Exception as exc:
                if not self.stop_event.is_set():
                    print(f"[POOL] reader stopped: {exc}")
                return

    def _drain_jobs(self):
        while True:
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                return

    def next_job(self, timeout=1.0):
        try:
            job = self.jobs.get(timeout=timeout)
            if self.share_target and not job.share_target:
                job.share_target = self.share_target
            return job
        except queue.Empty:
            return None

    def submit(self, job: CYTHANXJob, nonce: int, digest_hex: str):
        self.request_id += 1
        self._send({
            "id": self.request_id,
            "method": "mining.submit",
            "params": [self.user, job.job_id, int(nonce), digest_hex],
        })

    def keepalive_loop(self, stop_event):
        if not self.keepalive:
            return
        while not stop_event.wait(30):
            try:
                self.request_id += 1
                self._send({
                    "id": self.request_id,
                    "method": "mining.ping",
                    "params": [],
                })
            except Exception:
                return

    def close(self):
        self.stop_event.set()
        for obj in (self.file, self.sock):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass


def block_from_cythanx_job(job: CYTHANXJob) -> Block:
    """Construct the exact mainnet Block header represented by a pool job."""
    return Block(
        height=job.height,
        timestamp=job.timestamp,
        previous_hash=job.previous_hash,
        transactions=job.transactions,
        target=job.target,
        cythan_commitment=job.cythan_commitment,
        joatt_state=job.joatt_state,
        joatt_identifier=job.joatt_identifier,
    )


def mine_cythanx_pool_job(job: CYTHANXJob, worker_id: int, worker_count: int, stop_event):
    """Mine a pool-issued CYTHANX job over a disjoint nonce range."""
    block = block_from_cythanx_job(job)
    target_hex = job.share_target or job.target
    target = int(target_hex, 16)
    nonce = worker_id
    while nonce <= 0xFFFFFFFF and not stop_event.is_set():
        block.nonce = nonce
        digest = block.hash_bytes()
        value = int.from_bytes(digest, "big")
        if value <= target:
            block.hash = digest.hex()
            return block
        nonce += worker_count
    return None

def mine_with_dragonfly_workers(chain):
    stop_event = threading.Event()
    result_q = queue.Queue()
    workers = []
    completion_lock = threading.Lock()
    completed = 0

    def run(worker_id):
        nonlocal completed
        try:
            worker = DragonflyWorker(chain, worker_id, stop_event)
            block, state = worker.mine()
            if block is not None:
                result_q.put(("found", block, state))
                stop_event.set()
        except Exception as exc:
            result_q.put(("error", exc))
            stop_event.set()
        finally:
            with completion_lock:
                completed += 1
                if completed == MINER_THREADS:
                    stop_event.set()

    for worker_id in range(MINER_THREADS):
        thread = threading.Thread(target=run, args=(worker_id,), name=f"dragonfly-{worker_id}", daemon=True)
        workers.append(thread)
        thread.start()

    for thread in workers:
        thread.join()

    while not result_q.empty():
        result = result_q.get()
        if result[0] == "error":
            raise result[1]
        if result[0] == "found":
            return result[1], result[2]
    return None, None


def automate():
    """Automated CYTHAN mainnet miner with optional pool credentials."""
    global RUNNING
    _prompt_pool_config()
    chain = CythanMainnet()
    vector = cythan_vector()
    print("=" * 72)
    print("CYTHANX DRAGONFLY AUTOMATED MAINNET MINER")
    print("=" * 72)
    print(f"Network       : {NETWORK}")
    print(f"Chain ID      : {CHAIN_ID}")
    print("Mode          : MAINNET FLOW + DRAGONFLY WORKERS")
    print(f"Workers       : {MINER_THREADS}")
    print(f"Keepalive     : {'ON' if KEEPALIVE else 'OFF'}")
    print(f"Pool          : {'ON' if POOL_ENABLED and POOL_URL else 'OFF'}")
    print(f"Pool protocol : {POOL_PROTOCOL}")
    print(f"PoW           : Scrypt")
    print(f"Block time    : {TARGET_BLOCK_TIME}s")
    print(f"JOAAT         : {vector['joaat']:08x}")
    print(f"BLAKE3        : {BLAKE3_BACKEND}")
    print("=" * 72)

    pool = None
    pool_stop = threading.Event()
    pool_thread = None
    if POOL_ENABLED and POOL_URL:
        try:
            pool = PoolStratumClient(POOL_URL, POOL_USER, POOL_PASS, KEEPALIVE, worker_name=f'dragonfly-{os.getpid()}', protocol=POOL_PROTOCOL)
            pool.connect()
            if KEEPALIVE:
                pool_thread = threading.Thread(
                    target=pool.keepalive_loop,
                    args=(pool_stop,),
                    name="pool-keepalive",
                    daemon=True,
                )
                pool_thread.start()
        except Exception as exc:
            print(f"[POOL] unavailable: {exc}")
            print("[POOL] continuing with local CYTHANX mainnet mining.")

    try:
        while RUNNING:
            if not chain.validate():
                raise RuntimeError("CHAIN VALIDATION FAILED")
            block_start = time.monotonic()

            # Prefer a CYTHANX-MINING/1 pool job when one is available.
            if pool is not None:
                job = pool.next_job(timeout=0.25)
                if job is not None:
                    pool_stop_workers = threading.Event()
                    pool_result = queue.Queue()
                    pool_completion_lock = threading.Lock()
                    pool_completed = 0

                    def pool_worker(worker_id):
                        nonlocal pool_completed
                        try:
                            found = mine_cythanx_pool_job(
                                job, worker_id, MINER_THREADS, pool_stop_workers
                            )
                            if found is not None:
                                pool_result.put(("found", found))
                                pool_stop_workers.set()
                        except Exception as exc:
                            pool_result.put(("error", exc))
                            pool_stop_workers.set()
                        finally:
                            with pool_completion_lock:
                                pool_completed += 1
                                if pool_completed == MINER_THREADS:
                                    pool_stop_workers.set()

                    pool_threads = [
                        threading.Thread(
                            target=pool_worker,
                            args=(worker_id,),
                            name=f"pool-dragonfly-{worker_id}",
                            daemon=True,
                        )
                        for worker_id in range(MINER_THREADS)
                    ]
                    for thread in pool_threads:
                        thread.start()

                    pool_stop_workers.wait()
                    for thread in pool_threads:
                        thread.join(timeout=1)

                    result = pool_result.get() if not pool_result.empty() else None
                    if result is not None and result[0] == "error":
                        print(f"[POOL] job error: {result[1]}")
                    elif result is not None and result[0] == "found":
                        found = result[1]
                        network_target = int(job.target, 16)
                        share_target = int(job.share_target or job.target, 16)
                        kind = "BLOCK CANDIDATE" if int(found.hash, 16) <= network_target else "share"
                        print(
                            f"[POOL] {kind} job={job.job_id} "
                            f"nonce={found.nonce} hash={found.hash} "
                            f"target={share_target:064x}"
                        )
                        try:
                            pool.submit(job, found.nonce, found.hash)
                        except Exception as exc:
                            print(f"[POOL] submit failed: {exc}")
                    continue

            print(f"[CHAIN] height={len(chain.chain) - 1}")
            if DRAGONFLY_WORKER:
                block, state = mine_with_dragonfly_workers(chain)
                if block is None:
                    continue
                chain.chain.append(block)
                chain.pending.clear()
                chain.save()
                chain.save_state(state)
                elapsed = time.monotonic() - block_start
                print(f"[BLOCK] {block.height} nonce={block.nonce} time={elapsed:.3f}s")
                print("[HASH]", block.hash)
                if pool:
                    print("[POOL] local block complete; pool mode uses CYTHANX-MINING/1 jobs when supplied.")
            else:
                chain.mine_block()

            if not chain.validate():
                raise RuntimeError("POST-MINING VALIDATION FAILED")
            elapsed = time.monotonic() - block_start
            remaining = max(0.0, BLOCK_INTERVAL - elapsed)
            if remaining:
                time.sleep(remaining)
    except KeyboardInterrupt:
        RUNNING = False
        print("\n[STOP] miner interrupted")
    finally:
        pool_stop.set()
        if pool:
            pool.close()
        try:
            chain.save()
        except Exception as error:
            print("[SAVE ERROR]", error)
        print(f"[STOPPED] final height={len(chain.chain) - 1}")


if __name__ == '__main__':
    import signal
    import sys
    def _request_stop(signum, frame):
        global RUNNING
        RUNNING = False
        print(f"\n[STOP] received signal {signum}; finishing shutdown...")
    for _sig in (getattr(signal, 'SIGTERM', None), getattr(signal, 'SIGINT', None)):
        if _sig is not None:
            try:
                signal.signal(_sig, _request_stop)
            except (ValueError, OSError):
                pass
    if MINER_THREADS < 1:
        print('[CONFIG ERROR] CYTHANX_THREADS must be at least 1.', file=sys.stderr)
        raise SystemExit(2)
    try:
        automate()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'[FATAL] {exc}', file=sys.stderr)
        raise SystemExit(1)
