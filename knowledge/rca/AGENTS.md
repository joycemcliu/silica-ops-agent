# RCA Guideline

Run only when the user requests an RCA, and only after Phase B is finished.

The agent never posts to the escalation channel. It gives the developer each PM-required message in the DM, labeled and in its own fenced code block, so he can copy and paste it verbatim. Fill in only the `<placeholders>`. Give each message when its step is reached, because the PM reads them as live status.

## Flow

1. **Start.** Give: `I’m taking over the RCA.`
2. Finish the root cause analysis, reusing the confirmed findings from the diagnosis.
3. **Google Doc.** Call `create_rca_doc` with the name `<store/env name> <incident title>`. The folder is fixed by the server. Content: root cause findings (<PM's required sections, if any>).
4. Give: `RCA complete. Findings: <google doc url>.`
5. Give: `I’m starting the full store health check.`
6. **Health check.** Run <runbook/skill path>. Usually nothing is found, but the check must actually run.
7. **Notion ticket**, only if a long-term fix is needed (<criteria>). Call `create_followup_ticket` with a link back to the Google Doc.
8. Give one of:
   - With a ticket: `Store check complete. <brief result> Follow-up: <notion ticket link>`
   - Without a ticket: `Store check complete. <brief result>` (omit the `Follow-up` part entirely)
9. **Wrap up.** Repeat all messages in one code block for convenience, with the doc, ticket and PR links.

## Rules

- Fill in a link only after the tool returns it. The doc link must exist before step 4 and the ticket link before step 8.
- Never give a "complete" message before its step has succeeded. If a step failed or the health check could not run, say so in the DM and do not draft that message.
- `<brief result>` is one or two sentences and states only what the check actually showed.
- On a repeated request, update the existing doc and ticket instead of creating new ones.
