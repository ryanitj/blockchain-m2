import json
import os
from typing import List
import socket

from src.block import Block, create_block, create_block_from_dict, create_genesis_block
from src.network import broadcast_block, broadcast_transaction


def get_peer_chain(peer_ip: str, port: int, timeout: int = 5) -> List[Block]:
    """
    Obtém a blockchain de um peer via socket e retorna como List[Block]
    Reutiliza sua lógica do load_chain
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((peer_ip, port))
        
        request = json.dumps({"type": "get_chain"})
        s.send(request.encode())
        
        data = s.recv(8192).decode()
        s.close()
        
        response = json.loads(data)
        if response.get("type") == "chain":
            chain_data = response.get("data", [])
            
            blockchain = []
            for block_data in chain_data:
                block = create_block_from_dict(block_data)
                blockchain.append(block)
            
            return blockchain
            
    except Exception as e:
        print(f"[RESOLVE] Erro ao obter chain do peer {peer_ip}: {e}")
        return []
    
    return []

def load_chain(fpath: str) -> List[Block]:
    if os.path.exists(fpath):
        with open(fpath) as f:
            data = json.load(f)
            blockchain = []
            for block_data in data:
                block = create_block_from_dict(block_data)
                blockchain.append(block)
            return blockchain

    return [create_genesis_block()]


def save_chain(fpath: str, chain: list[Block]):
    blockchain_serializable = []
    for b in chain:
        blockchain_serializable.append(b.as_dict())

    with open(fpath, "w") as f:
        json.dump(blockchain_serializable, f, indent=2)


def valid_chain(chain):
    for i in range(1, len(chain)):
        if chain[i]["prev_hash"] != chain[i - 1]["hash"]:
            return False
    return True


def print_chain(blockchain: List[Block]):
    for b in blockchain:
        print(f"Index: {b.index}, Hash: {b.hash[:10]}..., Tx: {len(b.transactions)}")


def mine_block(
    transactions: List,
    blockchain: List[Block],
    node_id: str,
    reward: int,
    difficulty: int,
    blockchain_fpath: str,
    peers_fpath: str,
    port: int,
):
    # 1. Minera o bloco (pode demorar)
    new_block = create_block(
        transactions,
        blockchain[-1].hash,
        miner=node_id,
        index=len(blockchain),
        reward=reward,
        difficulty=difficulty,
    )

    # 2. Após minerar, atualize prev_hash e index se a blockchain mudou
    if new_block.prev_hash != blockchain[-1].hash or new_block.index != len(blockchain):
        print("[!] Blockchain mudou durante a mineração, ajustando bloco antes de adicionar.")
        new_block.prev_hash = blockchain[-1].hash
        new_block.index = len(blockchain)
        # Recalcule o hash do bloco com os novos valores
        from src.block import hash_block
        new_block.hash = hash_block(new_block)

    blockchain.append(new_block)
    transactions.clear()

    # Resolve conflitos após mineração
    updated_chain = resolve_conflicts(peers_fpath, blockchain, port)
    if len(updated_chain) > len(blockchain):
        blockchain.clear()
        blockchain.extend(updated_chain)
        print("[RESOLVE] Blockchain atualizada após resolução de conflitos")

    save_chain(blockchain_fpath, blockchain)
    broadcast_block(new_block, peers_fpath, port)
    print(f"[✓] Block {new_block.index} mined and broadcasted.")


def make_transaction(sender, recipient, amount, transactions, peers_file, port):
    tx = {"from": sender, "to": recipient, "amount": amount}
    transactions.append(tx)
    broadcast_transaction(tx, peers_file, port)
    print("[+] Transaction added.")


def get_balance(node_id: str, blockchain: List[Block]) -> float:
    balance = 0
    for block in blockchain:
        for tx in block.transactions:
            if tx["to"] == node_id:
                balance += float(tx["amount"])
            if tx["from"] == node_id:
                balance -= float(tx["amount"])
    return balance


def list_peers(fpath: str):
    if not os.path.exists(fpath):
        print("[!] No peers file founded!")
        return []
    with open(fpath) as f:
        return [line.strip() for line in f if line.strip()]

def resolve_conflicts(peers_fpath: str, current_chain: List[Block], port: int) -> List[Block]:
    """
    Resolve conflitos usando apenas sockets - versão simples
    Reutiliza sua função load_chain para processar dados
    """
    peers = list_peers(peers_fpath)
    
    if not peers:
        return current_chain
    
    longest_chain = current_chain
    
    for peer_ip in peers:
        try:
            peer_chain = get_peer_chain(peer_ip, port)
            
            if not peer_chain:
                continue
            
            if len(peer_chain) > len(longest_chain):
                longest_chain = peer_chain
                print(f"[RESOLVE] ✓ Chain mais longa encontrada no peer {peer_ip} ({len(peer_chain)} blocos)")
                
        except Exception as e:
            print(f"[RESOLVE] Erro ao processar peer {peer_ip}: {e}")
    
    return longest_chain

def on_valid_block_callback(fpath, chain):
    save_chain(fpath, chain)