"""Regenerate the interop fixtures of the Recorder specification (see 04 §14).

Run with an interpreter where the wacryptolib of branch `warecorder_stable` is importable, with the
recorder's pinned dependencies (pycryptodome 3.20.0, pymongo 4.6.3, schema 0.7.5, uuid0 0.2.7, oscpy 0.6.0):

    PYTHONPATH=<witness-angel-cryptolib>/src python generate_fixtures.py --overwrite

wacomponents (Kivy) is NOT needed: the few recorder/components functions involved are replicated below,
with a citation, and kept byte-for-byte equivalent.

The output overwrites the sibling fixture files, so the script refuses to run without `--overwrite`.
Uids, keys, symkeys and RSA-OAEP ciphertexts are random, so a regeneration changes almost every file and
desynchronises the examples quoted in 04 (uids, sizes): regenerate both together. The self-check at the end
must pass.
"""

import base64
import hashlib
import io
import json
import random
import shutil
import sys
import tarfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import wacryptolib.sensor
from wacryptolib.cipher import encrypt_bytestring, decrypt_bytestring
from wacryptolib.cryptainer import (
    CRYPTAINER_TRUSTEE_TYPES, SHARED_SECRET_ALGO_MARKER, LOCAL_KEYFACTORY_TRUSTEE_MARKER, CryptainerStorage,
    CryptainerDecryptor, check_cryptoconf_sanity, check_cryptainer_sanity, gather_decryptable_symkeys,
    gather_trustee_dependencies, get_trustee_id, load_cryptainer_from_filesystem, dump_cryptainer_to_filesystem,
    encrypt_payload_into_cryptainer, decrypt_payload_from_cryptainer, CRYPTAINER_SCHEMA_JSON, CRYPTOCONF_SCHEMA_JSON,
)
from wacryptolib.authenticator import initialize_authenticator
from wacryptolib.keygen import generate_keypair, load_asymmetric_key_from_pem_bytestring
from wacryptolib.keystore import FilesystemKeystore, FilesystemKeystorePool, KEYSTORE_FORMAT, validate_keystore_tree, \
    generate_keypair_for_storage
from wacryptolib.sensor import TarfileRecordAggregator
from wacryptolib.shared_secret import split_secret_into_shards, recombine_secret_from_shards
from wacryptolib.signature import sign_message, verify_message_signature
from wacryptolib.trustee import TrusteeApi
from wacryptolib.utilities import dump_to_json_bytes, load_from_json_bytes, generate_uuid0, hash_message

HERE = Path(__file__).parent

PASSPHRASE_A = "guardian A passphrase"
PASSPHRASE_B = "Mot de passe du gardien B é"

# Deterministic payload standing for an ffmpeg/arecord stdout stream (content is opaque to the cryptainer layer)
PAYLOAD = b"".join(b"WA-RECORDER-FIXTURE-%05d|" % i for i in range(400)) + b"END"  # 10403 bytes, not a multiple of 16

JSONRPC_ID = 5776600559367167158  # Any int; the real client draws it at random


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump_to_json_bytes(data))  # Canonical Extended JSON, sort_keys, like the recorder and gateway


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# --- Replicas of recorder/components code (no Kivy available here) ---

def build_cryptoconf(keyguardian_threshold, selected_keystore_uids, filesystem_keystore_pool, rng):
    """Replica of WarecorderBackgroundServer._build_cryptoconf (REC/warecorder/warecorder_service.py:224-270)."""
    info_trustees = []
    all_foreign_keystore_metadata = filesystem_keystore_pool.get_all_foreign_keystore_metadata()
    for keystore_uid_str in selected_keystore_uids:
        keystore_uid = uuid.UUID(keystore_uid_str)
        keystore_owner = all_foreign_keystore_metadata[keystore_uid]["keystore_owner"]
        keystore = filesystem_keystore_pool.get_foreign_keystore(keystore_uid=keystore_uid)
        key_information_list = keystore.list_keypair_identifiers()
        key = rng.choice(key_information_list)  # Recorder uses the global random.choice()
        shard_trustee = dict(trustee_type=CRYPTAINER_TRUSTEE_TYPES.AUTHENTICATOR_TRUSTEE,
                             keystore_uid=keystore_uid, keystore_owner=keystore_owner)
        info_trustees.append(dict(key_cipher_layers=[dict(
            key_cipher_algo=key["key_algo"], keychain_uid=key["keychain_uid"], key_cipher_trustee=shard_trustee)]))
    shared_secret_encryption = [dict(key_cipher_algo=SHARED_SECRET_ALGO_MARKER,
                                     key_shared_secret_threshold=keyguardian_threshold,
                                     key_shared_secret_shards=info_trustees)]
    cryptoconf = dict(payload_cipher_layers=[dict(payload_cipher_algo="AES_CBC",
                                                  key_cipher_layers=shared_secret_encryption,
                                                  payload_signatures=[])])
    check_cryptoconf_sanity(cryptoconf)
    return cryptoconf


