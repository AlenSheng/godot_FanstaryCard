import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from verify_encrypted_pck import verify_pck


KEY = bytes(range(1, 33))


def encrypted(data):
    iv = bytes(range(16))
    encryptor = Cipher(algorithms.AES(KEY), modes.CFB(iv)).encryptor()
    padded = data + bytes((-len(data)) % 16)
    return hashlib.md5(data).digest() + struct.pack("<Q", len(data)) + iv + encryptor.update(padded) + encryptor.finalize()


def fixture(version=4, entry_flags=1, directory_flags=1, name="data/config.json"):
    content = b'{"test":"fixture"}'
    path = name.encode()
    directory = struct.pack("<I", len(path)) + path + struct.pack("<QQ", 0, len(content)) + hashlib.md5(content).digest() + struct.pack("<I", entry_flags)
    block = encrypted(directory)
    header_size = 96 if version == 2 else 104
    file_base = header_size + 4 + len(block)
    header = struct.pack("<6IQ", 0x43504447, version, 4, 7, 2, directory_flags, file_base)
    if version != 2:
        header += struct.pack("<Q", header_size)
    header += bytes(64)
    return header + struct.pack("<I", 1) + block + encrypted(content)


class EncryptedPackTests(unittest.TestCase):
    def verify(self, data, key=KEY.hex()):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.pck"
            path.write_bytes(data)
            return verify_pck(path, key, require_game=False)

    def test_supported_formats_decrypt_every_file(self):
        for version in (2, 3, 4):
            with self.subTest(version=version):
                report = self.verify(fixture(version=version))
                self.assertEqual(report["encrypted_files"], 1)
                self.assertTrue(report["directory_encrypted"])

    def test_wrong_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "key mismatch"):
            self.verify(fixture(), key=bytes(range(32)).hex())

    def test_unencrypted_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, "directory must be encrypted"):
            self.verify(fixture(directory_flags=0))

    def test_one_unencrypted_payload_rejected(self):
        with self.assertRaisesRegex(ValueError, "unencrypted"):
            self.verify(fixture(entry_flags=0))

    def test_corrupted_payload_rejected(self):
        data = bytearray(fixture())
        data[-16] ^= 0x80
        with self.assertRaisesRegex(ValueError, "corrupted"):
            self.verify(data)

    def test_truncated_pack_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(fixture()[:-10])

    def test_plaintext_script_or_key_rejected_even_when_encrypted(self):
        for name in ("ui/main.gd", "release-encryption.key", "tests/test.gdc"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "leaked"):
                self.verify(fixture(name=name))

    def test_default_zero_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonzero"):
            self.verify(fixture(), key="00" * 32)


if __name__ == "__main__":
    unittest.main()
