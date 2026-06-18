## 1. Data Collection

- [x] 1.1 Run `graphify query` for each pipeline: newsletter, social media, AI Radar, chat, agent workflows — capture node paths and community crossings
- [x] 1.2 Run `graphify path` between key god nodes (RadarReport, get_settings(), DotNetClient, MetaClient, CommunityManagerState) and their connected communities
- [x] 1.3 Collect community labels and membership counts from `.graphify_labels.json` and `GRAPH_REPORT.md`

## 2. Pipeline Documentation

- [x] 2.1 Write newsletter pipeline section with Mermaid flow from Community API Controller through Draft Models, Writer, Designer, Review Service to Publisher
- [x] 2.2 Write social media pipeline section with Mermaid flow from IncomingMessage through Strategist, Designer to MetaClient and TikTokApiClient
- [x] 2.3 Write AI Radar pipeline section with Mermaid flow from Researcher through BenchmarkSnapshot, RadarInsight, RadarReport to PPTX/HTML/Google Slides publishers
- [x] 2.4 Write chat pipeline section with Mermaid flow from ChatController through AzureAIChatService to response
- [x] 2.5 Write agent workflow pipeline section with Mermaid flow from CommunityManagerState through LangGraph publication graph nodes

## 3. God-Node Routing Analysis

- [x] 3.1 Document RadarReport: communities bridged, data role, transformation points
- [x] 3.2 Document get_settings(): communities bridged, configuration flow, dependency graph
- [x] 3.3 Document DotNetClient: Pipedrive integration path, data direction
- [x] 3.4 Document MetaClient: social platform routing, message flow
- [x] 3.5 Document CommunityManagerState: state machine transitions across nodes

## 4. Questions and Review

- [x] 4.1 Write 10 structured questions about missing flow context, runtime behavior, and edge cases
- [x] 4.2 Compile all sections into `docs/data-flow.md`
- [x] 4.3 Verify all Mermaid diagrams render correctly
- [x] 4.4 Add generation timestamp and instructions to refresh from graph