def import_from_authdevice(pool, authenticator_dir, include_private_keys):
    """Replica of ForeignKeystoreManagementScreen.import_keystores_from_usb (COMP/screens/foreign_keystore_management.py:93-117)."""
    keystore_tree = FilesystemKeystore(authenticator_dir).export_to_keystore_tree(include_private_keys=include_private_keys)
    for sensitive_key in ["keystore_secret", "keystore_passphrase_hint"]:
        keystore_tree.pop(sensitive_key, None)
    return pool.import_foreign_keystore_from_keystore_tree(keystore_tree)


def public_authenticator_to_keystore_tree(public_authenticator):
    """Replica of ForeignKeystoreManagementScreen._convert_public_authenticator_to_keystore_tree (:347-371)."""
    keypairs = [dict(keychain_uid=k["keychain_uid"], key_algo=k["key_algo"], public_key=k["key_value"], private_key=None)
                for k in public_authenticator["public_keys"]]
    keystore_tree = {"keystore_type": "authenticator", "keystore_format": KEYSTORE_FORMAT,
                     "keystore_owner": public_authenticator["keystore_owner"],
                     "keystore_uid": public_authenticator["keystore_uid"], "keypairs": keypairs}
    if public_authenticator["keystore_creation_datetime"]:
        keystore_tree["keystore_creation_datetime"] = public_authenticator["keystore_creation_datetime"]
    validate_keystore_tree(keystore_tree)
    return keystore_tree


def make_authenticator(target: Path, owner, hint, passphrase, keypair_count):
    initialize_authenticator(target, keystore_owner=owner, keystore_passphrase_hint=hint)
    keystore = FilesystemKeystore(target)
    for _ in range(keypair_count):
        keypair = generate_keypair(key_algo="RSA_OAEP", passphrase=passphrase)
        keystore.set_keypair(keychain_uid=generate_uuid0(), key_algo="RSA_OAEP",
                             public_key=keypair["public_key"], private_key=keypair["private_key"])
    return keystore


def public_authenticator_of(authenticator_dir):
    keystore = FilesystemKeystore(authenticator_dir)
    metadata = keystore.get_keystore_metadata()
    return {  # Same fields as the gateway serializer (AUTHSPEC 04 §7.3.1)
        "keystore_uid": metadata["keystore_uid"], "keystore_owner": metadata["keystore_owner"],
        "keystore_creation_datetime": metadata.get("keystore_creation_datetime"),
        "public_keys": [{"keychain_uid": k["keychain_uid"], "key_algo": k["key_algo"],
                         "key_value": keystore.get_public_key(keychain_uid=k["keychain_uid"], key_algo=k["key_algo"])}
                        for k in keystore.list_keypair_identifiers()],
    }


def envelope(method, params):
    return {"jsonrpc": "2.0", "method": method, "params": params, "id": JSONRPC_ID}


def stream_cryptainer(storage, filename_base, chunks, finalize=True):
    """What PeriodicSubprocessStreamRecorder does with the stdout of ffmpeg/arecord/libcamera-vid
    (CRYPTO/sensor.py:395-404, 449-463): one encryption stream per recording period."""
    stream = storage.create_cryptainer_encryption_stream(filename_base, cryptainer_metadata=None, dump_initial_cryptainer=True)
    for chunk in chunks:
        stream.encrypt_chunk(chunk)
    if finalize:
        stream.finalize()
    else:
        stream._output_data_stream.close()  # Simulate a crash: ".crypt~" + partial ".crypt.payload" remain
    return stream


