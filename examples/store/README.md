# Inspectable demo store

`supersede-demo.relate/` is a persistent Relate store in **directory mode**, built from the
fictional corpus in [`../corpus/`](../corpus/) (12 documents, 19 revisions, 34 facts; 65 nodes and
60 relationships). All data is invented.

Open it without changing it:

```python
import relate
conn = relate.connect("examples/store/supersede-demo.relate", read_only=True)
cur = conn.cursor()
cur.execute("MATCH (r:Rev) WHERE NOT (:Rev)-[:SUPERSEDES]->(r) RETURN r.id AS current ORDER BY current")
print(cur.fetchall())
```

Or serve it to an MCP client with Supersede (see the main README for the client config):

```bash
python -m supersede.mcp_server --db examples/store/supersede-demo.relate
```

Only one process can write to a store at a time; `read_only=True` opens it beside a running server.

Regenerate it from the corpus (the loader refuses an existing path, so delete it first):

```bash
python examples/load_corpus.py examples/store/supersede-demo.relate
```
