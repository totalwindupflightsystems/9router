import { v4 as uuidv4 } from "uuid";
import { getAdapter } from "../driver.js";
import { nowIso, stampInsert, stampUpdate, stampDelete, NOT_DELETED } from "../../federation/stamp.js";

function rowToKey(row) {
  if (!row) return null;
  return {
    id: row.id,
    key: row.key,
    name: row.name,
    machineId: row.machineId,
    isActive: row.isActive === 1 || row.isActive === true,
    createdAt: row.createdAt,
  };
}

export async function getApiKeys() {
  const db = await getAdapter();
  const rows = db.all(`SELECT * FROM apiKeys WHERE ${NOT_DELETED} ORDER BY createdAt ASC`);
  return rows.map(rowToKey);
}

export async function getApiKeyById(id) {
  const db = await getAdapter();
  const row = db.get(`SELECT * FROM apiKeys WHERE id = ? AND ${NOT_DELETED}`, [id]);
  return rowToKey(row);
}

export async function createApiKey(name, machineId) {
  if (!machineId) throw new Error("machineId is required");
  const db = await getAdapter();
  const { generateApiKeyWithMachine } = await import("@/shared/utils/apiKey");
  const result = generateApiKeyWithMachine(machineId);
  const apiKey = {
    id: uuidv4(),
    name,
    key: result.key,
    machineId,
    isActive: true,
    createdAt: new Date().toISOString(),
  };
  const s = stampInsert(db);
  db.run(
    `INSERT INTO apiKeys(id, key, name, machineId, isActive, createdAt${s.cols}) VALUES(?, ?, ?, ?, ?, ?${s.placeholders})`,
    [apiKey.id, apiKey.key, apiKey.name, apiKey.machineId, 1, apiKey.createdAt, ...s.params]
  );
  return apiKey;
}

export async function updateApiKey(id, data) {
  const db = await getAdapter();
  let result = null;
  db.transaction(() => {
    // NOT_DELETED: a tombstoned row must be invisible to writes too, not only to
    // reads. Without it a direct caller (the federation replay path, which does
    // not pre-check getApiKeyById) mutates columns of a row every sibling read
    // hides — pre-fix, with validateApiKey unfiltered, that was a
    // resurrect-by-forge: write a chosen `key` onto a deleted row and it
    // authenticates. The dashboard route is already guarded upstream
    // (src/app/api/keys/[id]/route.js:26 pre-checks getApiKeyById → 404), so this
    // only tightens the shared repository contract.
    const row = db.get(`SELECT * FROM apiKeys WHERE id = ? AND ${NOT_DELETED}`, [id]);
    if (!row) return;
    const merged = { ...rowToKey(row), ...data };
    const u = stampUpdate(db);
    db.run(
      `UPDATE apiKeys SET key = ?, name = ?, machineId = ?, isActive = ?${u.set} WHERE id = ?`,
      [merged.key, merged.name, merged.machineId, merged.isActive ? 1 : 0, ...u.params, id]
    );
    result = merged;
  });
  return result;
}

export async function deleteApiKey(id) {
  const db = await getAdapter();
  const d = stampDelete(db);
  const res = db.run(`UPDATE apiKeys SET ${d.set} WHERE id = ?`, [...d.params, id]);
  return (res?.changes ?? 0) > 0;
}

export async function validateApiKey(key) {
  const db = await getAdapter();
  // NOT_DELETED is load-bearing: deleteApiKey() is a tombstone (stampDelete sets
  // deleted = 1 and leaves isActive = 1), so without the predicate a key removed
  // through DELETE /api/keys/[id] keeps authenticating remote /v1 traffic — a
  // revocation that does not revoke. This is the authorization read for the
  // public API surface (src/dashboardGuard.js:166, src/sse/services/auth.js:373).
  const row = db.get(`SELECT isActive FROM apiKeys WHERE key = ? AND ${NOT_DELETED}`, [key]);
  if (!row) return false;
  return row.isActive === 1 || row.isActive === true;
}
