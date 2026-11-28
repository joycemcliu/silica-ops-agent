# RCA Guideline

Run only when the user requests an RCA, and only after Phase B is finished.

The agent never posts to the escalation channel. It gives the developer each PM-required message in the DM, labeled and in its own fenced code block, so he can copy and paste it verbatim. Fill in only the `<placeholders>`. Give each message when its step is reached, because the PM reads them as live status.

## Flow

1. **Start.** Give: `I’m taking over the RCA.`
2. Finish the root cause analysis, reusing the confirmed findings from the diagnosis.
3. **RCA report.** Show the draft for review and obtain approval to save it. Call `google_drive_rca.create_rca_doc` with the original escalation's root Slack timestamp as `slack_thread_id`. Supply the store code, store or environment name if different, and a readable incident title based on the incident record in `knowledge/incidents/`. If the tool returns a `url`, use it for step 4. If it returns `action: local_draft`, give the user the path on the MCP host and pause the publishing workflow at this step.
4. Give: `RCA complete. Findings: <google doc url>.`
5. Give: `I’m starting the full store health check.`
6. **Health check.** Run <runbook/skill path>. Usually nothing is found, but the check must actually run.
7. **Notion ticket**, only if a long-term fix is needed (<criteria>). Call `create_followup_ticket` with a link back to the Google Doc.
8. Give one of:
   - With a ticket: `Store check complete. <brief result> Follow-up: <notion ticket link>`
   - Without a ticket: `Store check complete. <brief result>` (omit the `Follow-up` part entirely)
9. **Wrap up.** Repeat all messages in one code block for convenience, with the doc, ticket and PR links.

## RCA report content

- Use the UTC incident date, known affected session IDs, severity (`SEV1`, `SEV2`, or `SEV3`), and status (`Resolved`, `Mitigated`, or `Monitoring`). The tool writes `N/A` for duration and for an empty session list.
- In **Summary and impact**, cover what happened, who was affected, and the current state in three to five plain-language sentences. Keep internal service names in **Root cause**, along with the trigger, underlying cause, detection gap, and relevant versions and configuration. Label suspected causes and evidence gaps.
- In **Recovery**, record the action, verification, and what the Technical Supporter should do if it recurs. Leave the section empty in the input when there was no recovery action. List any **Follow-up** actions with owners, due dates, and ticket links where known. The tool writes `N/A` when no recovery or follow-up is supplied.
- In **Incident timeline**, give the first evidence, detection (who or which alert), mitigation, and resolution. Include a timezone offset or `Z` for known timestamps. The tool converts them to UTC and writes `N/A` for unknown timestamps.

## Rules

- Confirm the Google Doc link before step 4 and the ticket link before step 8.
- Never give a "complete" message before its step has succeeded. If a step failed or the health check could not run, say so in the DM and do not draft that message.
- `<brief result>` is one or two sentences and states only what the check actually showed.
- To revise a local draft, reuse the same `slack_thread_id` with `replace_existing=true` after approval. If the user later wants a Drive copy, obtain approval and omit `replace_existing` for the first Drive publication.
- On a repeated request, update the existing doc and ticket. For a doc created by this tool, show the complete revised draft for approval and call `create_rca_doc` with the same `slack_thread_id` and `replace_existing=true`. Include any edits already made in Drive that should be kept because this replaces the full report body. Without that flag, the tool returns its matching doc without writing. If the original doc predates the tool, reuse its link and ask for permission to update it through the configured Google Docs editor.