def main():
    if "--overwrite" not in sys.argv[1:]:
        # ponytail: guard instead of a deterministic generator; seed the key generation if byte-stable fixtures are needed
        sys.exit("Refusing to overwrite the committed fixtures quoted in 04; rerun with --overwrite and update 04 together.")
    rng = random.Random(2026)
    for sub in ["authdevices", "keystore_pool", "cryptainers", "gateway", "all_features"]:
        shutil.rmtree(HERE / sub, ignore_errors=True)

    # 1. Two key guardians (authenticators on USB drives), as made by the Authenticator app
    dev_a = HERE / "authdevices" / "usb_A" / "authenticator.keystore"
    dev_b = HERE / "authdevices" / "usb_B" / "authenticator.keystore"
    dev_a.parent.mkdir(parents=True)
    dev_b.parent.mkdir(parents=True)
    make_authenticator(dev_a, "Alice Guardian", "usual A", PASSPHRASE_A, 2)
    make_authenticator(dev_b, "Bob Gardien é", "usual B", PASSPHRASE_B, 2)
    (HERE / "passphrases.json").write_text(json.dumps({"usb_A": PASSPHRASE_A, "usb_B": PASSPHRASE_B}, indent=2) + "\n")

    # 2. The recorder's keystore pool: A imported from USB WITH private keys, B imported from the gateway (public only)
    pool_dir = HERE / "keystore_pool"
    pool_dir.mkdir()
    pool = FilesystemKeystorePool(pool_dir)
    import_from_authdevice(pool, dev_a, include_private_keys=True)
    public_authenticator_b = public_authenticator_of(dev_b)
    pool.import_foreign_keystore_from_keystore_tree(public_authenticator_to_keystore_tree(public_authenticator_b))
    uid_a = FilesystemKeystore(dev_a).get_keystore_metadata()["keystore_uid"]
    uid_b = public_authenticator_b["keystore_uid"]
    selected = [str(uid_a), str(uid_b)]  # As stored in [keyguardian] selected_keyguardians, comma-joined

    write_json(HERE / "gateway" / "get_public_authenticator.request.json",
               envelope("get_public_authenticator", {"keystore_uid": uid_b}))
    write_json(HERE / "gateway" / "get_public_authenticator.response.json",
               {"jsonrpc": "2.0", "id": JSONRPC_ID, "result": public_authenticator_b})

    # 3. Cryptoconfs exactly as the recorder service builds them
    conf_1of2 = build_cryptoconf(1, selected, pool, rng)
    conf_2of2 = build_cryptoconf(2, selected, pool, rng)
    write_json(HERE / "cryptoconf_threshold_1_of_2.json", conf_1of2)
    write_json(HERE / "cryptoconf_threshold_2_of_2.json", conf_2of2)
    (HERE / "cryptoconf_schema.jsonschema.json").write_text(json.dumps(CRYPTOCONF_SCHEMA_JSON, indent=1) + "\n")
    (HERE / "cryptainer_schema.jsonschema.json").write_text(json.dumps(CRYPTAINER_SCHEMA_JSON, indent=1) + "\n")

    # 4. Streamed cryptainers, as sensors produce them (offloaded payload, temp file during recording)
    crypt_dir = HERE / "cryptainers"
    crypt_dir.mkdir()
    chunks = [PAYLOAD[:4096], PAYLOAD[4096:4100], PAYLOAD[4100:]]  # Arbitrary chunking: output must not depend on it
    storage_1 = CryptainerStorage(crypt_dir, keystore_pool=pool, default_cryptoconf=conf_1of2, max_workers=1,
                                  max_cryptainer_age=None)
    stream_cryptainer(storage_1, "20261026_120000_rtsp_camera_cryptainer.mp4", chunks)
    storage_2 = CryptainerStorage(crypt_dir, keystore_pool=pool, default_cryptoconf=conf_2of2, max_workers=1)
    stream_cryptainer(storage_2, "20261026_121500_rpi_microphone_cryptainer.wav", chunks)
    stream_cryptainer(storage_2, "20261026_123000_rtsp_camera_cryptainer.mp4", chunks[:1], finalize=False)
    (HERE / "expected_payload.bin").write_bytes(PAYLOAD)

    # 5. Revelation request flow (claimant side of the recorder GUI) for the 2-of-2 cryptainer
    response_keychain_uid = generate_uuid0()
    local_keyfactory = pool.get_local_keyfactory()
    generate_keypair_for_storage(key_algo="RSA_OAEP", keystore=local_keyfactory, keychain_uid=response_keychain_uid)
    response_public_key = local_keyfactory.get_public_key(keychain_uid=response_keychain_uid, key_algo="RSA_OAEP")
    requestor_uid = generate_uuid0()  # The recorder's wa_device_uid
    write_json(HERE / "wa_device_uid.json", {"wa_device_uid": requestor_uid})

    target_name = "20261026_121500_rpi_microphone_cryptainer.wav.crypt"
    cryptainer = storage_2.load_cryptainer_from_storage(target_name, include_payload_ciphertext=False)
    decryptable = gather_decryptable_symkeys([(Path(target_name), cryptainer)])
    devs = {str(uid_a): (dev_a, PASSPHRASE_A, public_authenticator_of(dev_a)), str(uid_b): (dev_b, PASSPHRASE_B, public_authenticator_b)}
    requests_out = []
    for idx, (trustee_id, (trustee_conf, symkey_requests)) in enumerate(sorted(decryptable.items())):
        params = dict(authenticator_keystore_uid=trustee_conf["keystore_uid"], revelation_requestor_uid=requestor_uid,
                      revelation_request_description="Police request 2026/123, incident of 26 October",
                      revelation_response_public_key=response_public_key,
                      revelation_response_keychain_uid=response_keychain_uid, revelation_response_key_algo="RSA_OAEP",
                      symkey_decryption_requests=symkey_requests)
        write_json(HERE / "gateway" / ("submit_revelation_request_%d.request.json" % (idx + 1)),
                   envelope("submit_revelation_request", params))
        # What the gateway stores, and what the authenticator answers on Accept (AUTHSPEC 04 §5.3)
        dev_dir, passphrase, public_authenticator = devs[str(trustee_conf["keystore_uid"])]
        response_key = load_asymmetric_key_from_pem_bytestring(response_public_key, key_algo="RSA_OAEP")
        items = []
        for req in symkey_requests:
            key_struct_bytes = TrusteeApi(FilesystemKeystore(dev_dir)).decrypt_with_private_key(
                keychain_uid=req["keychain_uid"], cipher_algo="RSA_OAEP",
                cipherdict=load_from_json_bytes(req["symkey_decryption_request_data"]), passphrases=[passphrase])
            items.append({
                "target_public_authenticator_key": [k for k in public_authenticator["public_keys"]
                                                    if k["keychain_uid"] == req["keychain_uid"]][0],
                "cryptainer_name": req["cryptainer_name"], "cryptainer_uid": req["cryptainer_uid"],
                "cryptainer_metadata": req["cryptainer_metadata"],
                "symkey_decryption_request_data": req["symkey_decryption_request_data"],
                "symkey_decryption_response_data": dump_to_json_bytes(
                    encrypt_bytestring(key_struct_bytes, cipher_algo="RSA_OAEP", key_dict=dict(key=response_key))),
                "symkey_decryption_status": "DECRYPTED",
            })
        requests_out.append({
            "target_public_authenticator": public_authenticator, "revelation_request_uid": generate_uuid0(),
            "revelation_requestor_uid": requestor_uid,
            "revelation_request_description": params["revelation_request_description"],
            "revelation_response_public_key": response_public_key,
            "revelation_response_keychain_uid": response_keychain_uid, "revelation_response_key_algo": "RSA_OAEP",
            "revelation_request_status": "ACCEPTED", "symkey_decryption_requests": items,
            "created_at": datetime(2026, 10, 26, 14, idx, 0, 123000, tzinfo=timezone.utc),
        })
    write_json(HERE / "gateway" / "list_requestor_revelation_requests.request.json",
               envelope("list_requestor_revelation_requests", {"revelation_requestor_uid": requestor_uid}))
    write_json(HERE / "gateway" / "list_requestor_revelation_requests.response.json",
               {"jsonrpc": "2.0", "id": JSONRPC_ID, "result": requests_out})

    # 6. Tar aggregation format (TarfileRecordAggregator), with cryptainer_metadata - not used by the recorder app itself
    clock = iter([datetime(2026, 10, 26, 13, 0, s, tzinfo=timezone.utc) for s in (0, 5, 10)])  # start, 2nd add, flush
    original_now = wacryptolib.sensor.get_utc_now_date
    wacryptolib.sensor.get_utc_now_date = lambda: next(clock)
    try:
        tar_storage = CryptainerStorage(crypt_dir, keystore_pool=pool, default_cryptoconf=conf_1of2, max_workers=1)
        aggregator = TarfileRecordAggregator(cryptainer_storage=tar_storage, max_duration_s=3600)
        t0 = datetime(2026, 10, 26, 12, 59, 0, tzinfo=timezone.utc)
        aggregator.add_record("gyroscope", t0, t0 + timedelta(seconds=5), ".json", b'[{"x": 1}]')
        aggregator.add_record("microphone", t0, t0 + timedelta(seconds=9), ".mp3", b"ID3fake-mp3-bytes")
        aggregator.finalize_tarfile()
        tar_storage.wait_for_idle_state()
    finally:
        wacryptolib.sensor.get_utc_now_date = original_now

    # 7. A cryptainer using every format feature (not produced by the recorder): 2 payload layers, signatures,
    #    nested symmetric key layer, local_keyfactory trustee, INLINE ciphertext, metadata
    af_pool_dir = HERE / "all_features" / "keystore_pool"
    af_pool_dir.mkdir(parents=True)
    af_pool = FilesystemKeystorePool(af_pool_dir)
    af_conf = dict(keychain_uid=generate_uuid0(), payload_cipher_layers=[
        dict(payload_cipher_algo="AES_EAX",
             key_cipher_layers=[dict(key_cipher_algo="RSA_OAEP", key_cipher_trustee=LOCAL_KEYFACTORY_TRUSTEE_MARKER)],
             payload_signatures=[dict(payload_digest_algo="SHA256", payload_signature_algo="RSA_PSS",
                                      payload_signature_trustee=LOCAL_KEYFACTORY_TRUSTEE_MARKER)]),
        dict(payload_cipher_algo="CHACHA20_POLY1305",
             key_cipher_layers=[dict(key_cipher_algo="CHACHA20_POLY1305", key_cipher_layers=[
                 dict(key_cipher_algo="RSA_OAEP", key_cipher_trustee=LOCAL_KEYFACTORY_TRUSTEE_MARKER,
                      keychain_uid=generate_uuid0())])],
             payload_signatures=[dict(payload_digest_algo="SHA3_512", payload_signature_algo="ECC_DSS",
                                      payload_signature_trustee=LOCAL_KEYFACTORY_TRUSTEE_MARKER),
                                 dict(payload_digest_algo="SHA512", payload_signature_algo="DSA_DSS",
                                      payload_signature_trustee=LOCAL_KEYFACTORY_TRUSTEE_MARKER)]),
    ])
    check_cryptoconf_sanity(af_conf)
    write_json(HERE / "all_features" / "cryptoconf.json", af_conf)
    af_cryptainer = encrypt_payload_into_cryptainer(PAYLOAD, cryptoconf=af_conf,
                                                    cryptainer_metadata={"place": "Paris", "count": 3,
                                                                         "when": datetime(2026, 10, 26, tzinfo=timezone.utc)},
                                                    keystore_pool=af_pool)
    dump_cryptainer_to_filesystem(HERE / "all_features" / "all_features_inline.crypt", af_cryptainer,
                                  offload_payload_ciphertext=False)

    # 8. Primitive test vectors (deterministic where the algorithm is)
    write_json(HERE / "primitives.json", build_primitives())

    # 9. OSC datagrams between GUI and service
    (HERE / "osc_messages.json").write_text(json.dumps(build_osc_messages(), indent=1) + "\n")

    self_check()


