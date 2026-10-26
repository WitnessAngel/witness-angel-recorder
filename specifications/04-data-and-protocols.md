# 04 - Data formats and protocols specification

Witness Angel Recorder (`warecorder` 1.0, `main` @ `bbf5d17`). This file gives the byte-level formats a reimplementation needs to stay compatible with:

- existing **cryptainers** (`.crypt` + `.crypt.payload`) written by recorders, and the revelation stations / Flightbox that decrypt them,
- **keystores**: the recorder's own pool, and authenticator folders imported from USB drives or from the gateway,
- the Witness Angel **gateway** (JSON-RPC over HTTPS), recorder/claimant side,
- `wacryptolib` on branch `warecorder_stable` (the cryptolib the recorder pins),
- the GUI ⇄ service **OSC** control channel, and the external capture programs (ffmpeg, arecord, libcamera, picamera).

Language-neutral in form: Python code is cited only as evidence. The recommended target is Python + `wacryptolib` (scope decision [OI-101](05-open-issues.md#oi-101), cryptolib branch [OI-100](05-open-issues.md#oi-100)); this file is then normative for bytes and serves verification and non-Python readers, while the decryptor's operation-report vocabulary comes from the library and is not specified here. Storage *roots* per OS, the OSC transport *mechanism* and the settings table are owned by [01](01-architecture-and-platform.md) ([§2.3](01-architecture-and-platform.md#23-local-control-channel-osc), [§6.2](01-architecture-and-platform.md#62-settings-reference-every-key), [§7](01-architecture-and-platform.md#7-storage-locations)); algorithms and state machines by [03](03-business-logic.md); open issues by [05](05-open-issues.md). Issues raised here link to their `OI-nn` item in 05.

**Citation prefixes** (`REC/`, `COMP/`, `CRYPTO/`, `SERVER/`, `AUTHSPEC/`) and their revisions: [README](README.md#source-baseline-and-citation-prefixes). **`AUTHSPEC/`** = [`../../witness-angel-authenticator/specifications/`](../../witness-angel-authenticator/specifications/README.md), the Authenticator specification, whose [04](../../witness-angel-authenticator/specifications/04-data-and-protocols.md) is **reused by reference**: this file only states the deltas and the recorder side. Normative tags: **MUST / SHOULD / MAY / INFO** as in the [README](README.md#normative-language).

Library versions (from `REC/poetry.lock`): pycryptodome **3.20.0**, pymongo **4.6.3** (`bson.json_util`), schema 0.7.5, uuid0 0.2.7, jsonrpc-requests 0.4.0, oscpy 0.6.0. All examples and [fixtures](fixtures/) were produced by running the real `warecorder_stable` cryptolib with these versions (Python 3.14); see §14.

---

## 0. Normative interop requirements (checklist)

**Encodings and keys (reused)**

1. MUST use the primitives of [AUTHSPEC 04 §1](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#1-primitive-encodings-used-everywhere) (uuid0 = any 16 bytes, aware UTC datetimes, ms precision) and Extended JSON per [AUTHSPEC 04 §3](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#3-serialization-extended-json-extjson). On this branch the codec is **pymongo `bson.json_util` CANONICAL** (`CRYPTO/utilities.py:29-33, 177-234`), whose output is byte-identical to the canonical form described there; writers MUST emit canonical, `sort_keys=True`, `", "`/`": "` separators, ASCII-only (§1).
2. MUST read/write PEM keys and passphrase-protected PKCS#8 exactly as [AUTHSPEC 04 §4](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#4-asymmetric-keys), including the `UTF-8(NFKC(strip(p)))` passphrase rule; MUST implement RSA-OAEP chunking as [AUTHSPEC 04 §5.2](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#52-rsa-oaep-chunked-encryption-the-format-the-authenticator-decrypts-and-produces) (SHA-512/MGF1-SHA-512, 60-byte chunks, `ciphertext_chunks`, legacy `digest_list` on read).

**Keystores (§2-§3)**

3. MUST lay out the keystore pool as `<pool>/local_keyfactory/` and `<pool>/foreign_keystores/keystore_<str(uuid)>/`, each holding `keystore_metadata.json` (foreign only) and `<keychain_uid>_<ALGO>_{public,private}_key.pem` files (§2.2).
4. MUST strip `keystore_secret` and `keystore_passphrase_hint` from imported foreign keystores, and MUST NOT send private keys anywhere (§3.2).

**Cryptoconf and cryptainers (§4-§8)**

5. MUST wrap each cryptainer's symkey in one `[SHARED_SECRET]` key layer over the selected guardians, with threshold `keyguardian_threshold` and one shard per selected guardian, each shard one `RSA_OAEP` layer with an `authenticator` trustee carrying `keystore_uid` and an explicit `keychain_uid` (§4.3). The payload cipher follows the decision of [OI-55](05-open-issues.md#oi-55) (INFO: `AES_CBC` in 1.0, which every reader MUST keep supporting). SHOULD keep `keystore_owner` in each trustee (revelation stations show it). INFO, as in [03 §5.1](03-business-logic.md#51-algorithm): a single payload layer, `payload_signatures` = `[]`, no root `keychain_uid`, shards in selection order; readers take all of these from the cryptainer itself, so they are not interop requirements.
6. MUST name the signature list **`payload_signatures`** (not `payload_ciphertext_signatures`) when writing; SHOULD accept both names when reading (§4.5). The newer cryptolib branches break both rules ([OI-63](05-open-issues.md#oi-63)); the library choice is [OI-100](05-open-issues.md#oi-100), and the cross-decryption test of §14.1 MUST pass.
7. MUST write cryptainer JSON with exactly the root fields of §5.1, `cryptainer_format = "cryptainer_1.0"`, and for streamed payloads `payload_ciphertext_struct = {"ciphertext_location": "offloaded"}` with the ciphertext in the sibling file `<name>.crypt.payload` (§5.2).
8. MUST name files `<from_ts>_<sensor_name>_cryptainer<ext>.crypt` with `from_ts` = UTC `%Y%m%d_%H%M%S` (§5.3); MUST use the `~` suffix (`.crypt~`) for the cryptainer while it is being written, and remove it after the final `.crypt` is written.
9. MUST wrap keys exactly as §6: symkey → Extended-JSON bytes → Shamir shards (16-byte chunks, PKCS#7 pad, GF(2^128) as pycryptodome) → each shard serialized as the JSON array `[idx, bytes]` → **`key_struct` `{"cryptainer_metadata": …, "key_bytes": …}`** → RSA-OAEP cipherdict JSON bytes → `{"shard_ciphertexts": [...]}` JSON bytes = `key_ciphertext`.
10. MUST reproduce AES-CBC/EAX/ChaCha20-Poly1305 parameters, the streaming equivalence and the digest/signature rules of §7.
11. MUST NOT re-serialize any byte-valued field (notably `key_ciphertext`, shard ciphertexts): the gateway and the decryptor match `symkey_decryption_request_data` **byte for byte** against them (§10.4).

**Gateway (§10)**

12. MUST call `get_public_authenticator`, `submit_revelation_request`, `list_requestor_revelation_requests` with named params in an Extended-JSON envelope ([AUTHSPEC 04 §7.1-7.2](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#71-transport)); MUST use the persistent `wa_device_uid` as `revelation_requestor_uid`; MUST decrypt `symkey_decryption_response_data` with the local response private key and use the `key_bytes` of the resulting `key_struct` (§10.5).
13. SHOULD set an HTTP timeout (this branch has none, [OI-73](05-open-issues.md#oi-73)).

**Local channel and capture (§11-§12)**

14. MUST, if interoperating with an unmodified GUI or service, use the OSC addresses and argument types of §11 (booleans travel as OSC int32).
15. Capture programs are not an interop surface: a reimplementation MAY use other tools, but the **produced media formats and file extensions** of §12 SHOULD be kept so that decrypted files stay playable and named alike.

---

## 1. Serialization deltas versus the Authenticator spec

| Topic | Recorder (`warecorder_stable`) | Evidence |
|---|---|---|
| JSON codec | pymongo `json_util.dumps/loads` with `JSONMode.CANONICAL`, `UuidRepresentation.STANDARD`, `tz_aware=True`; `sort_keys=True` default. Same bytes as AUTHSPEC 04 §3.1. | `CRYPTO/utilities.py:29-33, 177-198` |
| Invalid JSON | `JSONDecodeError` → `SchemaValidationError("Invalid JSON string: …")` | `CRYPTO/utilities.py:194-198` |
| Bytes ⇄ text | `dump_to_json_bytes` = UTF-8 of the (ASCII) JSON text; `load_from_json_bytes` decodes UTF-8 | `CRYPTO/utilities.py:201-215` |
| Files | Written with `open(path, "wb")` in place: no temp file, no fsync, default umask | `CRYPTO/utilities.py:218-225` |
| uuid0 | `uuid0.generate()` (6-byte time + 10 random bytes, AUTHSPEC §1) | `CRYPTO/utilities.py:237-248` |

Integers inside data (`key_shared_secret_threshold`, metadata ints, `signature_timestamp_utc`) are written `{"$numberInt": "…"}` (or `$numberLong` ≥ 2^31). Readers MUST accept both, and relaxed forms ([AUTHSPEC 04 §3.3](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#33-relaxed-mode)). The validation micro-schemas accept UUID `$binary` subtype `"03"` or `"04"` (`CRYPTO/utilities.py:415-421`).

INFO: the extended-JSON micro-schema for base64 (`CRYPTO/utilities.py:411-413`) requires at least 4 characters, so an **empty** `$binary` value fails jsonschema-mode validation while it passes python-mode validation ([OI-61](05-open-issues.md#oi-61)).

---

## 2. On-disk layout of the recorder's data

Roots are per OS ([01 §7](01-architecture-and-platform.md#7-storage-locations)); on desktop `INTERNAL_APP_ROOT = ~/.witnessangel/` (shared with every Witness Angel desktop app, [OI-04](05-open-issues.md#oi-04)), `INTERNAL_CACHE_DIR = INTERNAL_APP_ROOT/cache/`, `EXTERNAL_APP_ROOT = INTERNAL_APP_ROOT/external/` (`COMP/default_settings.py:119-124`).

### 2.1 Tree

```
INTERNAL_APP_ROOT/
├── warecorder_config.ini                 # settings (01 §6)                      REC/warecorder/warecorder_common_runtime.py:26
├── .wa_device_uid.json                   # {"wa_device_uid": <uuid0 $binary 04>}  COMP/application/_common_runtime_support.py:181-190
├── recording_in_progress                 # empty marker file, autostart (03 §4.5)  COMP/default_settings.py:134
├── .witnessangel0.sock / .witnessangel1.sock   # OSC unix datagram sockets (GUI / service), §11
├── logs/log.txt[.1 … .100]               # rotating 20 MiB × 100, shared by GUI+service  REC/…common_runtime.py:41-47
├── authenticator.keystore/               # (legacy "authenticator" renamed at import) NOT used by the recorder  COMP/default_settings.py:139-145
├── keystore_pool/                        # §2.2
│   ├── local_keyfactory/
│   └── foreign_keystores/keystore_<uuid>/…
├── cryptainers/                          # default cryptainer dir when [storage] cryptainer_dir is empty, §5
│   ├── <ts>_<sensor>_cryptainer<ext>.crypt
│   ├── <ts>_<sensor>_cryptainer<ext>.crypt.payload
│   └── <ts>_<sensor>_cryptainer<ext>.crypt~        # while recording / after a crash
├── cache/video_preview_image.jpg         # last preview (§12.7)                REC/…common_runtime.py:28
└── external/exports/                     # decrypted payloads and revelation reports (§13)
```

### 2.2 Keystore pool

`FilesystemKeystorePool(root_dir = INTERNAL_APP_ROOT/keystore_pool)` (`REC/warecorder/warecorder_common_runtime.py:33-37`, `COMP/application/_common_runtime_support.py:51-54`, `CRYPTO/keystore.py:686-771`).

| Path | Content | Rules |
|---|---|---|
| `local_keyfactory/` | Recorder-local keypairs: here only the **revelation response keypairs** (§10.3). Created on first access (`mkdir`). **No metadata file.** | `CRYPTO/keystore.py:702-707` |
| `local_keyfactory/<uid>_RSA_OAEP_public_key.pem` | SPKI PEM, no trailing newline | AUTHSPEC 04 §4.2 |
| `local_keyfactory/<uid>_RSA_OAEP_private_key.pem` | **Unprotected** PKCS#1 `-----BEGIN RSA PRIVATE KEY-----` (no passphrase) ([OI-77](05-open-issues.md#oi-77)) | `CRYPTO/_crypto_backend/pycryptodome.py:201-205` |
| `local_keyfactory/free_keys/<ALGO>/<10-11 digits>_{public,private}_key.pem` | Pregenerated pool; **not used** by the recorder (`free_keys_generator_worker=None`) | `CRYPTO/keystore.py:526-589`, `REC/warecorder/warecorder_service.py:411` |
| `foreign_keystores/keystore_<str(keystore_uid)>/` | One imported key guardian. Directory name = prefix `keystore_` + lowercase hyphenated uid. Listing = glob `keystore_*`, then `UUID(name minus prefix)`, sorted (a malformed name raises) | `CRYPTO/keystore.py:693-733` |
| `…/keystore_metadata.json` | Schema of [AUTHSPEC 04 §2.2](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#22-keystore_metadatajson-schema), **without** `keystore_secret` / `keystore_passphrase_hint` (§3.2); legacy `.keystore.json` also read | `CRYPTO/keystore.py:89-123` |
| `…/<keychain_uid>_<ALGO>_public_key.pem` / `_private_key.pem` | Copied bytes from the authenticator; private keys present only for USB import "with private keys"; they stay passphrase-protected PKCS#8 | `CRYPTO/keystore.py:602-641` |

Filename regex, listing order and skip rules are those of [AUTHSPEC 04 §2.1](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#21-folder-content). Example foreign metadata (real fixture, one line):

```json
{"keystore_creation_datetime": {"$date": {"$numberLong": "1793032011473"}}, "keystore_format": "keystore_1.0", "keystore_owner": "Alice Guardian", "keystore_type": "authenticator", "keystore_uid": {"$binary": {"base64": "EE66XHQys3pz3Zv2Hq3IfA==", "subType": "04"}}}
```

---

## 3. Key guardian import formats

### 3.1 Selection setting

`[keyguardian] selected_keyguardians` = `str(UUID)` values joined with `","` (no spaces) by the GUI (`REC/warecorder/warecorder_gui.py:204-207`). Readers split on `,`, strip, drop empties (`REC/warecorder/warecorder_common_runtime.py:147-150`), then drop any uid not present in `foreign_keystores/` (`:49-67`). `keyguardian_threshold` is an INI integer (`:144-145`). Full settings table: [01 §6.2](01-architecture-and-platform.md#62-settings-reference-every-key).

### 3.2 From an authdevice (USB)

Authdevice discovery and folder names (`authenticator.keystore`, legacy `.authenticator` at the partition root) are as in [AUTHSPEC 03 §2](../../witness-angel-authenticator/specifications/03-business-logic.md#2-authenticator-locations) (`CRYPTO/authdevice.py:13-47`). An authdevice counts if `keystore_metadata.json` or `.keystore.json` exists (`CRYPTO/authenticator.py:71-88`).

Import (`COMP/screens/foreign_keystore_management.py:76-137`):

1. `export_to_keystore_tree(include_private_keys)` → the keystore tree of [AUTHSPEC 04 §2.3](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#23-keystore-tree-in-memory-exportimport-format) (metadata + `keypairs[{keychain_uid, key_algo, public_key, private_key|null}]`); validated by `KEYSTORE_TREE_SCHEMA`, `key_algo` ∈ `AES_CBC, AES_EAX, CHACHA20_POLY1305, RSA_OAEP` (`CRYPTO/keystore.py:66-78, 486-515`).
2. Delete `keystore_secret` and `keystore_passphrase_hint` (MUST).
3. `import_foreign_keystore_from_keystore_tree`: create `keystore_<uid>/` if missing; if no metadata yet, write `keystore_metadata.json` = tree minus `keypairs` (validated); else require same `keystore_uid` (`ValidationError` → counted as "corrupted"). Then write each public key, then the private key if non-null; `KeyAlreadyExists` is **ignored** (existing files are kept, never compared) (`CRYPTO/keystore.py:591-641, 765-771`). Returns "updated" iff metadata existed.
4. `SchemaValidationError` while exporting → skipped as corrupted.

### 3.3 From the gateway

`get_public_authenticator(keystore_uid=UUID(text.strip().lower()))` (§10.2), converted (`COMP/screens/foreign_keystore_management.py:346-371`) to:

```
{"keystore_type": "authenticator", "keystore_format": "keystore_1.0",
 "keystore_owner": <owner>, "keystore_uid": <uid>,
 ["keystore_creation_datetime": <dt>]      # only if non-null in the response
 "keypairs": [{"keychain_uid", "key_algo", "public_key": <key_value bytes>, "private_key": null}, …]}
```

then imported as in §3.2 step 3. Result: a foreign keystore with public keys only.

---

## 4. Cryptoconf

A **cryptoconf** is the encryption recipe; a cryptainer is a deep copy of it enriched with ciphertexts (§5).

### 4.1 Schema (decoded types)

Validated by `CRYPTOCONF_SCHEMA_PYTHON` / `CRYPTOCONF_SCHEMA_JSON` (`CRYPTO/cryptainer.py:2378-2517`); the jsonschema version is in [fixtures/cryptoconf_schema.jsonschema.json](fixtures/cryptoconf_schema.jsonschema.json). Dicts are closed (extra keys refused).

```
cryptoconf := {
  ["keychain_uid": UUID],                      # default keychain for layers without one; random uuid0 if absent
  "payload_cipher_layers": [ payload_cipher_layer, … ]   # non-empty; applied in order (first = innermost)
}
payload_cipher_layer := {
  "payload_cipher_algo": "AES_CBC" | "AES_EAX" | "CHACHA20_POLY1305" | "RSA_OAEP",   # RSA_OAEP is accepted by the schema but unusable (OI-60)
  "key_cipher_layers": [ key_cipher_layer, … ],     # non-empty; applied in order
  "payload_signatures": [ payload_signature, … ]     # may be empty
}
key_cipher_layer := asymmetric | symmetric | shared_secret
asymmetric := {"key_cipher_algo": "DSA_DSS"|"ECC_DSS"|"RSA_OAEP"|"RSA_PSS",  # schema allows all 4; only RSA_OAEP can encrypt
               "key_cipher_trustee": trustee, ["keychain_uid": UUID]}
symmetric  := {"key_cipher_algo": "AES_CBC"|"AES_EAX"|"CHACHA20_POLY1305", "key_cipher_layers": [key_cipher_layer, …]}  # non-empty, recursive
shared_secret := {"key_cipher_algo": "[SHARED_SECRET]",
                  "key_shared_secret_threshold": int,                     # 1 ≤ t ≤ len(shards) (python mode only, OI-58)
                  "key_shared_secret_shards": [ {"key_cipher_layers": [key_cipher_layer, …]}, … ]}
payload_signature := {"payload_digest_algo": "SHA256"|"SHA512"|"SHA3_256"|"SHA3_512",
                      "payload_signature_algo": "DSA_DSS"|"ECC_DSS"|"RSA_PSS",
                      "payload_signature_trustee": trustee, ["keychain_uid": UUID]}
```

### 4.2 Trustee dicts

| `trustee_type` | Fields | Trustee id (`get_trustee_id`, used as passphrase-mapper key) | Key source | Evidence |
|---|---|---|---|---|
| `local_keyfactory` | exactly `{"trustee_type": "local_keyfactory"}` | `"local_keyfactory"` | `<pool>/local_keyfactory`; **keys auto-generated on demand, unprotected** | `CRYPTO/cryptainer.py:99-128, 312-329`, `CRYPTO/trustee.py:32-49` |
| `authenticator` | `keystore_uid` (UUID), optional `keystore_owner` (str, informative, ignored by the id) | `"authenticator@" + str(keystore_uid)` | foreign keystore `keystore_<uid>`, read-only (never generates) | same, `CRYPTO/trustee.py:232-244` |
| `jsonrpc_api` | `jsonrpc_url` (str) | `"jsonrpc_api@" + url` | remote TrusteeApi over JSON-RPC (`fetch_public_key`, `get_message_signature`, `decrypt_with_private_key`, `request_decryption_authorization`, named params). **Not used by the recorder.** | `CRYPTO/cryptainer.py:327-328`, `CRYPTO/trustee.py:51-229` |

### 4.3 The cryptoconf built by the recorder

Built by `WarecorderBackgroundServer._build_cryptoconf` at every toolchain build, i.e. every recording start (`REC/warecorder/warecorder_service.py:215-270`; algorithm and its triggering: [03 §5](03-business-logic.md#5-building-the-cryptoconf)). Inputs: `keyguardian_threshold` (t) and the filtered selected uids (n), in **setting order**. For each guardian: owner from its foreign metadata, **one keypair chosen with `random.choice`** among *all* its keypairs (any algo, private key present or not; [OI-54](05-open-issues.md#oi-54)).

Real output, t = 1, n = 2 ([fixtures/cryptoconf_threshold_1_of_2.json](fixtures/cryptoconf_threshold_1_of_2.json), re-indented; the file itself is one line):

```json
{"payload_cipher_layers": [
  {"key_cipher_layers": [
     {"key_cipher_algo": "[SHARED_SECRET]",
      "key_shared_secret_shards": [
        {"key_cipher_layers": [{"key_cipher_algo": "RSA_OAEP",
            "key_cipher_trustee": {"keystore_owner": "Alice Guardian",
                                   "keystore_uid": {"$binary": {"base64": "EE66XHQys3pz3Zv2Hq3IfA==", "subType": "04"}},
                                   "trustee_type": "authenticator"},
            "keychain_uid": {"$binary": {"base64": "EE66XINOmYnh7lXPygrkdA==", "subType": "04"}}}]},
        {"key_cipher_layers": [{"key_cipher_algo": "RSA_OAEP",
            "key_cipher_trustee": {"keystore_owner": "Bob Gardien é",
                                   "keystore_uid": {"$binary": {"base64": "EE66XJcrWRUDuvTyS3rmhw==", "subType": "04"}},
                                   "trustee_type": "authenticator"},
            "keychain_uid": {"$binary": {"base64": "EE66XK0El/m0qF/O8muTog==", "subType": "04"}}}]}],
      "key_shared_secret_threshold": {"$numberInt": "1"}}],
   "payload_cipher_algo": "AES_CBC",
   "payload_signatures": []}]}
```

Properties of this cryptoconf, with the tags of [03 §5.1](03-business-logic.md#51-algorithm): the `[SHARED_SECRET]` layer over the selected guardians with threshold `keyguardian_threshold` and one `RSA_OAEP` authenticator layer per shard is **MUST** (checklist item 5); `keystore_owner` present is **SHOULD** (revelation stations show it); no root `keychain_uid` (so each cryptainer gets a fresh random one, unused), shard order = selection order and a single payload layer without signatures are **INFO**: the decryptor reads layers, shard order and keychain uids from each cryptainer (`CRYPTO/cryptainer.py:1025-1375`), so changing them does not break readers. The 1.0 payload cipher is AES-CBC, hence **no integrity protection of the payload**; whether new recordings switch to `AES_EAX`/`CHACHA20_POLY1305` is the decision of [OI-55](05-open-issues.md#oi-55) (readers MUST keep AES-CBC). `check_cryptoconf_sanity` runs on it (`:267`).

### 4.4 Settings → cryptoconf mapping

| Setting | Cryptoconf field |
|---|---|
| `[keyguardian] keyguardian_threshold` | `key_shared_secret_threshold` |
| `[keyguardian] selected_keyguardians` (filtered) | one shard per uid, `key_cipher_trustee.keystore_uid` |
| foreign `keystore_metadata.json` → `keystore_owner` | `key_cipher_trustee.keystore_owner` |
| random keypair of that keystore | `keychain_uid`, `key_cipher_algo` (= its `key_algo`) |
| (hard-coded) | `payload_cipher_algo = "AES_CBC"`, `payload_signatures = []` |

### 4.5 Naming history: `payload_signatures` vs `payload_ciphertext_signatures`

- `warecorder_stable` reads and writes only **`payload_signatures`** (`CRYPTO/cryptainer.py:172, 517, 707, 1123, 2496`).
- Recorder commit `7de2edc` (2025-08-08) switched the recorder to `payload_ciphertext_signatures`, the naming of the newer cryptolib branches (`cryptainer_module_refactoring` @ `ac1a951`, and `poc/pure-python-crypto-utils` @ `2717a79`, the branch `waflet_components` runs on). With the pinned branch this made `check_cryptoconf_sanity` fail, so no recording could start. Commit **`efbf4ce`** (2025-09-21, message "Rename legacy payload_cipher_layers cryptoconf setting", a misleading title) reverted to `payload_signatures`.
- **The newer branches do not read the legacy name when decrypting.** They convert `payload_signatures` only during *schema validation*, through a `Use(_handle_payload_signatures_retrocompatibility)` step (`cryptainer/_validation.py:131-146` there). The decrypt path never validates the cryptainer, and their decryptor indexes `payload_cipher_layer["payload_ciphertext_signatures"]` directly (`cryptainer/_decryptor.py:399` on the poc branch, `:398` on `cryptainer_module_refactoring`). So decrypting a 1.0 cryptainer with them raises `KeyError: 'payload_ciphertext_signatures'` (reproduced on [fixtures/cryptainers/](fixtures/cryptainers/) with `CryptainerStorage.decrypt_cryptainer_from_storage`; the same call on `warecorder_stable` returns the 10 403-byte payload).
- Conversely, their encryptor reads and writes only `payload_ciphertext_signatures` (`cryptainer/_encryptor.py:266` on the poc branch), and `warecorder_stable` indexes `payload_signatures` directly (`CRYPTO/cryptainer.py:1123`): cryptainers written by the newer branches are **not** decryptable by deployed recorders and revelation tools (`KeyError`).
- Consequence: existing recorder cryptainers all use `payload_signatures`, and the two library generations are mutually incompatible on this field. Which library the reimplementation uses is the decision [OI-100](05-open-issues.md#oi-100); whichever is chosen, the acceptance test of §14.1 applies. See checklist item 6 and [OI-63](05-open-issues.md#oi-63).

---

## 5. Cryptainer file format

### 5.1 Root fields

Validated by `CRYPTAINER_SCHEMA_*` (`CRYPTO/cryptainer.py:2413-2441`; jsonschema in [fixtures/cryptainer_schema.jsonschema.json](fixtures/cryptainer_schema.jsonschema.json)). A cryptainer = the cryptoconf plus:

| Field | Type | Value |
|---|---|---|
| `cryptainer_format` | str | exactly `"cryptainer_1.0"` (`:70`); readers MUST refuse others (`:1066-1068`) |
| `cryptainer_uid` | UUID | fresh uuid0 per cryptainer (`:480`) |
| `keychain_uid` | UUID | conf's `keychain_uid` or fresh uuid0 (`:482-484`) |
| `cryptainer_state` | `"STARTED"` \| `"FINISHED"` | STARTED in the temp file, FINISHED once signatures/MACs are set (`:109-111, 522-529, 722`) |
| `cryptainer_metadata` | dict \| null | **Unencrypted, unauthenticated**; `null` for every recorder sensor (`CRYPTO/sensor.py:400`); the tar aggregator writes `{"members": …}` (§9). Also copied inside every `key_struct` (§6.2). |
| `payload_ciphertext_struct` | object | `{"ciphertext_location": "inline", "ciphertext_value": bytes}` or exactly `{"ciphertext_location": "offloaded"}` (compared by dict equality, `:1871`) |
| `payload_cipher_layers[i].key_ciphertext` | bytes | wrapped symkey of that layer (§6) |
| `payload_cipher_layers[i].payload_macs` | object | `{}` for AES_CBC, `{"tag": 16 bytes}` for EAX/ChaCha20; **`null` while STARTED** |
| `…key_cipher_layers[j].key_ciphertext` | bytes | only in *symmetric* key layers: the wrapped sub-symkey (`:631`) |
| `…payload_signatures[k].payload_digest_value` | bytes | digest of that layer's output ciphertext (`:710`) |
| `…payload_signatures[k].payload_signature_struct` | object | `{"signature_value": bytes, "signature_timestamp_utc": int}` (§7.6) |

### 5.2 Files of one cryptainer

| File | Content |
|---|---|
| `<base>.crypt` | Canonical Extended-JSON (one line, sorted keys, no trailing newline), state FINISHED |
| `<base>.crypt.payload` | Raw outer-layer ciphertext bytes, nothing else (no header). Present iff offloaded. Name = cryptainer filename with any trailing `~` removed + `.payload` (`CRYPTO/cryptainer.py:88, 1835-1839`). |
| `<base>.crypt~` | Same JSON with state STARTED and `payload_macs: null`, written at stream creation; deleted after `.crypt` is written (`:1610-1612, 1630-1645`) |

Write sequence of a streamed cryptainer (`CRYPTO/cryptainer.py:1600-1657`): open `<base>.crypt.payload` (truncate) → build keys, write `<base>.crypt~` → append ciphertext chunks to `.payload` → finalize: flush/close `.payload`, set MACs/signatures/state, write `<base>.crypt`, unlink `<base>.crypt~`. No step is atomic (no rename); a crash leaves `.crypt~` + partial `.payload`.

INFO: a STARTED cryptainer fails both schemas (`payload_macs` null) and is never listed as decryptable ([OI-46](05-open-issues.md#oi-46)). For AES-CBC the partial `.payload` is decryptable block by block with the key from `.crypt~`, but no tool does it.

Reading (`:1857-1880`): if `payload_ciphertext_struct` is the offloaded marker, the reader loads the sibling `.payload` and substitutes an inline struct in memory. Listing: glob `*.crypt` (finished) and `*.crypt~` (unfinished), no subfolders, sorted by name (`:1919-1939`). Size = `.crypt` + `.payload` (`:1892-1899`). Deletion removes both (`:1883-1889`).

Non-streamed writes (`dump_cryptainer_to_filesystem`, `offload_payload_ciphertext=True` default in `CryptainerStorage`) also produce `.crypt` + `.payload`; with `offload=False` the ciphertext is inline (`:1843-1854`). The recorder always streams (all its payload ciphers are streamable, `:2262-2263, 1669-1673`).

### 5.3 File naming

| Producer | Name | Evidence |
|---|---|---|
| Stream sensors (all recorder sensors) | `{from_ts}_{sensor_name}_cryptainer{ext}.crypt` | `CRYPTO/sensor.py:381-389` |
| Tar aggregator (unused by the recorder) | `{from_ts}_to_{to_ts}_cryptainer.tar.crypt` | `CRYPTO/sensor.py:99-106` |
| Records inside a tar | `{from_ts}_to_{to_ts}_{sensor_name}{ext}` | `CRYPTO/sensor.py:129-135` |

`from_ts`/`to_ts` = `strftime("%Y%m%d_%H%M%S")` of an **aware UTC** datetime (`CRYPTAINER_DATETIME_FORMAT`, `CRYPTO/cryptainer.py:72-75`); `from_ts` = start of the recording period. Sensor names and extensions: §12.1. Example: `20230722_123919_rtsp_camera_cryptainer.mp4.crypt` (real 2023 name, `REC/list_requestor_revelation_requests_fixture.json`).

Readers derive the creation time from the first 15 characters parsed as UTC, else from file mtime (`CRYPTO/cryptainer.py:1941-1952`); it drives the age-based purge ([03 §8.1](03-business-logic.md#81-purge-algorithm)) and "latest" display. Names sort chronologically. Two periods of the same sensor starting in the same second produce the same name and the later overwrites the earlier ([OI-20](05-open-issues.md#oi-20)).

### 5.4 Annotated real cryptainer

`fixtures/cryptainers/20261026_120000_rtsp_camera_cryptainer.mp4.crypt` (14 029 bytes, base64 cut, re-indented):

```json
{"cryptainer_format": "cryptainer_1.0",
 "cryptainer_metadata": null,
 "cryptainer_state": "FINISHED",
 "cryptainer_uid": {"$binary": {"base64": "EE66XK2oFWBTIGSMu3n/7Q==", "subType": "04"}},
 "keychain_uid":   {"$binary": {"base64": "EE66XK2orojbigy4CyRD0Q==", "subType": "04"}},
 "payload_cipher_layers": [{
    "key_cipher_layers": [ …exactly the cryptoconf of §4.3… ],
    "key_ciphertext": {"$binary": {"base64": "eyJzaGFyZF9jaXBoZXJ0ZXh0cyI6IFt7…", "subType": "00"}},   // 9 539 bytes, §6.3
    "payload_cipher_algo": "AES_CBC",
    "payload_macs": {},
    "payload_signatures": []}],
 "payload_ciphertext_struct": {"ciphertext_location": "offloaded"}}
```

and `…mp4.crypt.payload` = 10 416 bytes = AES-256-CBC of the 10 403-byte payload.

---

## 6. Key wrapping (exact byte pipeline)

### 6.1 Per payload layer (encryption, `CRYPTO/cryptainer.py:494-520, 532-690`)

1. `symkey = generate_symkey(payload_cipher_algo)` (§7.1); `key_bytes = ExtJSON(symkey)`.
2. For each key layer **in order**: `cipherdict = wrap(key_bytes, layer)`; `key_bytes = ExtJSON(cipherdict)`.
3. `key_ciphertext` = final `key_bytes`.

`wrap` per layer kind:

| Layer | Output cipherdict |
|---|---|
| asymmetric (`RSA_OAEP`) | `key_struct = {"cryptainer_metadata": <cryptainer metadata>, "key_bytes": <input bytes>}`; `RSA_OAEP(public key of (trustee, keychain_uid or default), ExtJSON(key_struct))` → `{"ciphertext_chunks": [...]}` (`:677-690`) |
| symmetric (algo A) | sub-symkey `S = generate_symkey(A)`; `layer["key_ciphertext"] = wrap_all(ExtJSON(S), layer["key_cipher_layers"])` (recursive, stored **in the layer**); output = `encrypt(A, S, input)` e.g. `{"ciphertext": …}` or `{"ciphertext": …, "tag": …}` (`:616-634`) |
| `[SHARED_SECRET]` | `shards = split(input, n, t)` (§7.5); for each shard i and shard conf i: `wrap_all(ExtJSON([idx, shard_bytes]), conf.key_cipher_layers)`; output `{"shard_ciphertexts": [bytes, …]}` in shard order (`:583-614`) |

Note: the plaintext an authenticator decrypts is always a **`key_struct`**, never a bare symkey or shard. [AUTHSPEC 04 §5.1](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#51-symmetric-ciphers-context-only) and its `expected_plaintexts.json` fixture describe a bare symkey; that is inexact for recorder cryptainers (harmless, opaque to the authenticator; [OI-65](05-open-issues.md#oi-65)).

### 6.2 Recorder case, real sizes (t = 1, n = 2)

```
symkey  {"iv": {"$binary": {"base64": "<16 B>", "subType": "00"}}, "key": {"$binary": {"base64": "<32 B>", "subType": "00"}}}
        = 173 bytes ExtJSON
  └─ Shamir: PKCS#7 pad → 176 B → 11 chunks of 16 B → shard i = (i, 176 B)
       └─ shard JSON  [{"$numberInt": "1"}, {"$binary": {"base64": "<176 B>", "subType": "00"}}]   = 303 B
            └─ key_struct {"cryptainer_metadata": null, "key_bytes": {"$binary": {"base64": "<303 B>", "subType": "00"}}} = 492 B
                 └─ RSA-OAEP: ceil(492/60) = 9 chunks × 256 B → {"ciphertext_chunks": [9 × $binary]}  = 3 533 B   ← symkey_decryption_request_data
  └─ {"shard_ciphertexts": [<3 533 B>, <3 533 B>]}  = 9 539 B  = key_ciphertext
```

With t = 1 every shard equals the padded secret (degree-0 polynomial): each guardian alone can reveal the key, as intended, but the shard is the symkey JSON in clear inside the `key_struct` ([OI-56](05-open-issues.md#oi-56)). The real 2023 gateway data (`REC/list_requestor_revelation_requests_fixture.json`) shows the same 9 × 256-byte, 3 533-byte request data.

### 6.3 Decryption (`CRYPTO/cryptainer.py:1025-1375`)

- Payload layers are undone in **reverse** order; signatures of a layer are verified (errors only reported) before its key is unwrapped; key layers are undone in reverse order.
- Shared secret: shards are tried in order; stop as soon as `t` shards are decrypted; fewer → failure. `zip` truncates silently if lists differ in length ([OI-62](05-open-issues.md#oi-62)).
- Asymmetric layer: first look the **exact `key_ciphertext` bytes of this layer** (= `ExtJSON({"ciphertext_chunks": …})`) up in the *predecrypted symkey mapper* built from the gateway (§10.5); on a hit, use `key_struct["key_bytes"]`. Otherwise decrypt with the trustee's private key, trying no passphrase then `passphrase_mapper[trustee_id] + passphrase_mapper[None]` ([AUTHSPEC 04 §4.3](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#43-private-key-pem-passphrase-protected)).
- `key_struct["cryptainer_metadata"]` is decoded but unused.
- Payload: `decrypt(algo, symkey, {"ciphertext": c, **payload_macs})`; MAC failure → `DecryptionIntegrityError`. Result `None` on any failure, with an operation report (format: [03 §10.7](03-business-logic.md#107-decryption-process)).

---

## 7. Cipher algorithms and parameters

### 7.1 Symmetric key dicts (`CRYPTO/keygen.py:21-53`)

| `cipher_algo` | Key dict (ExtJSON keys sorted) | Random source |
|---|---|---|
| `AES_CBC` | `{"iv": 16 B, "key": 32 B}` | `Crypto.Random.get_random_bytes` |
| `AES_EAX` | `{"key": 32 B, "nonce": 16 B}` | idem |
| `CHACHA20_POLY1305` | `{"key": 32 B, "nonce": 12 B}` | idem |

Key length < 32 bytes is refused (`CRYPTO/keygen.py:186-189`).

### 7.2 Payload ciphers (`CRYPTO/cipher.py:79-189`, `CRYPTO/_crypto_backend/pycryptodome.py:42-110`)

| Algo | Encryption | Cipherdict | Notes |
|---|---|---|---|
| `AES_CBC` | AES-256-CBC, PKCS#7 padding (always 1-16 bytes added) | `{"ciphertext"}` | output length `16·(⌊n/16⌋+1)`; unauthenticated |
| `AES_EAX` | AES-256 EAX, 16-byte nonce, no header/AAD, 16-byte tag | `{"ciphertext", "tag"}` | ciphertext length = plaintext length |
| `CHACHA20_POLY1305` | RFC 7539 ChaCha20-Poly1305, 12-byte nonce, no AAD, 16-byte tag | `{"ciphertext", "tag"}` | idem |
| `RSA_OAEP` | [AUTHSPEC 04 §5.2](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#52-rsa-oaep-chunked-encryption-the-format-the-authenticator-decrypts-and-produces) | `{"ciphertext_chunks"}` | only valid for key layers |

In a cryptainer, the payload `"ciphertext"` goes to `payload_ciphertext_struct`/`.payload` and the remaining entries (`tag`) to `payload_macs` (`CRYPTO/cryptainer.py:449-461`). Decryption with `verify_integrity_tags=False` skips tag checks.

Deterministic vectors (key `00 01 … 1f`, iv/nonce16 `64 65 … 73`, nonce12 `c8 c9 … d3`, plaintext `"Witness Angel test vector, 45 bytes long....."`, 45 bytes; [fixtures/primitives.json](fixtures/primitives.json)):

| Algo | Ciphertext (hex) | Tag |
|---|---|---|
| AES_CBC | `97947895581451a0783a220a2f5052c8abbec3691dc02c26b687385c3c3f587f26e958df68e2ce5c3883d9462948b5b8` | - |
| AES_EAX | `fe1b1c7ae47fd82b1c5e6bc09a1c690afe8ad63473ece4355960ce9a15dc68e87faf48ca035cf9b448e8c1baf7` | `3884d455a0e0911de7652797faeee7b2` |
| CHACHA20_POLY1305 | `420fe7e10239335d47d82d83e9f4e712f76dcc5197dce472eaa0186820ca6a73726a73e26dc661e8efdba05e08` | `9be27ebdcb76e9ddd13415ba6d5c48e4` |

### 7.3 Hashes (`CRYPTO/utilities.py:103-114`)

`SHA256`, `SHA512`, `SHA3_256`, `SHA3_512` (FIPS 180-4 / FIPS 202). Digest length asserted 32-64 bytes. Vectors on the plaintext above: SHA256 `cee89f3e…d0562f`, SHA512 `8b9b53a6…f6b904`, SHA3_256 `5f832f54…2a3e66`, SHA3_512 `274eedf4…900b1e` (full values in `primitives.json`).

### 7.4 Streaming encryptor (`CRYPTO/cipher.py:234-410`)

`PayloadEncryptionPipeline` chains one node per payload layer. MUST be byte-equivalent to one-shot encryption whatever the chunking (fixtures use chunks 4096/4/6303):

- AES_CBC node buffers the remainder modulo 16 and emits only whole blocks; `finalize` PKCS#7-pads the remainder (`:258-298`).
- EAX / ChaCha20 nodes are stream ciphers; their tag is taken after finalize (`:328-352`).
- `encrypt_chunk`: the chunk goes through every node in order; only the last node's output is written. `finalize`: for each node in order, encrypt the previous node's final output then finalize. Output is flushed.
- Each node hashes **its own output ciphertext** with the layer's `payload_digest_algo`s (`:258-265, 304-310`), i.e. the digest of layer i covers the input of layer i+1, as in the non-streamed path (`CRYPTO/cryptainer.py:430-465`).
- Sensors push subprocess stdout in chunks of 2 MiB (0.2 MiB for audio) (`CRYPTO/sensor.py:411`, `COMP/sensors/camera/raspberrypi_camera_microphone.py:234`); chunking is invisible in the output.

### 7.5 Shamir shared secret (`CRYPTO/shared_secret.py:13-115`, pycryptodome `Crypto/Protocol/SecretSharing.py`)

- `secret` → PKCS#7 pad to a multiple of 16 (always adds 1-16 bytes) → split into 16-byte chunks.
- Each chunk is shared independently with `Shamir.split(k=t, n, chunk, ssss=False)`: field GF(2^128) with modulus `x^128 + x^7 + x^2 + x + 1`; a 16-byte value maps to an element by **big-endian** integer, bit i = coefficient of x^i (not GCM's reflected order). Polynomial `p(x) = c_{k-1}x^{k-1} + … + c_1 x + chunk`, `c_j` = 16 random bytes. Share for user i (i = 1..n) = `p(i)` encoded as 16 bytes big-endian.
- Full shard i = `(i, concat of the chunk shares of user i)`, so its length = padded secret length.
- Recombination: take exactly the decrypted shards (the decryptor passes t of them), check distinct indices and equal lengths, Lagrange-interpolate each 16-byte column at x = 0, concatenate, PKCS#7-unpad.
- Wire form of one shard: `ExtJSON([idx, shard_bytes])` = `[{"$numberInt": "1"}, {"$binary": {…}}]`.
- Vector: `primitives.json → shamir` (secret 173 B, n = 3, t = 2, three 176-byte shards; any 2 recombine).

### 7.6 Signatures (`CRYPTO/signature.py:29-104`, `CRYPTO/_crypto_backend/pycryptodome.py:240-267`)

Not used by the recorder cryptoconf; needed to read general cryptainers.

- Signed message = `payload_digest_value` (the digest of the layer output).
- `timestamp = int(datetime.utcnow().timestamp())` → **off by the host's UTC offset** on non-UTC hosts (fixture made on a CET host: −3600 s; [OI-59](05-open-issues.md#oi-59)). Verifiers MUST use the stored integer as-is.
- Hash object `H = SHA512(message ‖ ASCII(decimal timestamp))`.
- `RSA_PSS`: RSASSA-PSS over H, MGF1-SHA512, salt length 64 bytes; signature = modulus length (256 B for RSA-2048).
- `DSA_DSS` and `ECC_DSS`: `DSS.new(key, "fips-186-3")`, binary encoding `r ‖ s` (fixed width; leftmost bits of SHA-512 truncated to the group order size); randomized k. DSA 2048 (q 224 bits → 56-byte signature); ECC curve **p521** by default (132-byte signature).
- Struct: `{"signature_timestamp_utc": int, "signature_value": bytes}`.
- Keys: `RSA_PSS` like RSA_OAEP; DSA private PEM PKCS#8 (protected: PBKDF2-HMAC-SHA1 + 3DES-CBC), ECC PKCS#8 (protected: PBKDF2-HMAC-SHA1 + AES-128-CBC); unprotected `-----BEGIN PRIVATE KEY-----` (`CRYPTO/_crypto_backend/pycryptodome.py:201-220`).
- Verification failures are reported, never fatal (`CRYPTO/cryptainer.py:1508-1590`). Vectors: `primitives.json → signatures` (verify-only, schemes are randomized).

### 7.7 Crypto backend

The recorder uses pycryptodome C extensions; the pure-Python fallback is only activated on iOS or with `FORCE_WACRYPTOLIB_FALLBACK_BACKEND` (`CRYPTO/_crypto_backend/__init__.py:12-18`); the fallback supports AES-CBC only, so a recorder on it could still encrypt (CBC) but not read EAX/ChaCha20 cryptainers. INFO.

---

## 8. Optional key-guardian passphrase mapper

`passphrase_mapper: {trustee_id | None: [passphrase, …]}` (§4.2 ids; `None` = try for all) (`CRYPTO/cryptainer.py:338-351, 1445-1449`). The GUI fills it per trustee after testing a passphrase against the **first** keypair of that foreign keystore (`COMP/screens/cryptainer_decryption_process.py:241-300`). In-memory only, never persisted.

---

## 9. Tar aggregation format (`TarfileRecordAggregator`)

INFO for the recorder: its toolchain has `tarfile_aggregators=[]` (`REC/warecorder/warecorder_service.py:406-412`); every recorder cryptainer holds one raw media stream. Other WA apps may produce tar cryptainers (example: [fixtures/cryptainers/20261026_130000_to_20261026_130010_cryptainer.tar.crypt](fixtures/cryptainers/)).

- Payload = an uncompressed POSIX tar written by Python `tarfile` mode `"w"` (default format **PAX**), padded to 10 240-byte blocks (`CRYPTO/sensor.py:58-196`).
- Members: name `{from_ts}_to_{to_ts}_{sensor_name}{ext}` (§5.3), size = payload length, `mtime` = `to_datetime.timestamp()` (a float: recent Pythons add a PAX `mtime=<float>` record; older ones store the integer only), mode 0644, no owner names. Same name twice: both stored, last wins on extraction.
- Cryptainer metadata (unencrypted): `{"members": {<member name>: {"size": int, "mtime": aware datetime}}}`, e.g. `{"members": {"20261026_125900_to_20261026_125905_gyroscope.json": {"mtime": {"$date": {"$numberLong": "1793019545000"}}, "size": {"$numberInt": "10"}}, …}}`.
- `JsonDataAggregator` members are `.json` files containing the ExtJSON array of collected dicts (`:199-244`).
- A tar is flushed when a new record arrives after `max_duration_s` from the first record, or explicitly.

---

## 10. Gateway JSON-RPC, recorder (claimant) side

### 10.1 Transport

As [AUTHSPEC 04 §7.1-§7.2](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#71-transport) (POST, `Content-Type: application/json`, `Accept: application/json-rpc`, ExtJSON envelope with `$numberLong` id, named params only, `status_slugs` error mapping), with these deltas:

| Aspect | Recorder | Evidence |
|---|---|---|
| URL | `[network] wagateway_url`, default `https://api.witnessangel.com/gateway/jsonrpc/`, read when the proxy is built; the decryption screen caches it at construction ([OI-72](05-open-issues.md#oi-72)) | `REC/warecorder/config_defaults.ini:52`, `COMP/application/_common_runtime_support.py:192-195`, `COMP/screens/cryptainer_decryption_process.py:54-57` |
| Timeout | **none** (requests default; a stalled server blocks forever) ([OI-73](05-open-issues.md#oi-73)) | `CRYPTO/jsonrpc_client.py:56-59` |
| Errors caught | listing and decryption catch `(JSONRPCError, OSError)` | `COMP/screens/claimant_revelation_request_management.py:55-64`, `CRYPTO/cryptainer.py:957-968` |

Example request body (byte-exact, `fixtures/gateway/list_requestor_revelation_requests.request.json`):

```json
{"id": {"$numberLong": "5776600559367167158"}, "jsonrpc": "2.0", "method": "list_requestor_revelation_requests", "params": {"revelation_requestor_uid": {"$binary": {"base64": "EE66XMOYtKwHrs3GhssFaw==", "subType": "04"}}}}
```

### 10.2 `get_public_authenticator`

Caller: "Import keys from web gateway" (`COMP/screens/foreign_keystore_management.py:373-415`). Params `{"keystore_uid": UUID}` (no secret). Result and errors: [AUTHSPEC 04 §7.3.1](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#731-get_public_authenticator). The GUI maps `ExistenceError` (incl. `KeystoreDoesNotExist`) to "Authenticator does not exist" and a bad UUID text to "Badly formed hexadecimal UUID string". Wire pair: `fixtures/gateway/get_public_authenticator.{request,response}.json`.

### 10.3 `submit_revelation_request`

Caller: revelation request form (`COMP/screens/claimant_revelation_request_creation_form.py:92-171`). Per submission:

1. Load the selected cryptainers **without payload**; `gather_decryptable_symkeys` (`CRYPTO/cryptainer.py:190-288`) walks, for each payload layer, the **last** key layer only: shared secret → recurse per shard with its shard ciphertext; symmetric → recurse into its `key_ciphertext`; asymmetric → emit one request item, grouped by trustee id:
   `{"cryptainer_name": str(name), "cryptainer_uid", "cryptainer_metadata", "symkey_decryption_request_data": <the asymmetric layer's input ciphertext bytes>, "keychain_uid": layer keychain_uid or cryptainer keychain_uid, "key_algo"}`.
2. Generate **one** response keypair: `keychain_uid = uuid0`, `RSA_OAEP` 2048, stored unprotected in `local_keyfactory` (§2.2).
3. For each `authenticator` trustee the user ticked, one call:

| Param | Value |
|---|---|
| `authenticator_keystore_uid` | trustee `keystore_uid` |
| `revelation_requestor_uid` | `wa_device_uid` (§2.1) |
| `revelation_request_description` | text stripped, ≥ 10 characters (client rule) |
| `revelation_response_public_key` | SPKI PEM bytes |
| `revelation_response_keychain_uid` | the new uid |
| `revelation_response_key_algo` | `"RSA_OAEP"` |
| `symkey_decryption_requests` | the items of step 1 for that trustee |

Server rules (`SERVER/apps/wagateway/core.py:114-178, 348-367`): schema as above; `symkey_decryption_request_data` values unique within the call (`ValidationError`); unknown authenticator → `KeystoreDoesNotExist`; item `(keychain_uid, key_algo)` not among published keys → `KeyDoesNotExist`; `cryptainer_name` ≤ 100 chars (DB column, `SERVER/apps/wagateway/models.py:124`). Result `null`. Non-idempotent: a retry creates a duplicate request ([OI-74](05-open-issues.md#oi-74)). Wire example: `fixtures/gateway/submit_revelation_request_{1,2}.request.json`:

```json
{"id": {"$numberLong": "5776600559367167158"}, "jsonrpc": "2.0", "method": "submit_revelation_request", "params": {
  "authenticator_keystore_uid": {"$binary": {"base64": "EE66XHQys3pz3Zv2Hq3IfA==", "subType": "04"}},
  "revelation_request_description": "Police request 2026/123, incident of 26 October",
  "revelation_requestor_uid": {"$binary": {"base64": "EE66XMOYtKwHrs3GhssFaw==", "subType": "04"}},
  "revelation_response_key_algo": "RSA_OAEP",
  "revelation_response_keychain_uid": {"$binary": {"base64": "EE66XK9Or3mjR/XjZ6zU7A==", "subType": "04"}},
  "revelation_response_public_key": {"$binary": {"base64": "LS0tLS1CRUdJTiBQVUJMSUMg…", "subType": "00"}},
  "symkey_decryption_requests": [{"cryptainer_metadata": null,
     "cryptainer_name": "20261026_121500_rpi_microphone_cryptainer.wav.crypt",
     "cryptainer_uid": {"$binary": {"base64": "EE66XK5DJ/eIdORs3Nc9ow==", "subType": "04"}},
     "key_algo": "RSA_OAEP",
     "keychain_uid": {"$binary": {"base64": "EE66XINOmYnh7lXPygrkdA==", "subType": "04"}},
     "symkey_decryption_request_data": {"$binary": {"base64": "eyJjaXBoZXJ0ZXh0X2NodW5r…", "subType": "00"}}}]}}
```

(re-indented; the real body is one line).

### 10.4 `list_requestor_revelation_requests`

Params `{"revelation_requestor_uid": UUID}`; **no authentication**: anyone knowing the uid can list ([OI-78](05-open-issues.md#oi-78)) (`SERVER/apps/wagateway/core.py:181-193`). Result: list of revelation request objects in every status, structure of [AUTHSPEC 04 §7.3.3](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#733-list_authenticator_revelation_requests). Callers: the request list screen (groups items by `cryptainer_uid`, newest uid first, [03 §10.9](03-business-logic.md#109-listing-revelation-requests)) and decryption (§10.5).

Real 2023 output: `REC/list_requestor_revelation_requests_fixture.json` (untracked, 50 898 bytes, identical to the copy in components): a bare `result` list of 4 `PENDING` requests from one requestor, targets owned by `¤aaa`/`¤bbb` with `keystore_creation_datetime: null` and 7 public keys, one item each, `cryptainer_metadata: null`, `symkey_decryption_response_data` = empty `$binary`, request data 3 533 bytes. A complete accepted example: `fixtures/gateway/list_requestor_revelation_requests.response.json`.

### 10.5 Revelation response decryption

On decryption, if `gateway_urls` and `revelation_requestor_uid` are given (the GUI always passes `[wagateway_url]` and `wa_device_uid`) (`CRYPTO/cryptainer.py:984-1062`):

1. Call `list_requestor_revelation_requests` on each URL; network errors → report entry, continue.
2. Keep requests with `revelation_request_status == "ACCEPTED"`, then their items with `cryptainer_uid == cryptainer["cryptainer_uid"]` **and** `symkey_decryption_status == "DECRYPTED"`.
3. For each: `cipherdict = ExtJSON.load(symkey_decryption_response_data)`; private key = `local_keyfactory` key `(revelation_response_keychain_uid, revelation_response_key_algo)` (no passphrase); RSA-OAEP decrypt → `key_struct` bytes. Missing key / load / decrypt errors → report entries.
4. Mapper `{symkey_decryption_request_data (bytes): key_struct bytes}`; first entry wins.
5. During unwrapping (§6.3) a hit uses `ExtJSON.load(key_struct)["key_bytes"]`.

```
response_data ──ExtJSON──► {"ciphertext_chunks":[r1..rm]} ──RSA-OAEP-SHA512 (local response private key)──►
key_struct = {"cryptainer_metadata": …, "key_bytes": <shard JSON | symkey JSON | inner cipherdict>}
```

---

## 11. OSC messages (GUI ⇄ service)

Transport (01 owns it, [01 §2.3](01-architecture-and-platform.md#23-local-control-channel-osc)): OSC 1.0 messages, one per datagram, oscpy 0.6 with `encoding="utf8"`; unix datagram sockets `INTERNAL_APP_ROOT/.witnessangel0.sock` (GUI listens) and `.witnessangel1.sock` (service listens); on Windows UDP `127.0.0.1:6420` (GUI) / `6421` (service) (`COMP/service_control/_osc_transport.py:32-75`). No authentication ([OI-06](05-open-issues.md#oi-06)). Unknown addresses are logged by a default handler.

Encoding (oscpy `WRITERS` order): `float` → `f`, **`int` and `bool` → `i`** (bool is an int subclass, so `True` = int32 1, `False` = 0; the `T`/`F` tags are never produced), `str` → `s` (UTF-8, NUL-terminated, 4-byte padded). Receivers MUST accept `i` 0/1 and SHOULD also accept `T`/`F`.

| Address | Direction | Args | Meaning | Evidence |
|---|---|---|---|---|
| `/ping` | GUI → service | none | service logs and answers `/log_output "Pong"`; not used by the GUI loop | `COMP/service_control/_base_service_controller.py:30-31`, `COMP/application/recorder_service.py:131-135` |
| `/switch_daemonize_service` | GUI → service | `i` 0/1 | Android: keep service alive when GUI closes; desktop: no-op. Never sent by the Recorder GUI ([OI-10](05-open-issues.md#oi-10)) | `…_base_service_controller.py:33-35`, `recorder_service.py:137-151` |
| `/start_recording` | GUI → service | `s` (always `""`, ignored "env") | start recording ([03 §4.3](03-business-logic.md#43-start-recording)) | `…_base_service_controller.py:37-38`, `recorder_service.py:190-207` |
| `/stop_recording` | GUI → service | none | stop recording | `…:40-41`, `recorder_service.py:247-260` |
| `/broadcast_recording_state` | GUI → service | none | ask for `/receive_recording_state` (sent every 2 s × WAIT_TIME_MULTIPLIER) | `…:43-44`, `recorder_service.py:213-225`, `COMP/application/recorder_gui.py:119-131` |
| `/stop_server` | GUI → service | none | stop recording if any (≤ 30 s), stop OSC, exit | `COMP/service_control/_subprocess_service_controller.py:33-34`, `recorder_service.py:262-275` |
| `/attempt_cryptainer_decryption` | GUI → service | `s` path | defined in the controller, never called, no handler | `…_base_service_controller.py:46-48` |
| `/receive_recording_state` | service → GUI | `i` 0/1, or `s` `""` = state change in progress | ternary recording state | `recorder_service.py:213-225`, `recorder_gui.py:133-145` |
| `/log_output` | service → GUI | `s` | text for the GUI console (display disabled) | `recorder_gui.py:156-162` |

Byte-exact datagrams ([fixtures/osc_messages.json](fixtures/osc_messages.json)):

```
/ping                              2f70696e67000000 2c000000
/start_recording ""                2f73746172745f7265636f7264696e6700000000 2c730000 00000000
/receive_recording_state True      2f726563656976655f7265636f7264696e675f737461746500000000 2c690000 00000001
/receive_recording_state ""        2f726563656976655f7265636f7264696e675f737461746500000000 2c730000 00000000
/log_output "Pong"                 2f6c6f675f6f757470757400 2c730000 506f6e6700000000
```

### 11.1 Proposed: service status message (fix, not 1.0)

> **PROPOSAL, not part of the 1.0 behaviour.** Nothing below exists in 1.0. It defines the channel that the *fix* dispositions of [OI-15](05-open-issues.md#oi-15) (refusal reason), [OI-16](05-open-issues.md#oi-16) (degraded start), [OI-17](05-open-issues.md#oi-17) and [OI-18](05-open-issues.md#oi-18) (sensor restart and failure) and [OI-44](05-open-issues.md#oi-44) (storage full) need, so that implementers do not each invent one. Tags inside this section apply only to an implementation of these fixes. The project owner may replace the shape; the fixes then still need an equivalent channel.

1.0 has only the ternary `/receive_recording_state`. The proposal adds one request and one answer, and keeps every 1.0 message unchanged:

| Address | Direction | Args | Meaning |
|---|---|---|---|
| `/broadcast_service_status` | GUI → service | none | ask for `/receive_service_status`; a new GUI sends it with every `/broadcast_recording_state` poll |
| `/receive_service_status` | service → GUI | `s`: one Extended-JSON object (canonical, §1) | the service status below; sent in reply to the request, and at once after each start/stop completion, refused start, sensor state change or storage-full transition, to every GUI that has sent the request at least once since the service started |

Payload (field names are part of the proposal; `datetime` values are aware UTC as in §1):

```text
{
  "status_format": "service_status_1.0",
  "recording": true | false | null,            # same ternary as /receive_recording_state; null = start/stop in progress
  "refusal": null | {                          # the last start that failed, cleared by the next successful start
      "at": <datetime>,
      "checkup": [{"ok": bool, "message": str}, ...],   # the service's own checkup lines (03 §4.3.1), in order
      "error": str | null                      # toolchain build or start exception, e.g. "KeyDoesNotExist"; null if the checkup refused
  },
  "sensors": [                                 # one entry per enabled sensor of the current toolchain; [] when idle
      {"name": "rtsp_camera",                  # sensor slug (§12.1)
       "state": "running" | "restarting" | "failed",
       "last_data_utc": <datetime> | null,     # last payload chunk written, null if none yet
       "error": str | null}                    # last failure reason when state != "running"
  ],
  "storage": {"free_bytes": int, "full": bool} # cryptainer_dir partition; full = below the margin of OI-44
}
```

Rules:

- The service **SHOULD** keep `/receive_recording_state` and keep `recording` consistent with it; `recording` is `true` while at least one sensor is `running` or `restarting` ([OI-16](05-open-issues.md#oi-16)).
- The serialized string **SHOULD** stay well below the 65 535-byte datagram limit of [01 §2.3](01-architecture-and-platform.md#23-local-control-channel-osc) (truncate `message`/`error` strings to 200 characters).
- GUI display: [02 §3.2](02-ux-and-screens.md#32-the-record-button-state-machine) ("Proposed status display").
- Mixing old and new peers: [01 §2.3](01-architecture-and-platform.md#23-local-control-channel-osc) recommends new socket names, so that old and new processes never talk. If they do talk anyway: a new GUI facing a 1.0 service never receives a status and **MUST** fall back to the ternary state alone (as in 1.0); a 1.0 service receiving `/broadcast_service_status` only logs an unknown address ([OI-08](05-open-issues.md#oi-08)); a 1.0 GUI never sends the request, so a new service never pushes a status to it.

---

## 12. Capture programs, command lines, media formats

The recorder writes **subprocess stdout** (or picamera's encoder output) straight into a cryptainer stream, one cryptainer per sensor per period of `recording_duration_mn` (selection rules: [03 §6](03-business-logic.md#6-sensors)). Stop = `terminate()` (SIGTERM), wait 10 s, then `kill()`, wait 5 s (`CRYPTO/sensor.py:503-535`). Stdin is a pipe (unused); stderr lines are logged. When a setting's "parameters" string is non-empty it is split with POSIX `shlex.split` and **replaces** the whole default parameter block shown below ([OI-29](05-open-issues.md#oi-29)) (`REC/warecorder/warecorder_common_runtime.py:109-142`).

### 12.1 Sensor names, extensions, formats

| Sensor (`sensor_name`) | Program | Default `ext` | Media in the payload | Evidence |
|---|---|---|---|---|
| `rtsp_camera` | ffmpeg | `.mp4` (`.` + `ffmpeg_rtsp_output_format` or `mp4`) | fragmented MP4, video copied from the camera, **no audio** | `COMP/sensors/camera/rtsp_stream.py:42-139` |
| `rpi_libcamera` | libcamera-vid | `.h264` (no mic muxing) / `.mpegts` (muxed) | raw H.264 Annex-B / MPEG-TS H.264+AAC | `COMP/sensors/camera/raspberrypi_camera_microphone.py:112-223` |
| `rpi_microphone` | arecord / ffmpeg | `.wav` (`arecord_output_format` or `wav`) / `.mp3` when compressed (`ffmpeg_alsa_output_format` or `mp3`) | WAV PCM S16_LE mono / MP3 | `…:226-293` |
| `picamera` | picamera (legacy stack) | `.` + `format` (default `.h264`) | raw H.264 | `…:313-406` |
| `rpi_raspivid_camera` | raspivid | `.h264` | raw H.264 | `…:45-109`; **disabled** (`if False:`) `REC/warecorder/warecorder_service.py:321` |

### 12.2 RTSP camera (ffmpeg ≥ 4.3)

```
ffmpeg -y -hide_banner
  [-timeout 5000000 | -stimeout 5000000]           # ffmpeg ≥ 5: -timeout; < 5: -stimeout; omitted if version unknown (µs socket I/O timeout)
  -rtsp_flags prefer_tcp -fflags +igndts -i <ip_camera_url>
  <codec block>                                     # default below, or shlex(ffmpeg_rtsp_parameters)
  -loglevel info
  -f <ffmpeg_rtsp_output_format or mp4> pipe:1
  [-frames:v 1 -filter:v scale=140:-1,hue=s=0 <INTERNAL_CACHE_DIR>/video_preview_image.jpg]
default codec block: -vcodec copy -an -map 0 -f ismv -movflags empty_moov+delay_moov -probesize 128 -analyzeduration 500
```

- Two `-f` apply to the same output; the last (`mp4`) wins. `empty_moov` makes the muxer fragment, so the payload is a fragmented MP4 (`ftyp`, `moov`, then `moof`/`mdat` pairs per keyframe, `mfra` at the end if ffmpeg exits cleanly). `-probesize`/`-analyzeduration` sit after `-i`, so they are output options with no effect on probing ([OI-28](05-open-issues.md#oi-28)). This behaviour was checked with ffmpeg n9.0.2 on a lavfi source (not with an RTSP camera).
- Second output: one grayscale JPEG 140 px wide, height keeps the ratio (e.g. 140×105), overwriting the preview at each period start.
- Version detection: `ffmpeg -version`, regex `ffmpeg version .?(\d\.\d)` on the lowercased output → float (`COMP/sensors/camera/rtsp_stream.py:22-39`). Two-digit majors are misparsed (`10.1` → `0.1`) ([OI-38](05-open-issues.md#oi-38)). Checkup requires ≥ 4.3 (`REC/warecorder/warecorder_common_runtime.py:178-179`).

### 12.3 Microphone

```
arecord -t <arecord_output_format or wav> <params>          # default params: -c 1 -r 22005 -f S16_LE  → stdout
ffmpeg -f alsa -loglevel error <params> -f <ffmpeg_alsa_output_format or mp3> pipe:1
                                                              # default params: -i default -ac 1 -acodec libmp3lame -ab 128k
```

WAV to a pipe carries placeholder RIFF/data sizes (arecord cannot seek back); 22 005 Hz is probably a typo for 22 050 ([OI-27](05-open-issues.md#oi-27)).

### 12.4 libcamera-vid (modern Raspberry Pi stack)

```
libcamera-vid --timeout 0 --nopreview --output <"-" | "pipe:" when muxing audio>
  <video params, default: --flush --framerate 30>
  [--codec libav --libav-format mpegts -q 95 --libav-audio --audio-codec aac --audio-bitrate 16000 --audio-device <first pulse source containing "input">
   <audio params, default: --flush --framerate 30>]
preview: libcamera-jpeg --nopreview --output <preview> --width 140 --height 104 --immediate   (timeout 20 s)
```

Pulse sources: `pulsectl` client name `witness-angel-device`, names containing `input` (`COMP/sensors/camera/raspberrypi_camera_microphone.py:23-34`).

### 12.5 picamera (legacy stack, chosen when `vcgencmd get_camera` contains `supported=1 `)

Parameters: `[sensor] picamera_parameters` = JSON object (must contain `resolution`; checked by `assert` only) or default `{"resolution": [1280, 720], "framerate": 30, "format": "h264", "quality": 25}`. `resolution`/`framerate` go to `PiCamera(...)`, the rest to `start_recording(...)`; `rotation` = `local_camera_rotation`; periods rotate with `split_recording(new_output)` (no gap, new cryptainer). Preview: `capture(path, use_video_port=True, format="jpeg", resize=(140, 104))`; live LCD preview 480×480 JPEG every `live_preview_interval_s` (`…:313-406`).

### 12.6 raspivid (disabled)

`raspivid --timeout 0 --nopreview -v --framerate 30 -pf baseline --width 1296 --height 730 --output -`; preview `raspistill --nopreview --output <p> --width 140 --height 104 --quality 90 -v`.

### 12.7 Preview image

`INTERNAL_CACHE_DIR/video_preview_image.jpg`, deleted then regenerated at each period start by the camera sensor (140 × 104 nominal) (`COMP/sensors/camera/_camera_base.py:14-45`). Not encrypted (privacy: one plaintext frame per period on disk). INFO.

---

## 13. Exported files

| File | Content | Evidence |
|---|---|---|
| `EXTERNAL_EXPORTS_DIR/<cryptainer name without ".crypt">` e.g. `20261026_120000_rtsp_camera_cryptainer.mp4` | the decrypted payload (an empty payload gives an empty file); **overwrites silently** ([OI-70](05-open-issues.md#oi-70)) | `COMP/screens/cryptainer_decryption_process.py:340-346` |
| `EXTERNAL_EXPORTS_DIR/<cryptainer name>_revelation_report_<UTC %Y%m%d_%H%M%S>.txt` | UTF-8 text of the operation report: one entry per paragraph, `Info: <message>` or `<CRITICITY>: <Type Title> (<ExceptionClass>)\nMessage: <message>` | `COMP/screens/cryptainer_decryption_result.py:83-108`, `COMP/utilities/__init__.py:228-253` |

---

## 14. Test vectors (fixtures)

[fixtures/](fixtures/) is produced by `fixtures/generate_fixtures.py` with the `warecorder_stable` cryptolib and the pinned library versions; it needs no Kivy (the three recorder/components functions involved are replicated with citations). Run:

```
PYTHONPATH=<witness-angel-cryptolib@warecorder_stable>/src python generate_fixtures.py --overwrite
```

Uids, keys and ciphertexts are random: every run changes the files; the final self-check MUST print `Fixtures OK`, and a reimplementation can mirror its assertions. The script overwrites `fixtures/` in place, so it refuses to run without `--overwrite`. **The examples quoted in this file (base64 uids in §2.2, §4.3, §5.4, §10.1, §10.3; file sizes such as 14 029 / 10 416 bytes) are bound to the committed fixtures: regenerate the fixtures and update these examples in the same change.**

| File | Content | What to test |
|---|---|---|
| `passphrases.json` | passphrases of the two guardians | |
| `authdevices/usb_{A,B}/authenticator.keystore/` | two authenticators (2 RSA_OAEP keypairs each, 1000-iteration PKCS#8), as on USB drives | §3.2 import source |
| `keystore_pool/` | the recorder pool: guardian A imported from USB **with** private keys, guardian B imported from the gateway (public only), `local_keyfactory/` with the unprotected response key | §2.2 layout, §3.2-§3.3 |
| `cryptoconf_threshold_{1,2}_of_2.json` | cryptoconfs exactly as the recorder builds them | §4.3 |
| `cryptoconf_schema.jsonschema.json`, `cryptainer_schema.jsonschema.json` | the cryptolib's jsonschemas (for ExtJSON trees) | validation |
| `cryptainers/20261026_120000_rtsp_camera_cryptainer.mp4.crypt` (+`.payload`) | 1-of-2, streamed in uneven chunks | decrypt with A's passphrase alone → `expected_payload.bin`; without passphrase → failure |
| `cryptainers/20261026_121500_rpi_microphone_cryptainer.wav.crypt` (+`.payload`) | 2-of-2 | needs B's shard from the gateway (§10.5) |
| `cryptainers/20261026_123000_rtsp_camera_cryptainer.mp4.crypt~` (+ 4 096-byte `.payload`) | unfinished (STARTED, `payload_macs` null) | listing with `finished=False`; schema refusal ([OI-46](05-open-issues.md#oi-46)) |
| `cryptainers/20261026_130000_to_20261026_130010_cryptainer.tar.crypt` (+`.payload`) | tar aggregation with `members` metadata | §9 |
| `expected_payload.bin` | 10 403-byte plaintext of all the above | |
| `wa_device_uid.json` | the requestor uid file | §2.1 |
| `gateway/get_public_authenticator.{request,response}.json` | for guardian B | §10.2 |
| `gateway/submit_revelation_request_{1,2}.request.json` | the two calls for the 2-of-2 cryptainer (A and B) | §10.3 envelope, item layout |
| `gateway/list_requestor_revelation_requests.{request,response}.json` | two ACCEPTED requests with DECRYPTED items, response data encrypted to the local response key exactly as the authenticator does ([AUTHSPEC 04 §5.3](../../witness-angel-authenticator/specifications/04-data-and-protocols.md#53-authenticator-processing-of-one-symkey-request-exact-pipeline)) | §10.5: decrypt the 2-of-2 cryptainer with no passphrase |
| `all_features/all_features_inline.crypt`, `all_features/cryptoconf.json`, `all_features/keystore_pool/` | not recorder-made: AES_EAX + CHACHA20_POLY1305 layers, nested symmetric key layer, `local_keyfactory` trustee, RSA_PSS/ECC_DSS/DSA_DSS signatures, inline ciphertext, metadata with int and date | general cryptainer reader, signature verification (no report errors expected) |
| `primitives.json` | AES/EAX/ChaCha20 deterministic vectors, hashes, a Shamir 2-of-3 set, verify-only signatures, a 3-chunk RSA-OAEP cipherdict with its key | §7 |
| `osc_messages.json` | byte-exact OSC datagrams | §11 |

The real 2023 gateway output `REC/list_requestor_revelation_requests_fixture.json` is a parse-only vector (§10.4); its keys are unknown.

### 14.1 Cryptolib acceptance test (whichever OI-100 option is chosen)

The choice of cryptolib for the reimplementation is pending ([OI-100](05-open-issues.md#oi-100)); the two current library generations cannot decrypt each other's cryptainers (§4.5). Whatever the decision, the reimplementation's test suite **MUST** include both directions, run against the exact library build it ships:

1. **Old → new.** The chosen library decrypts every finished 1.0 fixture to `expected_payload.bin`: the 1-of-2 cryptainer with guardian A's passphrase alone, the 2-of-2 cryptainer with the gateway fixture of §10.5, the tar cryptainer, and `all_features/all_features_inline.crypt` (no report errors).
2. **New → old.** `wacryptolib` `warecorder_stable` @ `b91aaf4`, unmodified, decrypts every cryptainer the new recorder writes, at least one per sensor it can record with (§12.1) and for thresholds 1-of-2 and 2-of-2, with the fixture guardians.

Under [OI-101](05-open-issues.md#oi-101) option (b), "the chosen library" is the reimplementation's own reader and writer.

---

## 15. Open issues

All open issues raised by this file are in [05](05-open-issues.md), with their final `OI-nn` IDs and dispositions.
