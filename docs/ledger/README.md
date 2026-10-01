# Ledger (one file per entry)

Decisions and hard calls: what changed, why, who, and where things stand. Any
agent or human can read the newest entries and pick up the work without asking.

**One file per entry**, in this directory, named `YYYY-MM-DD-HHMM-<slug>.md`.
New files never conflict, which matters here because chess-lab work lands as
stacked PRs that are open at the same time. `docs/LEDGER.md` is frozen: it
keeps the history up to the switch and is never edited again. Every entry it
held was also converted into a file here, so this directory is the complete
record.

## Writing an entry

```powershell
node scripts/ledger.mjs new "Short title of the change"
```

That creates the file with the current local time and an empty template. Fill in:

```
# YYYY-MM-DD HH:MM TZ - <short title>
- **Who:** <Drew / Council / agent session; add "technical" for agent technical calls>
- **Change:** <what changed, concretely>
- **Why:** <the reason; for hard calls, the alternative and why it lost>
- **State after:** <what is true now; what is still open>
- **Refs:** <PRs, commits, receipts, files>
```

## Rules

- **Append only.** Never edit or delete an entry. To correct one, add a new
  entry whose **Why** starts `Supersedes <file name>` and explains the
  correction.
- **Every number is receipted**: name the `receipts/` path.
- **Absolute dates and times** with a time zone. The file name's date and time
  must match the heading's.
- No em dashes.

Converted entries carry the date from their `docs/LEDGER.md` heading and the
author time of the commit that added them, because the single-file ledger
recorded dates only. Entries from one commit share a minute, so `print` orders
them by slug within that minute; the frozen `docs/LEDGER.md` keeps their
original order.

`.github/workflows/ledger.yml` runs `node scripts/ledger.mjs check` on every
pull request and on push to `main`, so a malformed entry fails CI.

## Reading

```powershell
node scripts/ledger.mjs print        # every entry, oldest first
```

There is no committed index on purpose: a generated index file would conflict
the same way a single ledger file does.
