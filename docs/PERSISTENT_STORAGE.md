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
