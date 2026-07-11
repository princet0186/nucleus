import os
import json
from dataclasses import dataclass
from backend.security.key_derivation import hash_sha256


@dataclass
class ZKCommitment:
    commitment: str
    nonce: str
    sanitized_hash: str
    proof: str


class ZeroKnowledgeProver:
    @staticmethod
    def commit(original_query: str, sanitized_query: str) -> ZKCommitment:
        nonce = os.urandom(32).hex()
        commitment = hash_sha256(original_query + nonce)
        sanitized_hash = hash_sha256(sanitized_query)
        proof = hash_sha256(commitment + sanitized_hash + nonce)
        return ZKCommitment(
            commitment=commitment,
            nonce=nonce,
            sanitized_hash=sanitized_hash,
            proof=proof,
        )

    @staticmethod
    def verify(commitment: ZKCommitment) -> bool:
        expected_proof = hash_sha256(
            commitment.commitment + commitment.sanitized_hash + commitment.nonce
        )
        return expected_proof == commitment.proof

    @staticmethod
    def verify_from_original(original_query: str, commitment: ZKCommitment) -> bool:
        expected_commitment = hash_sha256(original_query + commitment.nonce)
        return expected_commitment == commitment.commitment

    @staticmethod
    def to_dict(commitment: ZKCommitment) -> dict:
        return {
            "commitment": commitment.commitment,
            "nonce": commitment.nonce,
            "sanitized_hash": commitment.sanitized_hash,
            "proof": commitment.proof,
        }

    @staticmethod
    def from_dict(data: dict) -> ZKCommitment:
        return ZKCommitment(
            commitment=data["commitment"],
            nonce=data["nonce"],
            sanitized_hash=data["sanitized_hash"],
            proof=data["proof"],
        )


zkp = ZeroKnowledgeProver()
