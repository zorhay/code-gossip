"""SQLite ownership: evidence, both trajectories, and delivery history.

Transactions are short. A separate per-session process lock serializes builders;
collectors continue to append while a builder waits on a provider.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from .contracts import QUIET_SECONDS, MAX_BATCH_SECONDS, MAX_BATCH_EVENTS, MAX_BATCH_BYTES


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
 id INTEGER PRIMARY KEY, agent TEXT NOT NULL, source_id TEXT NOT NULL,
 original_task TEXT NOT NULL DEFAULT '', updated REAL NOT NULL,
 UNIQUE(agent, source_id));
CREATE TABLE IF NOT EXISTS interactions (
 id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions ON DELETE CASCADE,
 source_id TEXT, ordinal INTEGER NOT NULL, request TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'active', boundary TEXT NOT NULL,
 UNIQUE(session_id, source_id), UNIQUE(session_id, ordinal));
CREATE TABLE IF NOT EXISTS session_trajectories (
 session_id INTEGER PRIMARY KEY REFERENCES sessions ON DELETE CASCADE,
 context TEXT NOT NULL DEFAULT '', context_through INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS interaction_trajectories (
 interaction_id INTEGER PRIMARY KEY REFERENCES interactions ON DELETE CASCADE,
 context TEXT NOT NULL DEFAULT '', context_through INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS batches (
 id INTEGER PRIMARY KEY, interaction_id INTEGER NOT NULL REFERENCES interactions ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
 closed INTEGER NOT NULL DEFAULT 0, urgent INTEGER NOT NULL DEFAULT 0,
 bytes INTEGER NOT NULL DEFAULT 0, count INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
 UNIQUE(interaction_id, ordinal));
CREATE UNIQUE INDEX IF NOT EXISTS one_open_batch ON batches(interaction_id) WHERE closed=0;
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions ON DELETE CASCADE,
 interaction_id INTEGER REFERENCES interactions ON DELETE CASCADE,
 batch_id INTEGER REFERENCES batches ON DELETE CASCADE,
 source_id TEXT, event TEXT NOT NULL, received REAL NOT NULL,
 call_id TEXT NOT NULL, payload TEXT NOT NULL, evidence TEXT NOT NULL,
 UNIQUE(session_id, source_id));
CREATE INDEX IF NOT EXISTS events_batch ON events(batch_id, id);
CREATE TABLE IF NOT EXISTS tool_links (
 session_id INTEGER NOT NULL REFERENCES sessions ON DELETE CASCADE,
 kind TEXT NOT NULL, source_id TEXT NOT NULL,
 interaction_id INTEGER NOT NULL REFERENCES interactions ON DELETE CASCADE,
 PRIMARY KEY(session_id, kind, source_id));
CREATE TABLE IF NOT EXISTS interaction_records (
 batch_id INTEGER PRIMARY KEY REFERENCES batches ON DELETE CASCADE,
 trajectory_id INTEGER NOT NULL REFERENCES interaction_trajectories ON DELETE CASCADE,
 summary TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS session_records (
 interaction_id INTEGER PRIMARY KEY REFERENCES interaction_trajectories ON DELETE CASCADE,
 trajectory_id INTEGER NOT NULL REFERENCES session_trajectories ON DELETE CASCADE,
 through_batch INTEGER NOT NULL, summary TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS narrations (
 id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL UNIQUE REFERENCES batches ON DELETE CASCADE,
 text TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, finished REAL,
 session_through INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS interactions_session ON interactions(session_id, ordinal);
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(str(path), timeout=.5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.path.chmod(0o600)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def row(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def rows(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args)]

    def collect(self, event):
        """Append evidence before any playback decision. Return the session key."""
        with self.transaction():
            self.db.execute("INSERT INTO sessions(agent,source_id,updated) VALUES(?,?,?) "
                            "ON CONFLICT(agent,source_id) DO UPDATE SET updated=excluded.updated",
                            (event.agent, event.session, event.received))
            session = self.row("SELECT * FROM sessions WHERE agent=? AND source_id=?", (event.agent, event.session))
            sid = session["id"]
            self.db.execute("INSERT OR IGNORE INTO session_trajectories(session_id) VALUES(?)", (sid,))
            if event.source_id and self.row("SELECT id FROM events WHERE session_id=? AND source_id=?", (sid, event.source_id)):
                return sid
            interaction = self._interaction(sid, event)
            iid = interaction["id"] if interaction else None
            batch = None
            if iid:
                for kind, key in (("call", event.call), ("process", event.process)):
                    if key:
                        self.db.execute("INSERT OR IGNORE INTO tool_links VALUES(?,?,?,?)", (sid, kind, key, iid))
                if event.actor and event.event in ("SubagentStart", "subagentStart"):
                    self.db.execute("INSERT OR IGNORE INTO tool_links VALUES(?,?,?,?)", (sid, "actor", event.actor, iid))
                size = len(event.evidence.encode())
                batch = self.row("SELECT * FROM batches WHERE interaction_id=? AND closed=0", (iid,))
                if batch and (batch["count"] >= MAX_BATCH_EVENTS or batch["bytes"] + size > MAX_BATCH_BYTES
                              or event.received - batch["created"] >= MAX_BATCH_SECONDS):
                    self.db.execute("UPDATE batches SET closed=1 WHERE id=?", (batch["id"],))
                    batch = None
                if not batch:
                    ordinal = self.row("SELECT coalesce(max(ordinal),0)+1 AS n FROM batches WHERE interaction_id=?", (iid,))["n"]
                    bid = self.db.execute("INSERT INTO batches(interaction_id,ordinal,created,updated) VALUES(?,?,?,?)",
                                          (iid, ordinal, event.received, event.received)).lastrowid
                else:
                    bid = batch["id"]
                self.db.execute("UPDATE batches SET count=count+1,bytes=bytes+?,updated=?,closed=?,urgent=max(urgent,?) WHERE id=?",
                                (size, event.received, int(event.urgent or interaction["status"] != "active"), int(event.urgent), bid))
                if event.ending:
                    self.db.execute("UPDATE interactions SET status=? WHERE id=?", (event.ending, iid))
                # Late evidence invalidates the rollup, not the historical batch records.
                self.db.execute("DELETE FROM session_records WHERE interaction_id=?", (iid,))
                self.db.execute("UPDATE session_trajectories SET context='',context_through=0 WHERE session_id=? AND context_through>=?",
                                (sid, interaction["ordinal"]))
            else:
                bid = None
            self.db.execute("INSERT INTO events(session_id,interaction_id,batch_id,source_id,event,received,call_id,payload,evidence) "
                            "VALUES(?,?,?,?,?,?,?,?,?)", (sid, iid, bid, event.source_id or None, event.event,
                                                         event.received, event.call, event.payload, event.evidence))
            return sid

    def _interaction(self, sid, event):
        interaction = None
        if event.actor and not event.starts:
            interaction = self.row("SELECT i.* FROM interactions i JOIN tool_links t ON t.interaction_id=i.id "
                                   "WHERE t.session_id=? AND t.kind='actor' AND t.source_id=?", (sid, event.actor))
        if not interaction and event.turn:
            interaction = self.row("SELECT * FROM interactions WHERE session_id=? AND source_id=?", (sid, event.turn))
        if not interaction and not event.starts:
            for kind, key in (("actor", event.actor), ("call", event.call), ("process", event.process_ref)):
                if key:
                    interaction = self.row("SELECT i.* FROM interactions i JOIN tool_links t ON t.interaction_id=i.id "
                                           "WHERE t.session_id=? AND t.kind=? AND t.source_id=?", (sid, kind, key))
                    if interaction:
                        break
        if not interaction and (event.starts or event.turn and (not event.actor or event.event in ("SubagentStart", "subagentStart"))):
            # A native turn can arrive before its prompt. Preserve its identity and fill the request later.
            if event.starts:
                active = self.rows("SELECT id FROM interactions WHERE session_id=? AND status='active'", (sid,))
                for old in active:
                    self.db.execute("UPDATE interactions SET status='superseded' WHERE id=?", (old["id"],))
                    self.db.execute("UPDATE batches SET closed=1 WHERE interaction_id=?", (old["id"],))
            ordinal = self.row("SELECT coalesce(max(ordinal),0)+1 AS n FROM interactions WHERE session_id=?", (sid,))["n"]
            iid = self.db.execute("INSERT INTO interactions(session_id,source_id,ordinal,request,boundary) VALUES(?,?,?,?,?)",
                                  (sid, event.turn or None, ordinal, event.prompt, "native" if event.turn else "prompt")).lastrowid
            self.db.execute("INSERT INTO interaction_trajectories(interaction_id) VALUES(?)", (iid,))
            interaction = self.row("SELECT * FROM interactions WHERE id=?", (iid,))
        if not interaction and not event.turn:
            interaction = self.row("SELECT * FROM interactions WHERE session_id=? AND status='active' ORDER BY ordinal DESC LIMIT 1", (sid,))
        if interaction and event.prompt:
            self.db.execute("UPDATE interactions SET request=? WHERE id=?", (event.prompt, interaction["id"]))
            self.db.execute("UPDATE sessions SET original_task=? WHERE id=? AND original_task=''", (event.prompt, sid))
            interaction["request"] = event.prompt
        return interaction

    def seal_due(self, sid, now):
        with self.transaction():
            self.db.execute("UPDATE batches SET closed=1 WHERE closed=0 AND interaction_id IN "
                            "(SELECT id FROM interactions WHERE session_id=?) AND (updated<=? OR created<=?)",
                            (sid, now - QUIET_SECONDS, now - MAX_BATCH_SECONDS))

    def next_batch(self, sid):
        return self.row("SELECT b.*,i.session_id,i.request,i.status,i.ordinal AS interaction_order "
                        "FROM batches b JOIN interactions i ON i.id=b.interaction_id "
                        "LEFT JOIN interaction_records r ON r.batch_id=b.id "
                        "WHERE i.session_id=? AND r.batch_id IS NULL ORDER BY i.ordinal,b.ordinal LIMIT 1", (sid,))

    def batch_events(self, bid):
        return [{"id": row["id"], "event": row["event"], "evidence": json.loads(row["evidence"])}
                for row in self.rows("SELECT id,event,evidence FROM events WHERE batch_id=? ORDER BY id", (bid,))]

    def commit_batch(self, summary, now):
        with self.transaction():
            batch = self.row("SELECT * FROM batches WHERE id=? AND closed=1", (summary.batch_id,))
            if not batch:
                raise ValueError("Only a closed batch can be summarized")
            self.db.execute("INSERT OR IGNORE INTO interaction_records VALUES(?,?,?,?)",
                            (batch["id"], batch["interaction_id"], summary.text, now))
            self.db.execute("UPDATE batches SET error='' WHERE id=?", (batch["id"],))

    def next_rollup(self, sid):
        return self.row("SELECT i.*,coalesce(max(b.id),0) AS through_batch FROM interactions i "
                        "JOIN batches b ON b.interaction_id=i.id "
                        "LEFT JOIN interaction_records r ON r.batch_id=b.id "
                        "LEFT JOIN session_records s ON s.interaction_id=i.id "
                        "WHERE i.session_id=? AND i.status!='active' GROUP BY i.id "
                        "HAVING count(b.id)=count(r.batch_id) AND (s.interaction_id IS NULL OR s.through_batch<max(b.id)) "
                        "ORDER BY i.ordinal LIMIT 1", (sid,))

    def commit_rollup(self, summary, now):
        with self.transaction():
            interaction = self.row("SELECT * FROM interactions WHERE id=?", (summary.interaction_id,))
            latest = self.row("SELECT max(id) AS n FROM batches WHERE interaction_id=?", (summary.interaction_id,))["n"]
            if latest != summary.through_batch:
                return False  # New evidence arrived while the provider was working.
            self.db.execute("INSERT INTO session_records VALUES(?,?,?,?,?) ON CONFLICT(interaction_id) DO UPDATE SET "
                            "through_batch=excluded.through_batch,summary=excluded.summary,created=excluded.created",
                            (interaction["id"], interaction["session_id"], summary.through_batch, summary.text, now))
            return True

    def trajectory(self, scope, owner, before=None):
        if scope == "interaction":
            root = self.row("SELECT * FROM interaction_trajectories WHERE interaction_id=?", (owner,))
            records = self.rows("SELECT b.ordinal AS position,r.summary,b.id AS source FROM interaction_records r "
                                "JOIN batches b ON b.id=r.batch_id WHERE r.trajectory_id=? ORDER BY b.ordinal", (owner,))
        else:
            root = self.row("SELECT * FROM session_trajectories WHERE session_id=?", (owner,))
            records = self.rows("SELECT i.ordinal AS position,r.summary,i.id AS source FROM session_records r "
                                "JOIN interactions i ON i.id=r.interaction_id WHERE r.trajectory_id=? ORDER BY i.ordinal", (owner,))
        if before is not None:
            records = [r for r in records if r["position"] < before]
            if root["context_through"] >= before:
                root = {"context": "", "context_through": 0}
        return {"context": root["context"], "through": root["context_through"],
                "records": [r for r in records if r["position"] > root["context_through"]]}

    def save_context(self, scope, owner, text, through, expected_generation):
        table, key = ("interaction_trajectories", "interaction_id") if scope == "interaction" else ("session_trajectories", "session_id")
        sid = self.row("SELECT session_id FROM interactions WHERE id=?", (owner,))["session_id"] if scope == "interaction" else owner
        with self.transaction():
            if self.generation(sid) == expected_generation:
                self.db.execute(f"UPDATE {table} SET context=?,context_through=? WHERE {key}=?", (text, through, owner))

    def trajectory_session(self, scope, owner):
        return self.row("SELECT session_id FROM interactions WHERE id=?", (owner,))["session_id"] if scope == "interaction" else owner

    def narration_candidate(self, sid):
        return self.row("SELECT b.*,i.session_id,i.request,i.ordinal AS interaction_order FROM batches b "
                        "JOIN interactions i ON i.id=b.interaction_id JOIN interaction_records r ON r.batch_id=b.id "
                        "LEFT JOIN narrations n ON n.batch_id=b.id WHERE i.session_id=? AND n.id IS NULL "
                        "AND i.ordinal=(SELECT max(ordinal) FROM interactions WHERE session_id=i.session_id) "
                        "AND b.ordinal=(SELECT max(ordinal) FROM batches WHERE interaction_id=i.id) "
                        "ORDER BY i.ordinal DESC,b.ordinal DESC LIMIT 1", (sid,))

    def record_narration(self, bid, text, status, now):
        batch = self.row("SELECT i.session_id FROM batches b JOIN interactions i ON i.id=b.interaction_id WHERE b.id=?", (bid,))
        with self.transaction():
            self.db.execute("UPDATE narrations SET status='superseded',finished=? WHERE status='pending' AND batch_id IN "
                            "(SELECT b.id FROM batches b JOIN interactions i ON i.id=b.interaction_id WHERE i.session_id=?)",
                            (now, batch["session_id"]))
            through = self.row("SELECT coalesce(max(interaction_id),0) AS n FROM session_records WHERE trajectory_id=?", (batch["session_id"],))["n"]
            self.db.execute("INSERT OR IGNORE INTO narrations(batch_id,text,status,created,session_through) VALUES(?,?,?,?,?)",
                            (bid, text, status, now, through))
            # Older summarized batches have been considered in this trajectory view.
            self.db.execute("INSERT OR IGNORE INTO narrations(batch_id,text,status,created) "
                            "SELECT b.id,'','superseded',? FROM batches b JOIN interactions i ON i.id=b.interaction_id "
                            "JOIN interaction_records r ON r.batch_id=b.id WHERE i.session_id=? AND b.id<?",
                            (now, batch["session_id"], bid))

    def delivered(self, sid):
        return [r["text"] for r in self.rows("SELECT n.text FROM narrations n JOIN batches b ON b.id=n.batch_id "
                                            "JOIN interactions i ON i.id=b.interaction_id WHERE i.session_id=? AND n.status='completed' "
                                            "ORDER BY n.id DESC LIMIT 5", (sid,))][::-1]

    def already_delivered(self, sid, text):
        return bool(self.row("SELECT n.id FROM narrations n JOIN batches b ON b.id=n.batch_id "
                             "JOIN interactions i ON i.id=b.interaction_id WHERE i.session_id=? "
                             "AND n.status='completed' AND lower(trim(n.text))=lower(trim(?)) LIMIT 1", (sid, text)))

    def generation(self, sid):
        return self.row("SELECT coalesce(max(id),0) AS n FROM events WHERE session_id=?", (sid,))["n"]

    def session(self, sid):
        return self.row("SELECT * FROM sessions WHERE id=?", (sid,))

    def batch_failed(self, bid):
        self.db.execute("UPDATE batches SET attempts=attempts+1,error='Summary generation failed' WHERE id=?", (bid,))

    def waiting(self, sid):
        return self.next_batch(sid) is not None or self.next_rollup(sid) is not None

    def next_delivery(self):
        return self.row("SELECT n.*,i.session_id,i.id AS interaction_id,i.ordinal AS interaction_order,b.urgent "
                        "FROM narrations n JOIN batches b ON b.id=n.batch_id JOIN interactions i ON i.id=b.interaction_id "
                        "WHERE n.status='pending' ORDER BY b.urgent DESC,n.id LIMIT 1")

    def delivery_current(self, item):
        last = self.row("SELECT max(ordinal) AS n FROM interactions WHERE session_id=?", (item["session_id"],))["n"]
        batch = self.row("SELECT max(id) AS n FROM batches WHERE interaction_id=?", (item["interaction_id"],))["n"]
        return last == item["interaction_order"] and batch == item["batch_id"]

    def delivery_status(self, nid, status, now):
        self.db.execute("UPDATE narrations SET status=?,finished=? WHERE id=?", (status, now, nid))

    def recover_delivery(self, now):
        # Called only after acquiring the exclusive speaker lock. No old speaker can still own it.
        self.db.execute("UPDATE narrations SET status='uncertain',finished=? WHERE status='playing'", (now,))

    def last_delivery(self):
        return self.row("SELECT coalesce(max(finished),0) AS t FROM narrations WHERE status='completed'")["t"]

    def pending_delivery_generation(self):
        return self.row("SELECT coalesce(max(id),0) AS n FROM narrations WHERE status='pending'")["n"]

    def prune(self, now=None):
        now = time.time() if now is None else now
        self.db.execute("DELETE FROM sessions WHERE updated<?", (now - 7 * 86400,))

    def limit_payloads(self, sid, limit=32 * 1024 * 1024):
        """Bound retained raw text; preserve records and mark missing evidence."""
        with self.transaction():
            total = self.row("SELECT coalesce(sum(length(cast(payload AS blob))+length(cast(evidence AS blob))),0) AS n "
                             "FROM events WHERE session_id=?", (sid,))["n"]
            if total <= limit:
                return
            marker = '{"evicted":true,"reason":"session text storage limit"}'
            for row in self.rows("SELECT id,length(cast(payload AS blob))+length(cast(evidence AS blob)) AS bytes "
                                 "FROM events WHERE session_id=? ORDER BY id", (sid,)):
                if row["bytes"] <= len(marker) * 2:
                    continue
                self.db.execute("UPDATE events SET payload=?,evidence=? WHERE id=?", (marker, marker, row["id"]))
                total -= row["bytes"] - len(marker) * 2
                if total <= limit:
                    break

    def export(self, sid):
        """Inspectable replay output without importing a provider or audio."""
        return {"session": self.row("SELECT * FROM sessions WHERE id=?", (sid,)),
                "interactions": self.rows("SELECT * FROM interactions WHERE session_id=? ORDER BY ordinal", (sid,)),
                "events": self.rows("SELECT * FROM events WHERE session_id=? ORDER BY id", (sid,)),
                "interaction_records": self.rows("SELECT r.* FROM interaction_records r JOIN interactions i ON i.id=r.trajectory_id "
                                                 "WHERE i.session_id=? ORDER BY i.ordinal,r.batch_id", (sid,)),
                "session_records": self.rows("SELECT * FROM session_records WHERE trajectory_id=? ORDER BY interaction_id", (sid,)),
                "narrations": self.rows("SELECT n.* FROM narrations n JOIN batches b ON b.id=n.batch_id "
                                        "JOIN interactions i ON i.id=b.interaction_id WHERE i.session_id=? ORDER BY n.id", (sid,))}
