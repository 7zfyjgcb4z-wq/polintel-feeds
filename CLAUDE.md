# Claude guidance for polintel-feeds

This file records the things that must not be repeated in every prompt: feed-level invariants, scope boundaries, and the vault contract. Assume all of this is already true; do not re-derive it.

## Invariants

- Every source terminates by emitting normalised RSS 2.0 XML into `feeds/`. **Never write to Supabase or to a local database as a terminal step.** This deviation has been introduced twice and reverted twice. `[VERIFY]`
- Feed schema: organisation in `dc:creator` with `<author>` as fallback, ignored if the value looks like an email address; `date_posted` maps to `pubDate` with timezone handling; `category` carries the feed label, not the location; location in a `polintel:location` extension element with the namespace declared on the `<rss>` root; description clipped to 2,000 characters. `[VERIFY]`
- **The item URL a source emits is its identity downstream**, where a unique constraint enforces it. Changing URL construction duplicates every live posting from that source. Do not change it without flagging. Verified against the live database 2026-08-17.
- Politeness is not optional. Honour robots.txt and any declared `Crawl-delay` per host. A 2 second default against a declared 600 second delay is a breach, and it has happened.
- Detection-first, AI-last. Try known ATS platforms and structured data before any inference.
- Disabling a source requires a `notes` field recording the reason and the date. 125 of 210 currently disabled sources have no recorded reason and every audit pays for that. `[VERIFY]`
- No user-agent rotation, header spoofing, or challenge solving, on any source, ever.
- Compliance stubs stay stubs. Civil Service Jobs is ALTCHA-gated by ruling, and sources excluded on terms-of-service grounds are not to be revisited technically.

## Scope of this repo

This repo produces feed files. It does not own the Supabase schema, the classification rules, or the frontend. Make no claim about them here; the frontend repo's `CLAUDE.md` holds the jobs-table invariants.

## Knowledge vault

The Pol-Intel Obsidian vault is the durable cross-session context layer. Read the relevant feeds notes at the start of a session and update them at the end. Live table state and live code always beat a vault claim: the vault is a map, not the territory. Record anything unconfirmed as `[VERIFY]` rather than as fact.
