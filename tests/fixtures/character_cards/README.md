# Character Card import fixtures

These minimal fictional fixtures were hand-authored for LivingWorld tests from
the public V2/V3 specifications. They contain no community card content.
`example.invalid` addresses are inert references and never fetched.

[card_fixtures.py](../../card_fixtures.py) constructs tiny CRC-valid PNG/APNG
containers and deliberate malformed/duplicate payloads from these JSON files.
Tests add unknown fields, extensions, embedded books and asset descriptors
explicitly; no downloaded images or third-party application code are used.
`group_second.json` adds a distinct neutral contact for the real browser group
creation and world-isolation smoke.
