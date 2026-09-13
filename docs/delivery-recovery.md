# Delivery Recovery

Bark notifications use compact UTF-8 JSON capped at 4,000 bytes, with up to ten
article previews and a dated archive link. Feishu and the archive retain the full
selection.

If a notification fails, the workflow still commits generated pages and any
successful delivery checkpoint, deploys Pages, then reports the original failure.
This prevents a Bark error from replaying articles already delivered to Feishu.
A channel that fails is reported but is not retried separately after another
channel succeeds.

For a backlog that was already delivered but never checkpointed, manually run the
Shibei Digest workflow with `recovery_only=true`. This archives the backlog and
advances state without sending it again. The default is false; scheduled runs
continue to send only new articles with a minimum interval of 36 hours.

After recovery, a manual run with `force_run=true` and `recovery_only=false` checks
delivery. With no new articles, it sends an empty notification linking to the
most recent archive without replacing that archive with an empty page.

Use recovery only for an explicitly approved backlog: its selected articles will
not be sent on subsequent regular runs. Git commit and Pages service failures
still require investigation in Actions logs.
