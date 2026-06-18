## ADDED Requirements

### Requirement: Document newsletter data pipeline

The system SHALL produce a Mermaid flow diagram tracing the newsletter pipeline from trigger through draft generation, content creation, review, and publication. Each step SHALL map to its graph community and key nodes.

#### Scenario: Newsletter pipeline documented
- **WHEN** a reader views `docs/data-flow.md`
- **THEN** they see a flow with at least 5 stages: Community API Controller → LLM & AI Services → Writer Content Pipeline → Designer Module → Review Service → Newsletter Publisher

### Requirement: Document social media pipeline

The system SHALL produce a Mermaid flow diagram tracing the social media pipeline from incoming message through routing, content generation, platform-specific formatting, and platform delivery (Meta, TikTok).

#### Scenario: Social media pipeline documented
- **WHEN** a reader views `docs/data-flow.md`
- **THEN** they see the path from IncomingMessage through CommunityManagerState → Strategist → Designer → MetaClient / TikTokApiClient

### Requirement: Document AI Radar pipeline

The system SHALL produce a Mermaid flow diagram tracing the AI Radar report pipeline from research through benchmark data collection, insight extraction, slide generation, and multi-channel publication (PPTX, HTML, Google Slides).

#### Scenario: AI Radar pipeline documented
- **WHEN** a reader views `docs/data-flow.md`
- **THEN** they see the flow from Researcher → BenchmarkSnapshot → RadarInsight → RadarReport → NewsletterPPTXPublisher / GoogleSlidesRadarPublisher

### Requirement: Document god-node routing role

The system SHALL document each god node (RadarReport, get_settings(), DotNetClient, MetaClient, CommunityManagerState) with: which communities it connects, what data it carries, and whether it is a transformation point or passthrough.

#### Scenario: God nodes documented
- **WHEN** a reader views `docs/data-flow.md`
- **THEN** they see a section for each god node with its cross-community connections and data role

### Requirement: Include 10 context-gathering questions

The system SHALL include 10 structured questions at the end of `docs/data-flow.md` that surface undocumented flow behavior, runtime state, and edge cases the static graph cannot capture.

#### Scenario: Questions present
- **WHEN** a reader scrolls to the end of `docs/data-flow.md`
- **THEN** they see exactly 10 numbered questions about data flow gaps
