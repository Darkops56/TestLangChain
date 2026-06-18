## Context

The Graphify graph maps 4,765 nodes across 309 communities, but no document translates the static graph into runtime data flows. Developers must read source files across 3 stacks (Python agent, C# backend, Angular frontend) to understand how a request propagates. The graph identifies god nodes (RadarReport, get_settings(), DotNetClient, MetaClient) as cross-community bridges, but their role as data routers is undocumented.

## Goals / Non-Goals

**Goals:**
- Document the 4-5 primary data pipelines visible in the graph (newsletter, social media, chat, AI Radar, agent workflows)
- Map each pipeline's path through communities with node-level detail
- Identify data transformations at community boundaries (where graph edges cross communities)
- Produce 10 structured questions to uncover undocumented flow behavior

**Non-Goals:**
- Not a replacement for reading source code
- Not an architectural decision record (ADR)
- Not a performance or latency analysis

## Decisions

1. **Mermaid flow diagrams** over ASCII art — renders natively on GitHub and embeds in Notion. Each pipeline gets a `flowchart LR` block with communities as nodes and key data-bearing edges as links.
2. **Pipeline-first organization** over community-first — readers care about "how does a newsletter get sent", not "what nodes are in community 20". Each pipeline section traces: trigger → routing → transformation → persistence → delivery.
3. **graphify query as source** — each pipeline section is backed by a `graphify path A B` or `graphify query` call to ensure accuracy. No manual edge listing.
4. **God nodes as section headers** — each cross-community bridge node (RadarReport, get_settings(), DotNetClient, MetaClient, CommunityManagerState) gets its own subsection explaining what data it carries and which communities it connects.

## Risks / Trade-offs

- [Stale graph] → Graph will evolve; mark doc with generation date and `graphify update .` refresh instructions
- [Oversimplification] → Mermaid flows hide edge weights and confidence scores; add inline confidence annotations for INFERRED edges
- [Missing runtime state] → Graph shows static structure; questions section captures runtime behavior the team knows but isn't in the code
