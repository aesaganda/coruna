# Repository Comparison: Upstream vs Coruna Orchestrator

Technical comparison between upstream reference implementations ([khanhduytran0/coruna](https://github.com/khanhduytran0/coruna)) and the code in `exploits/coruna/`, highlighting bug fixes and compatibility enhancements.

---

## 1. Upstream Deficiencies for Bluebird (iOS 15.6 – 16.1.2)

1. **Module Resolution in `group.html`**:
   - In upstream `group.html`, `hPL3On` was assigned via `this.getModuleByName`. Inside an IIFE, `this` refers to the global object, meaning `obChTK.hPL3On` resolved to `undefined` when called by Bluebird.
   - **Fix**: Direct function references are bound to `obChTK`.

2. **Primitive Normalization (`Xn` → `exploitPrimitive`)**:
   - Bluebird exports its memory primitives under `P.zn.Xn` with methods `tr`, `Mr`, `br`, `dr`, while Stage 3 expects `platformState.exploitPrimitive` exposing standard methods `addrof`, `fakeobj`, `read32`, `write32`, etc.
   - **Fix**: The loader normalizes `Xn` and provides aliases so that Stage 3 can access memory transparently regardless of the loaded Stage 1 primitive.

3. **Missing `platformState.Nn` and Version Offsets**:
   - Bluebird and Stage 3 VariantA attempt to read `P.zn.Nn.fGOrHX`, `P.zn.Nn.oGn3OG`. In upstream code, `Nn` was undefined, resulting in an immediate uncaught `TypeError`.
   - **Fix**: Initialized `Nn: {}` and populated version offsets for the `150600` version block.

---

## 2. Memory Primitive Methods Required by Stage 3

Stage 3 (`Stage3_VariantB.js` and `Stage3_VariantA.js`) assumes a standardized primitive interface. Bluebird initially exposed disparate method names. The following aliases are normalized:

- `addrof` (← `tr`), `fakeobj` (← `Mr`), `read32` (← `br`), `write32` (← `dr`)
- `readRawBigInt`, `read32FromInt64`, `readInt64FromInt64`, `copyBigInt`, `writeInt64ToOffset`
- `readString`, `readStringFromInt64`

Additionally, two methods were introduced:

| Method | Role in Stage 3 | Implementation |
|---|---|---|
| `readByte(addr)` | Single-byte read for Mach-O export trie and symbol parsing | `(ep.br(addr & ~3) >>> (8 * (addr % 4))) & 0xff` |
| `readDoubleAsPointer(addr)` | 8-byte pointer comparison as IEEE-754 double | Reconstructs 64-bit float from dual 32-bit reads via `Float64Array` / `Uint32Array` buffers |

---

## 3. Crash Loop Prevention

- **Upstream**: Calling `cleanup()` on failed stages without tracking execution state caused Safari to auto-reload and crash indefinitely ("A problem repeatedly occurred").
- **Fix**: A `sessionStorage` guard (`CORUNA_DONE_KEY`) marks attempts before loading Stage 3, preventing persistent crash loops on failed runs.

---

## 4. Modified Files Summary

| File | Upstream | This Repository |
|---|---|---|
| `group.html` | Faulty `this` binding, missing `Xn` normalization, no reload guards | Fixed bindings, normalized primitives, `readByte`/`readDoubleAsPointer`, `CORUNA_DONE_KEY` |
| `platform_module.js` | Missing `Nn`, incomplete 150600 block | Full `Nn` initialization and complete offsets for Bluebird |
| `Stage1_13.0_15.1.1_buffout.js` | Missing in upstream (resulted in 404) | Fully integrated and wired into loader |
| `Stage3_VariantB.js` | Silent failures on corrupt Mach-O buffers | Explicit size and HTTP status verification for `bootstrap.dylib` |
