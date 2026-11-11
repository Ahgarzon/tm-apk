# Synthetic SQL context diagnostic

**Draft, not executed.** The workflow is an inert `.example` template because
the current CLI OAuth grant lacks `workflow`. Do not activate it through another
credential or code path. Complete the official scope refresh, revalidate source,
public visibility/free runner/history/QA reservation, then install the reviewed
workflow and run it once. No source or unit test proves a real SQL outcome.

Manual diagnostic on the standard `windows-2022` runner of this public repository.
GitHub documents standard hosted runners as free for public repositories:
https://docs.github.com/en/actions/concepts/billing-and-usage

The controller must verify public visibility, owner, current reviewed SHA,
no active/duplicate run and the QA reservation before dispatch. Journal the
32-hex nonce before the POST; reconcile an uncertain POST by its run name.
Inputs cannot select scripts, databases, hosts, credentials or engine downloads.
No artifacts/cache are uploaded, no secrets or private product source are loaded,
and no Android builder/distribution/store workflow is changed.

Only a newly named LocalDB instance and four empty synthetic databases on that
ephemeral VM are used. The matrix compares MULTI_USER/RESTRICTED_USER and a
SELECT-only WITHOUT LOGIN principal with/without a requested explicit CONNECT.
Cases record the actual failing phase and SQL number/state/class. A completed
matrix is a diagnostic receipt; successful application access is not required.
No db_owner/CONTROL/guest/TRUSTWORTHY grants or restored data are involved.
Preinstalled major 15 is preferred, otherwise 16 is recorded; a different build
does not reproduce the exact restored LocalDB of another host.

Start/phase guards remain 3072/2048 MiB, disk 2304 MiB. The new own instance is
capped at 256 MiB/MAXDOP1 and monitored at 768 MiB RSS/1100 MiB host margin/90s.
Databases are dropped by exact owned identifiers and the instance is stopped;
no recursive filesystem deletion or unrelated instance/service action occurs.
Missing software/capacity or incomplete cleanup fails the workflow.

This does **not** accept SQL schemas/adapters, Node/TLS, original rows, the local
restored copy, Firebase, the backend, parity, an IPA or TestFlight. Keep their
gates pending. Reversal is a selective revert of these diagnostic files; retain
past receipts. Do not re-run the same source/matrix without an explicit cause.