def build_primitives():
    key32 = bytes(range(32))
    iv16 = bytes(range(100, 116))
    nonce12 = bytes(range(200, 212))
    plaintext = b"Witness Angel test vector, 45 bytes long....."
    out = {"plaintext": plaintext, "key": key32}
    out["AES_CBC"] = dict(key_dict={"key": key32, "iv": iv16},
                          cipherdict=encrypt_bytestring(plaintext, cipher_algo="AES_CBC", key_dict={"key": key32, "iv": iv16}))
    out["AES_EAX"] = dict(key_dict={"key": key32, "nonce": iv16},
                          cipherdict=encrypt_bytestring(plaintext, cipher_algo="AES_EAX", key_dict={"key": key32, "nonce": iv16}))
    out["CHACHA20_POLY1305"] = dict(key_dict={"key": key32, "nonce": nonce12}, cipherdict=encrypt_bytestring(
        plaintext, cipher_algo="CHACHA20_POLY1305", key_dict={"key": key32, "nonce": nonce12}))
    out["hashes_of_plaintext"] = {algo: hash_message(plaintext, hash_algo=algo)
                                  for algo in ["SHA256", "SHA512", "SHA3_256", "SHA3_512"]}
    secret = dump_to_json_bytes({"key": key32, "iv": iv16})  # A serialized AES_CBC symkey
    shards = split_secret_into_shards(secret, shard_count=3, threshold_count=2)
    out["shamir"] = dict(secret=secret, shard_count=3, threshold=2, shards=[list(s) for s in shards],
                         shard_json_bytes=[dump_to_json_bytes(s) for s in shards])
    signatures = {}
    message = hash_message(plaintext, hash_algo="SHA512")  # Recorder-style: the signed message is a payload digest
    for algo in ["RSA_PSS", "ECC_DSS", "DSA_DSS"]:
        keypair = generate_keypair(key_algo=algo, serialize=False)
        sig = sign_message(message, signature_algo=algo, private_key=keypair["private_key"])
        public_pem = keypair["public_key"].export_key(format="PEM")
        signatures[algo] = dict(message=message, public_key_pem=public_pem.encode("ascii") if isinstance(public_pem, str) else public_pem,
                                signature=sig)
    out["signatures"] = signatures
    rsa = generate_keypair(key_algo="RSA_OAEP")
    rsa_pub = load_asymmetric_key_from_pem_bytestring(rsa["public_key"], key_algo="RSA_OAEP")
    long_plaintext = bytes(range(130))  # 3 chunks: 60 + 60 + 10
    out["RSA_OAEP"] = dict(private_key_pem=rsa["private_key"], plaintext=long_plaintext,
                           cipherdict_json=dump_to_json_bytes(encrypt_bytestring(long_plaintext, cipher_algo="RSA_OAEP",
                                                                                 key_dict=dict(key=rsa_pub))))
    return out


