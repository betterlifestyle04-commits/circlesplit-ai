# CircleSplit AI — safer persistence for the sandbox demo

CircleSplit uses SQLite. The active [`render.yaml`](../render.yaml)
uses a **Free** Render web service and has no persistent disk. This is
intentional for an inexpensive, fictional-data hackathon demo, but there is a
fundamental safety limitation: events, approvals, invite tokens, idempotency
keys, and the PayPal **Sandbox** order/capture ledger can disappear when the
service restarts, spins down or redeploys.

Render's documentation states that its Free web service filesystem is
ephemeral and that persistent disks require paid compute:
- https://render.com/docs/free
- https://render.com/docs/disks

A Free Render Postgres instance is **not** a permanent alternative; Render's
Free database instances expire after 30 days and do not have managed backups.
For a real service, prefer a managed durable database with a proper migration,
identity model and disaster recovery design.

## Browser-local dataset-change warning

The protected workspace now checks the database incarnation prefix and
two aggregate evidence counts on startup. It stores a checkpoint **only
in the currently used browser**, not on Render or an offsite server.
When a later visit sees a different database incarnation or fewer
locally recorded verified Sandbox captures or webhook events, it displays
a warning across the workspace. The older checkpoint is preserved until
an organizer acknowledges external investigation.

Open **Activity → Dataset continuity monitor** to check again, see
aggregate comparisons, and acknowledge a new browser baseline after
inspecting prior private manifest files and PayPal Sandbox records.
Acknowledgement does not import, restore, delete, reconcile or refund
anything. It cannot detect an earlier reset on a browser that never
stored a checkpoint; private browsing, disabled localStorage and other
devices have independent or missing history.

This small addition is **not** a persistent disk, automatic backup, remote
audit, or tested disaster recovery procedure. It does not change the
requirements for a durable database and externally verified payment
reconciliation.

## Changes implemented now

- During SQLite initialization, `storage_identity` records a randomly
  generated **database incarnation ID** and its creation timestamp. An existing
  DB keeps this ID across restarts. Replacing/losing the DB creates a new ID.
  The protected `GET /api/judge-readiness` response exposes only the first
  12 hexadecimal characters, not secrets or filesystem paths. Compare the ID
  before and after deploys; a changed ID means the **local** database changed
  and financial records might need external investigation.
- `GET /api/judge-readiness` reports `storage` (`ephemeral-sqlite`,
  `mounted-sqlite` or `local-sqlite-unverified`), whether an actual non-root
  mount was found, and the checkout guard status. The protected workspace
  displays a prominent warning for ephemeral hosted storage.
- Optional `CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB=1` refuses **new**
  PayPal Sandbox order creation with HTTP 503 unless the configured database
  is physically under a verified mount. This guard executes before local
  payment rows or remote PayPal calls are created. Existing order status
  checks, previously initiated captures and signature-verified webhooks
  remain available: blocking recovery could make an uncertain payment worse.
- Setting `CIRCLESPLIT_PERSISTENT_MOUNT` to any existing directory is **not**
  sufficient; the application checks that it is a real non-root mount and
  contains the database file. It does not equate environment variables or
  directory names with data durability. On a platform with unusual bind mounts,
  the conservative guard can report unverified and reject new orders.

The gate is **off by default** to avoid breaking the present judge sandbox
flow. The active Free blueprint remains unchanged. A warning is not a backup.

## Compare saved private manifests after a suspected reset

The organizer's protected **Activity → Compare private recovery snapshots**
panel accepts an earlier and a later reconciliation manifest JSON file.
Both are processed on the device, without uploading them. The browser checks
the recorded SHA-256 digest for each file and reports aggregate changes.

If the SQLite incarnation changes, local payment IDs may be reused. The
comparison matches **known PayPal Sandbox order IDs only** across different
incarnations; unknown-order creation attempts cannot be matched and require
manual investigation. Missing an order in the new database does not prove
that the PayPal order ceased to exist. Always inspect PayPal Sandbox directly.
The exported manifest can contain names and payment identifiers, so keep the
source files private and never commit them. A digest is not a signature.

## In-flight Sandbox order creation during ephemeral database loss

New order creation checks the original database incarnation and original
payment request keys **after** PayPal Sandbox responds, before saving a
provider order ID or returning a success response. If Render Free resets
the SQLite file mid-request, it cannot accidentally assign the old Sandbox
order to a new payment row that reused the same integer ID. The endpoint
fails closed and instructs an external provider review. A remote order can
still exist even when CircleSplit lost its record, and a fresh request on
a newly reset database could still duplicate a previous attempt. **This
guard does not substitute for persistent storage or PayPal reconciliation.**

## Save a reconciliation snapshot before a risky redeploy

If the protected workspace is accessible and contains PayPal Sandbox orders,
use the organizer credential and **Activity → Save private reconciliation manifest** to download an
authenticated, local read-only JSON inventory. It includes Sandbox order IDs
and locally recorded capture IDs, along with the database incarnation. It
does **not** include idempotency secrets or invitation links. Keep it private;
it cannot be restored into the application or used to recreate payments.

