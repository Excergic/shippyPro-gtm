# Sample data

`demo_accounts.json` holds five **synthetic** accounts for demo mode. The companies, people, articles, emails and LinkedIn URLs are invented. Domains use the reserved `.example` TLD, so nothing here refers to a real company or person.

Each row has the same fields the real pipeline produces: the public signal and source, the 5-part ICP fit breakdown, one contact, and the copy angle (opener, question, diagnostic, measure).

```sh
python3 src/outbound_engine.py serve --demo   # review dashboard on http://127.0.0.1:8765
python3 src/mcp_server.py --demo              # MCP tools over the same demo databases
```

Both commands build `results/demo/campaign.sqlite3` and `results/demo/leads.sqlite3`. `serve --demo` rebuilds them on every start.
