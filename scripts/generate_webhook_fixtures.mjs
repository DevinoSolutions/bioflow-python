/**
 * Regenerates tests/fixtures/webhook_signatures.json from the PRODUCER-side
 * TypeScript signer that BioFlow actually ships
 * (`packages/api/src/webhooks/signing.ts` — `signWebhook`).
 *
 * That makes tests/test_webhooks.py a genuine cross-implementation check: the
 * signatures were produced by the server's own code, and the Python verifier has
 * to accept exactly the ones the server would consider valid.
 *
 * Usage (Node >= 22.18, which strips TypeScript types natively):
 *
 *   node scripts/generate_webhook_fixtures.mjs [path/to/bioflow/packages/api/src/webhooks/signing.ts]
 *
 * Defaults to a sibling `bioflow` checkout. The fixtures are committed, so this
 * only needs re-running if the wire contract itself changes.
 */
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const here = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const repoRoot = resolve(here, "..");
const signerPath =
  process.argv[2] ??
  resolve(repoRoot, "..", "bioflow", "packages", "api", "src", "webhooks", "signing.ts");

const { signWebhook } = await import(pathToFileURL(signerPath).href);

const SECRET = "whsec_c2VjcmV0LW9uZS1mb3ItYmlvZmxvdy10ZXN0cw==";
const ROTATED_SECRET = "whsec_c2VjcmV0LXR3by1mb3ItYmlvZmxvdy10ZXN0cw==";
const OTHER_SECRET = "whsec_YW4tZW50aXJlbHktZGlmZmVyZW50LXNlY3JldA==";

const TIMESTAMP = 1767225600; // 2026-01-01T00:00:00Z
const ID = "whmsg_01JQZ0000000000000000000";

const body = (type, data) =>
  JSON.stringify({ id: ID, type, created_at: "2026-01-01T00:00:00.000Z", data });

const CONTACT_BODY = body("contact.created", {
  contact: {
    id: "ct_1",
    email: "fan@example.com",
    name: null,
    source: "email_capture",
    source_block_id: "bl_1",
    created_at: "2026-01-01T00:00:00.000Z",
  },
});
const UNICODE_BODY = body("page.published", {
  page: { id: "pg_1", title: "Café ☕ — naïve", slug: "cafe", published_at: "2026-01-01T00:00:00.000Z" },
});

const sign = (rawBody, secrets, id = ID, timestampSeconds = TIMESTAMP) =>
  signWebhook({ id, timestampSeconds, rawBody, secrets });

const cases = [
  {
    name: "valid_single_signature",
    note: "The ordinary case: one active secret, one v1 entry.",
    id: ID,
    timestamp: TIMESTAMP,
    payload: CONTACT_BODY,
    secret: SECRET,
    signature_header: sign(CONTACT_BODY, [SECRET]),
    valid: true,
  },
  {
    name: "valid_unicode_payload",
    note: "Signing is over the raw UTF-8 bytes, not a re-serialized object.",
    id: ID,
    timestamp: TIMESTAMP,
    payload: UNICODE_BODY,
    secret: SECRET,
    signature_header: sign(UNICODE_BODY, [SECRET]),
    valid: true,
  },
  {
    name: "valid_during_rotation_new_secret_first",
    note: "Rotation sends two entries; the consumer still holds the OLD secret.",
    id: ID,
    timestamp: TIMESTAMP,
    payload: CONTACT_BODY,
    secret: SECRET,
    signature_header: sign(CONTACT_BODY, [ROTATED_SECRET, SECRET]),
    valid: true,
  },
  {
    name: "valid_during_rotation_old_secret_first",
    note: "Same overlap, other order — the consumer has already stored the NEW secret.",
    id: ID,
    timestamp: TIMESTAMP,
    payload: CONTACT_BODY,
    secret: ROTATED_SECRET,
    signature_header: sign(CONTACT_BODY, [SECRET, ROTATED_SECRET]),
    valid: true,
  },
  {
    name: "invalid_tampered_body",
    note: "One byte changed after signing.",
    id: ID,
    timestamp: TIMESTAMP,
    payload: CONTACT_BODY.replace("fan@example.com", "attacker@example.com"),
    secret: SECRET,
    signature_header: sign(CONTACT_BODY, [SECRET]),
    valid: false,
  },
  {
    name: "invalid_tampered_id",
    note: "The webhook-id is part of the signed string.",
    id: "whmsg_01JQZ9999999999999999999",
    timestamp: TIMESTAMP,
    payload: CONTACT_BODY,
    secret: SECRET,
    signature_header: sign(CONTACT_BODY, [SECRET]),
    valid: false,
  },
  {
    name: "invalid_tampered_timestamp",
    note: "The timestamp is part of the signed string, so replaying it fails too.",
    id: ID,
    timestamp: TIMESTAMP + 1,
    payload: CONTACT_BODY,
    secret: SECRET,
    signature_header: sign(CONTACT_BODY, [SECRET]),
    valid: false,
  },
  {
    name: "invalid_wrong_secret",
    note: "A signature from a different endpoint's secret must never verify.",
    id: ID,
    timestamp: TIMESTAMP,
    payload: CONTACT_BODY,
    secret: SECRET,
    signature_header: sign(CONTACT_BODY, [OTHER_SECRET]),
    valid: false,
  },
  {
    name: "invalid_no_v1_entry",
    note: "An unknown signature version must not be treated as a match.",
    id: ID,
    timestamp: TIMESTAMP,
    payload: CONTACT_BODY,
    secret: SECRET,
    signature_header: sign(CONTACT_BODY, [SECRET]).replace("v1,", "v2,"),
    valid: false,
  },
];

const fixtures = {
  generated_by: "packages/api/src/webhooks/signing.ts :: signWebhook (BioFlow app repo)",
  generator: "scripts/generate_webhook_fixtures.mjs",
  contract: "Standard Webhooks v1 — HMAC-SHA256 over `${id}.${timestamp}.${rawBody}`",
  cases,
};

const outputPath = resolve(repoRoot, "tests", "fixtures", "webhook_signatures.json");
writeFileSync(outputPath, `${JSON.stringify(fixtures, null, 2)}\n`, "utf8");
console.log(`wrote ${outputPath} (${cases.length} cases)`);
