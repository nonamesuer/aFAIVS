from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ConfigEncryptor:
    """
    Configuration file encryption compatible with the eFAIVS training system.

    ``aes_like`` intentionally preserves the existing custom wire format:
    16-byte IV + encrypted JSON bytes + 4-byte original length.
    """

    def __init__(self, password: str | None = None, salt: bytes | None = None):
        self.password = password or os.getenv(
            "CONFIG_ENCRYPTION_PASSWORD",
            "efaivs_config_password_sqweH12sDd5vs_GyorLAG",
        )
        self.salt = salt or os.getenv(
            "CONFIG_ENCRYPTION_SALT",
            "efaivs_config_salt_2026",
        ).encode()

    def _derive_key(self, iterations: int = 100000) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            self.password.encode("utf-8"),
            self.salt,
            iterations,
            dklen=32,
        )

    @staticmethod
    def _simple_encrypt(data: bytes, key: bytes) -> bytes:
        key_repeated = (key * (len(data) // len(key) + 1))[: len(data)]
        encrypted = bytes(a ^ b for a, b in zip(data, key_repeated))
        return os.urandom(16) + encrypted

    @staticmethod
    def _simple_decrypt(encrypted_data: bytes, key: bytes) -> bytes:
        if len(encrypted_data) < 16:
            raise ValueError("Encrypted data is too short")
        encrypted = encrypted_data[16:]
        key_repeated = (key * (len(encrypted) // len(key) + 1))[: len(encrypted)]
        return bytes(a ^ b for a, b in zip(encrypted, key_repeated))

    @staticmethod
    def _aes_like_encrypt(data: bytes, key: bytes) -> bytes:
        iv = os.urandom(16)
        encrypt_key = hashlib.pbkdf2_hmac(
            "sha256",
            key,
            iv,
            10000,
            dklen=32,
        )
        block_size = 32
        encrypted_blocks: list[bytes] = []
        previous_block = iv
        for index in range(0, len(data), block_size):
            block = data[index : index + block_size]
            if index > 0:
                previous_hash = hashlib.sha256(
                    previous_block + encrypt_key
                ).digest()[:block_size]
            else:
                previous_hash = hashlib.sha256(iv + encrypt_key).digest()[
                    :block_size
                ]
            encrypted_block = bytes(
                a ^ b for a, b in zip(block, previous_hash[: len(block)])
            )
            encrypted_blocks.append(encrypted_block)
            previous_block = encrypted_block
        return (
            iv
            + b"".join(encrypted_blocks)
            + len(data).to_bytes(4, "big")
        )

    @staticmethod
    def _aes_like_decrypt(encrypted_data: bytes, key: bytes) -> bytes:
        if len(encrypted_data) < 20:
            raise ValueError("Encrypted data is too short")
        iv = encrypted_data[:16]
        encrypted = encrypted_data[16:-4]
        original_length = int.from_bytes(encrypted_data[-4:], "big")
        if original_length != len(encrypted):
            raise ValueError("Encrypted data length is invalid")

        decrypt_key = hashlib.pbkdf2_hmac(
            "sha256",
            key,
            iv,
            10000,
            dklen=32,
        )
        block_size = 32
        decrypted_blocks: list[bytes] = []
        previous_block = iv
        for index in range(0, len(encrypted), block_size):
            block = encrypted[index : index + block_size]
            if index > 0:
                previous_hash = hashlib.sha256(
                    previous_block + decrypt_key
                ).digest()[:block_size]
            else:
                previous_hash = hashlib.sha256(iv + decrypt_key).digest()[
                    :block_size
                ]
            decrypted_blocks.append(
                bytes(
                    a ^ b
                    for a, b in zip(block, previous_hash[: len(block)])
                )
            )
            previous_block = block
        return b"".join(decrypted_blocks)[:original_length]

    @staticmethod
    def _build_package(
        config_data: dict[str, Any],
        method: str,
        original_filename: str | None = None,
    ) -> bytes:
        metadata = {
            "encrypted_at": datetime.now().isoformat(),
            "encryption_method": method,
            "version": "1.0",
        }
        if original_filename:
            metadata["original_filename"] = original_filename
        package = {
            "data": config_data,
            "metadata": metadata,
        }
        return json.dumps(
            package,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

    @staticmethod
    def _parse_package(decrypted_bytes: bytes) -> tuple[dict, dict]:
        package = json.loads(decrypted_bytes.decode("utf-8"))
        if not isinstance(package, dict):
            raise ValueError("Invalid encrypted configuration package")
        config_data = package.get("data")
        metadata = package.get("metadata", {})
        if not isinstance(config_data, dict):
            raise ValueError("Encrypted configuration data must be an object")
        if not isinstance(metadata, dict):
            raise ValueError("Encrypted configuration metadata must be an object")
        return config_data, metadata

    def encrypt_config_in_memory(
        self,
        config_data: dict[str, Any],
        method: str = "aes_like",
        original_filename: str | None = None,
    ) -> bytes:
        if method not in {"simple", "aes_like"}:
            raise ValueError("Unsupported encryption method")
        json_bytes = self._build_package(
            config_data,
            method,
            original_filename,
        )
        key = self._derive_key()
        if method == "simple":
            return self._simple_encrypt(json_bytes, key)
        return self._aes_like_encrypt(json_bytes, key)

    def decrypt_config_from_memory(
        self,
        encrypted_data: bytes,
        method: Optional[str] = None,
    ) -> dict[str, Any]:
        if not encrypted_data:
            raise ValueError("Encrypted configuration is empty")
        if method not in {None, "simple", "aes_like"}:
            raise ValueError("Unsupported decryption method")

        key = self._derive_key()
        methods = [method] if method else ["aes_like", "simple"]
        last_error: Exception | None = None
        for candidate in methods:
            try:
                if candidate == "simple":
                    decrypted = self._simple_decrypt(encrypted_data, key)
                else:
                    decrypted = self._aes_like_decrypt(encrypted_data, key)
                data, metadata = self._parse_package(decrypted)
                return {
                    "data": data,
                    "metadata": metadata,
                    "method": candidate,
                }
            except Exception as exc:
                last_error = exc
        raise ValueError("Failed to decrypt configuration file") from last_error

    def encrypt_file(
        self,
        source_path: str,
        target_path: str,
        method: str = "aes_like",
    ) -> dict[str, Any]:
        try:
            with open(source_path, "r", encoding="utf-8") as source_file:
                config_data = json.load(source_file)
            if not isinstance(config_data, dict):
                raise ValueError("Configuration file must contain an object")
            encrypted_data = self.encrypt_config_in_memory(
                config_data,
                method=method,
                original_filename=Path(source_path).name,
            )
            with open(target_path, "wb") as target_file:
                target_file.write(encrypted_data)
                target_file.flush()
                os.fsync(target_file.fileno())
            return {
                "success": True,
                "encrypted_size": len(encrypted_data),
                "method": method,
                "target_path": target_path,
            }
        except Exception as exc:
            logger.error("Configuration encryption failed: %s", exc)
            raise

    def decrypt_file(
        self,
        encrypted_path: str,
        output_path: str,
        method: Optional[str] = None,
    ) -> dict[str, Any]:
        try:
            with open(encrypted_path, "rb") as encrypted_file:
                encrypted_data = encrypted_file.read()
            result = self.decrypt_config_from_memory(encrypted_data, method)
            with open(output_path, "w", encoding="utf-8") as output_file:
                json.dump(
                    result["data"],
                    output_file,
                    ensure_ascii=False,
                    indent=2,
                )
                output_file.flush()
                os.fsync(output_file.fileno())
            return {
                "success": True,
                "method": result["method"],
                "metadata": result["metadata"],
                "output_path": output_path,
            }
        except Exception as exc:
            logger.error("Configuration decryption failed: %s", exc)
            raise