The SHA-256 field only checks accidental record-array changes, not document
authenticity. Exporting does **not** make the SQLite database durable, and
only the records still present at export time can be saved. Check any
uncertain order at PayPal itself. For more than 10,000 payment attempts the
endpoint rejects the request; use an operator-led encrypted DB backup.

## Compare two encrypted backup generations safely

Before using any archived ledger as recovery evidence, compare an older
and a newer encrypted backup **offline**:

```bash
python tools/encrypted_snapshot.py compare \
  --previous /private/backups/older.csb \
  --current /private/backups/newer.csb \
  --previous-key-file /private/keys/older.passphrase \
  --current-key-file /private/keys/newer.passphrase
```

This operation independently authenticates both encrypted files, checks
each SQLite backup's SHA-256, schema, incarnation and payment-ledger
consistency, then compares remembered PayPal Sandbox order/capture
identifiers **in private memory**. Only aggregated numerical differences
leave the tool. Cross-database comparisons never equate local SQLite
payment IDs, which can be reused after a reset. Same-database
comparisons also check whether earlier local request keys vanished.

Any changed incarnation, older known provider order or capture missing,
decline in ledger/webhook counts, altered previously known amount or
capture, reverted completion, local audit inconsistency, or backwards
manifest creation time returns `NEEDS_REVIEW` (exit 3). A clean local
comparison returns 0; invalid key, corrupted archive or incompatible
ledger returns 2. Unknown order-creation attempts are counted but
cannot be safely matched across a different database incarnation.

**Do not assume that missing local evidence means PayPal did not
process the request.** This check has no PayPal provider access. The
operator must separately reconcile with their Sandbox dashboard or
provider API before restoring historical data or retrying a payment.
The process never imports a ledger, contacts a payment provider or
uploads confidential archives. Both generations and their keys must
remain securely retained for the comparison to be useful.

## Optional encrypted, locally generated backup archive

The new `tools/encrypted_snapshot.py` builds on the existing offline SQLite
backup and audit routines, and combines a consistent snapshot with its
manifest **inside one AES-256-GCM encrypted `.csb` archive**. It uses a
different random salt and GCM nonce per archive, scrypt key derivation
(`N=32768, r=8, p=1`), and authenticates both file contents and the archive
header. Encryption and decryption are streamed; temporary plaintext
databases are restricted to isolated directories and removed after use.

```bash
pip install -r requirements-ops.txt
mkdir -m 700 -p /private/circlesplit-backups /private/circlesplit-keys
python tools/encrypted_snapshot.py keygen \
  --output /private/circlesplit-keys/circlesplit.passphrase
python tools/encrypted_snapshot.py seal \
  --source /absolute/path/circlesplit.sqlite3 \
  --output /private/circlesplit-backups/snapshot-20261105.csb \
  --key-file /private/circlesplit-keys/circlesplit.passphrase
python tools/encrypted_snapshot.py verify \
  --bundle /private/circlesplit-backups/snapshot-20261105.csb \
  --key-file /private/circlesplit-keys/circlesplit.passphrase
python tools/encrypted_snapshot.py drill \
  --bundle /private/circlesplit-backups/snapshot-20261105.csb \
  --key-file /private/circlesplit-keys/circlesplit.passphrase
```

The key is a separately generated, unprinted, random private
`.passphrase` file. On POSIX, destination directories require user ownership
and mode 0700, and the key file is enforced as 0600. Restrict NTFS ACLs
manually on Windows. Neither a key nor plaintext SQL data belongs in Git,
Devpost, screenshots or command-line arguments. Only archive files should
be copied to independently secured offsite storage; retain the key separately
with a documented recovery owner. Losing the key makes the encrypted backup
unusable. Cryptographic authentication does **not** validate external PayPal
settlement or prove the accuracy of the original ledger.

Both `verify` and `drill` decrypt only to a private temporary folder and
do not offer an import into the running service. The drill repeats the
locally bounded payment-ledger semantic audit and uses exit status `3`
when local contradictions require investigation. There is no scheduled
backup, hosted uploader, live restore, payment API call, or automatic financial
replay. The current Render Free service remains ephemeral; operators still
need access to an actual DB file and a secure offsite storage provider to
implement durable backups.

## Operator-only SQLite snapshot and isolated restore drill

For a **local SQLite development copy** or a future operator-accessible
single-instance service, the repository now provides
`tools/sqlite_snapshot.py`, supporting only `create`, `verify` and
`drill`. It is **not** connected to the API or public browser.

```bash
# Execute on the machine where the real SQLite DB exists.
mkdir -m 700 -p ./private-sandbox-backups
python tools/sqlite_snapshot.py create --source /absolute/path/circlesplit.sqlite3 \
  --output ./private-sandbox-backups/snapshot-20261105.sqlite3
python tools/sqlite_snapshot.py verify \
  --snapshot ./private-sandbox-backups/snapshot-20261105.sqlite3
python tools/sqlite_snapshot.py drill \
  --snapshot ./private-sandbox-backups/snapshot-20261105.sqlite3
```

