# Local campaign inputs

The public repository includes ShippyPro scoring settings, the offer/cadence, and empty configuration examples. Real account manifests, reviewed people, individually authored message angles and provider receipts remain private and are not published.

For a fresh checkout, start the signal configuration with:

```sh
cp config/signal_first.example.json config/signal_first.json
```

Restore the private `results/signal_first_v3/` source/profile/receipt artifacts, `config/outbound/angles.tsv`, and the existing SQLite files from your local workspace or private backup before rebuilding the saved campaign. The examples do not generate prospects. Earlier ICP/intent experiment scripts also require their own private manifests; their `.example.json` files describe empty starting structures only.

The regression tests depend on saved research artifacts and the original audit database. They run in the full local workspace, not a source-only checkout without those fixtures. Never commit the live databases or contact exports to this public repository.