def build_osc_messages():
    from oscpy.parser import format_message
    msgs = [("app->service", "/ping", []), ("app->service", "/switch_daemonize_service", [True]),
            ("app->service", "/start_recording", [""]), ("app->service", "/stop_recording", []),
            ("app->service", "/broadcast_recording_state", []), ("app->service", "/stop_server", []),
            ("service->app", "/receive_recording_state", [True]), ("service->app", "/receive_recording_state", [False]),
            ("service->app", "/receive_recording_state", [""]), ("service->app", "/log_output", ["Pong"])]
    result = []
    for direction, address, values in msgs:
        datagram, _stats = format_message(address, values, encoding="utf8")
        result.append(dict(direction=direction, address=address, python_values=repr(values), datagram_hex=datagram.hex()))
    return result


def self_check():
    """Assertions a reimplementation can mirror in its own test suite."""
    pool = FilesystemKeystorePool(HERE / "keystore_pool")
    storage = CryptainerStorage(HERE / "cryptainers", keystore_pool=pool)
    names = [str(n) for n in storage.list_cryptainer_names(as_sorted_list=True)]
    assert names == ["20261026_120000_rtsp_camera_cryptainer.mp4.crypt",
                     "20261026_121500_rpi_microphone_cryptainer.wav.crypt",
                     "20261026_130000_to_20261026_130010_cryptainer.tar.crypt"], names
    assert [str(n) for n in storage.list_cryptainer_names(finished=False)] == ["20261026_123000_rtsp_camera_cryptainer.mp4.crypt~"]
    for name in names:
        check_cryptainer_sanity(storage.load_cryptainer_from_storage(name))

    uid_a = FilesystemKeystore(HERE / "authdevices/usb_A/authenticator.keystore").get_keystore_metadata()["keystore_uid"]
    uid_b = FilesystemKeystore(HERE / "authdevices/usb_B/authenticator.keystore").get_keystore_metadata()["keystore_uid"]

    # 1-of-2: guardian A's passphrase alone decrypts locally (A was imported WITH private keys)
    data, report = storage.decrypt_cryptainer_from_storage("20261026_120000_rtsp_camera_cryptainer.mp4.crypt",
                                                           passphrase_mapper={"authenticator@%s" % uid_a: [PASSPHRASE_A]})
    assert data == PAYLOAD, report.format_entries()
    data, report = storage.decrypt_cryptainer_from_storage("20261026_120000_rtsp_camera_cryptainer.mp4.crypt")
    assert data is None  # No passphrase, no gateway -> failure, reported not raised

    # 2-of-2: A locally + B through the gateway's ACCEPTED revelation response
    response = load_from_json_bytes((HERE / "gateway/list_requestor_revelation_requests.response.json").read_bytes())
    original = CryptainerDecryptor._get_single_gateway_revelation_request_list
    CryptainerDecryptor._get_single_gateway_revelation_request_list = lambda self, *a, **k: response["result"]
    try:
        requestor_uid = load_from_json_bytes((HERE / "wa_device_uid.json").read_bytes())["wa_device_uid"]
        for mapper in ({}, {"authenticator@%s" % uid_a: [PASSPHRASE_A]}):
            data, report = storage.decrypt_cryptainer_from_storage(
                "20261026_121500_rpi_microphone_cryptainer.wav.crypt", passphrase_mapper=mapper,
                gateway_urls=["https://gateway.invalid/jsonrpc/"], revelation_requestor_uid=requestor_uid)
            assert data == PAYLOAD, report.format_entries()
    finally:
        CryptainerDecryptor._get_single_gateway_revelation_request_list = original

    # Unfinished cryptainer: STARTED state, payload_macs null, partial payload present
    started = load_cryptainer_from_filesystem(HERE / "cryptainers/20261026_123000_rtsp_camera_cryptainer.mp4.crypt~",
                                              include_payload_ciphertext=False)
    assert started["cryptainer_state"] == "STARTED" and started["payload_cipher_layers"][0]["payload_macs"] is None
    assert (HERE / "cryptainers/20261026_123000_rtsp_camera_cryptainer.mp4.crypt.payload").stat().st_size == 4096

    # Tar aggregation cryptainer
    data, report = storage.decrypt_cryptainer_from_storage(
        "20261026_130000_to_20261026_130010_cryptainer.tar.crypt", passphrase_mapper={None: [PASSPHRASE_A]})
    tar = tarfile.open(mode="r", fileobj=io.BytesIO(data))
    assert tar.getnames() == ["20261026_125900_to_20261026_125905_gyroscope.json",
                              "20261026_125900_to_20261026_125909_microphone.mp3"], tar.getnames()

    # All-features cryptainer
    af = load_cryptainer_from_filesystem(HERE / "all_features/all_features_inline.crypt")
    check_cryptainer_sanity(af)
    data, report = decrypt_payload_from_cryptainer(af, keystore_pool=FilesystemKeystorePool(HERE / "all_features/keystore_pool"))
    assert data == PAYLOAD and not report.has_errors(), report.format_entries()

    # Primitives
    p = load_from_json_bytes((HERE / "primitives.json").read_bytes())
    for algo in ["AES_CBC", "AES_EAX", "CHACHA20_POLY1305"]:
        assert decrypt_bytestring(p[algo]["cipherdict"], cipher_algo=algo, key_dict=p[algo]["key_dict"]) == p["plaintext"]
    shards = [tuple(s) for s in p["shamir"]["shards"]]
    assert recombine_secret_from_shards(shards[1:]) == recombine_secret_from_shards([shards[0], shards[2]]) == p["shamir"]["secret"]
    for algo, v in p["signatures"].items():
        verify_message_signature(message=v["message"], signature_algo=algo, signature=v["signature"],
                                 public_key=load_asymmetric_key_from_pem_bytestring(v["public_key_pem"], key_algo=algo))
    priv = load_asymmetric_key_from_pem_bytestring(p["RSA_OAEP"]["private_key_pem"], key_algo="RSA_OAEP")
    cd = load_from_json_bytes(p["RSA_OAEP"]["cipherdict_json"])
    assert len(cd["ciphertext_chunks"]) == 3
    assert decrypt_bytestring(cd, cipher_algo="RSA_OAEP", key_dict=dict(key=priv)) == p["RSA_OAEP"]["plaintext"]
    print("Fixtures OK")


if __name__ == "__main__":
    main()