The creator refuses to overwrite an existing snapshot or its matching
`.manifest.json`. It uses SQLite's online `backup()` API rather than
copying a live DB file directly; committed WAL transactions are included.
The staged copy is converted to a standalone, checkpointed database and
checked with `PRAGMA integrity_check`. Its manifest records a SHA-256
checksum, exact byte size, database incarnation UUID, timestamp and aggregate
event/expense/participant/payment/webhook counts, **not** individuals or
provider identifiers. Both output files are private and must be saved
together. On POSIX, the output directory must be user-owned and mode 0700;
Windows operators must restrict NTFS ACLs manually.

The `verify` command compares size, SHA-256, schema and database identity
and re-counts records without writing data. The `drill` command verifies
the copy, reads a temporary *isolated* rehearsal copy, and discards it.
The isolated `drill` now also runs the existing **read-only local ledger
audit** on the copied database, checking payment/event/participant links,
exact stored amount agreement, completed-capture consistency, duplicate
capture IDs and multiple orders per person. The command returns only
aggregated issue codes and counts. An unresolved Sandbox order is counted
but is **not** automatically an integrity violation.

The CLI exits `0` for a complete, locally consistent drill, `2` for
snapshot/integrity/schema verification failure, or `3` when the backup
is structurally intact but local payment anomalies require manual review.
A report of `NEEDS_REVIEW` must never trigger a payment retry or automated
financial import. The semantic scan is limited to 50,000 payment records
to avoid unbounded processing.

Neither operation restores data into the running service. For actual disaster
recovery, stop the service, compare private manifests and the Sandbox provider
ledger externally, and design an operator-reviewed migration plan. **Never
overwrite a live ledger or automatically replay financial transactions.**

**Confidentiality:** a raw snapshot includes private invitation hashes,
fictional names, Sandbox order IDs, idempotency keys and other private app
data. Store it offline/encrypted, control access, and never upload it to
Devpost, public GitHub, logs, or public storage. Digest verification detects
accidental modification but is not authentication, encryption or proof of
payment settlement. The tool does not automate scheduled copies or make
Render Free storage durable; the current Free service has no guaranteed
operator-readable persistent DB and no offsite backups.

## Preparing a paid persistent disk (opt-in only)

A separate, **inactive** example is provided:
[`render.persistent.example.yaml`](../render.persistent.example.yaml).

1. Decide whether a paid persistent disk is appropriate. Compare the service
   and disk prices and usage policies in your Render dashboard **before**
   changing your plan. This project does **not** automatically upgrade anything.
2. Preserve any existing sandbox payment history you can still access and
   review live PayPal Sandbox orders externally before moving the database.
   Do **not** assume a fresh empty DB means prior sandbox charges never
   happened. Never copy an unknown or conflicting ledger over an active DB.
3. Attach a persistent disk with an actual mount such as `/var/data`, on a
   paid single-instance web service, then configure:
   ```
   CIRCLESPLIT_DB=/var/data/circlesplit.sqlite3
   CIRCLESPLIT_PERSISTENT_MOUNT=/var/data
   CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB=1
   ```
4. Ensure the storage directory is writable by the web-service process;
   verify the database is truly inside the mount. Existing DB migration or
   copying must be conducted carefully while the service is stopped. Moving
   only the DB filename in environment configuration **does not** transfer
   its historical rows.
5. Re-deploy, authenticate into the protected workspace, and confirm that
   `storage` reports `mounted-sqlite`,
   `persistent_mount_verified` is true, and new sandbox checkout is allowed
   only when explicitly configured and the server agrees.
6. Check the database incarnation ID and existing PayPal Sandbox provider
   records before and after a further controlled deployment. Enable regular
   encrypted backups and perform a restore drill. A disk is not a replacement
   for external backups, account-level isolation or production controls.

**Operational tradeoffs:** Render documents that a service with an attached
persistent disk is single-instance and cannot use zero-downtime deploys.
Backups and webhook reconciliation are still necessary. Avoid treating
mounted storage as proof of an actual payment or verified identity.

## Security boundaries

- No production PayPal charges, payouts or escrow are supported.
- Never publish a raw SQLite backup to GitHub or a public URL. It can contain
  bearer-invitation hashes, financial identifiers, RSVP answers and private
  event details.
- The dataset ID is a diagnostic marker, not a password, receipt, guarantee
  of durability, or evidence of a PayPal capture.
- Treat a changed dataset ID as a **stop and investigate** signal before
  re-creating orders. An old sandbox checkout can still exist upstream even
  if its local ledger disappeared.
- A paid disk is a possible bridge for this single-instance hackathon demo.
  Durable Postgres, backup/restore, strict identity controls, proper audit
  trails and tenancy isolation remain prerequisites for a real service.
