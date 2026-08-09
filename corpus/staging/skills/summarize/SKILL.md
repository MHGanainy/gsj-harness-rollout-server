# Skill: summarize

Produce a structured summary of the case as it stands in this checkout.

## Instructions

1. Establish the current state of the case from the pages in `md/`, using
   `mcp_gsj_search_case` before grep for content questions.
2. Structure the summary as: **Parties**, **Timeline**, **Key events**,
   **Open questions**.
3. Every claim cites its source page as `page:N`. A claim without a page
   citation is forbidden.
4. Separate facts from inferences per AGENTS.md; list inferences in their
   own subsection, each naming the cited facts it rests on.
5. Write the summary to `out/<task_id>.md`.
