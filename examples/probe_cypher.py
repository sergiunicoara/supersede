"""Probe which Cypher patterns Relate 1.2.0 supports for the Supersede design.

Each probe runs independently and reports PASS / FAIL with the first line of the
error, so we learn the real support surface instead of assuming Neo4j parity.
"""
import sys
import relate

print("relate paramstyle:", relate.paramstyle)

conn = relate.connect(":memory:")


def run(q, params=None):
    cur = conn.cursor()
    cur.execute(q, params) if params is not None else cur.execute(q)
    try:
        return cur.fetchall()
    except Exception:
        return None


SEED = [
    # documents (with authority level: higher = more authoritative)
    "CREATE (:Doc {id:'D1', title:'Final inspection procedure', authority:3, kind:'regulatory'})",
    "CREATE (:Doc {id:'D2', title:'Shift work instruction', authority:1, kind:'informal'})",
    # revisions
    "CREATE (:Rev {id:'D1-r1', doc:'D1', rev:1, effective:'2024-01-01'})",
    "CREATE (:Rev {id:'D1-r2', doc:'D1', rev:2, effective:'2025-03-01'})",
    "CREATE (:Rev {id:'D2-r1', doc:'D2', rev:1, effective:'2025-06-01'})",
    # facts asserted by revisions
    "CREATE (:Fact {fid:'F1', subject:'final_inspection', predicate:'sampling', value:'100%'})",
    "CREATE (:Fact {fid:'F2', subject:'final_inspection', predicate:'sampling', value:'AQL 1.0'})",
    "CREATE (:Fact {fid:'F3', subject:'final_inspection', predicate:'sampling', value:'AQL 1.0'})",
]
LINKS = [
    "MATCH (a:Rev {id:'D1-r2'}), (b:Rev {id:'D1-r1'}) CREATE (a)-[:SUPERSEDES]->(b)",
    "MATCH (d:Doc {id:'D1'}), (r:Rev) WHERE r.doc = d.id CREATE (d)-[:HAS_REV]->(r)",
    "MATCH (d:Doc {id:'D2'}), (r:Rev) WHERE r.doc = d.id CREATE (d)-[:HAS_REV]->(r)",
    "MATCH (r:Rev {id:'D1-r1'}), (f:Fact {fid:'F1'}) CREATE (r)-[:ASSERTS]->(f)",
    "MATCH (r:Rev {id:'D1-r2'}), (f:Fact {fid:'F2'}) CREATE (r)-[:ASSERTS]->(f)",
    "MATCH (r:Rev {id:'D2-r1'}), (f:Fact {fid:'F3'}) CREATE (r)-[:ASSERTS]->(f)",
]

PROBES = [
    ("create nodes", None),  # handled below
    ("current revision (NOT pattern)",
     "MATCH (r:Rev) WHERE NOT (:Rev)-[:SUPERSEDES]->(r) RETURN r.id AS id ORDER BY id", None),
    ("supersedes chain, var-length path",
     "MATCH p=(n:Rev)-[:SUPERSEDES*1..5]->(o:Rev) RETURN n.id AS newer, o.id AS older, length(p) AS hops", None),
    ("contradiction detection (self-join, <>)",
     "MATCH (a:Fact),(b:Fact) WHERE a.subject=b.subject AND a.predicate=b.predicate "
     "AND a.value<>b.value AND a.fid<b.fid RETURN a.fid AS a, b.fid AS b, a.value AS av, b.value AS bv", None),
    ("fact -> revision -> doc authority (3-hop)",
     "MATCH (d:Doc)-[:HAS_REV]->(r:Rev)-[:ASSERTS]->(f:Fact) "
     "RETURN f.fid AS fact, f.value AS value, r.id AS rev, d.authority AS authority ORDER BY authority DESC", None),
    ("parameterised query",
     "MATCH (f:Fact) WHERE f.subject = $s RETURN count(f) AS n", {"s": "final_inspection"}),
    ("aggregation with collect()",
     "MATCH (r:Rev)-[:ASSERTS]->(f:Fact) RETURN r.doc AS doc, collect(f.value) AS vals", None),
    ("OPTIONAL MATCH",
     "MATCH (r:Rev) OPTIONAL MATCH (r)-[:SUPERSEDES]->(o:Rev) RETURN r.id AS id, o.id AS supersedes ORDER BY id", None),
    ("EXISTS subquery",
     "MATCH (r:Rev) WHERE EXISTS { (r)-[:SUPERSEDES]->(:Rev) } RETURN r.id AS id", None),
    ("MERGE upsert",
     "MERGE (d:Doc {id:'D3'}) ON CREATE SET d.title='New', d.authority=2 RETURN d.id AS id", None),
    ("datetime() function",
     "RETURN datetime() IS NOT NULL AS ok", None),
    ("WITH + ORDER BY + LIMIT",
     "MATCH (r:Rev) WITH r ORDER BY r.rev DESC LIMIT 1 RETURN r.id AS id", None),
    ("labels()/type() introspection",
     "MATCH (a)-[x]->(b) RETURN DISTINCT labels(a)[0] AS a, type(x) AS rel, labels(b)[0] AS b ORDER BY rel", None),
]

results = []
# seed
try:
    for q in SEED + LINKS:
        run(q)
    conn.commit()
    results.append(("seed graph", "PASS", ""))
except Exception as e:
    results.append(("seed graph", "FAIL", str(e).splitlines()[0]))
    print("seed failed:", e)
    sys.exit(1)

for name, q, p in [x for x in PROBES if x[1] is not None] if False else []:
    pass

for item in PROBES[1:]:
    name, q, p = item
    try:
        rows = run(q, p)
        results.append((name, "PASS", repr(rows)[:140]))
    except Exception as e:
        results.append((name, "FAIL", str(e).splitlines()[0][:140]))

for name, status, detail in results:
    print(f"[{status}] {name}: {detail}")
