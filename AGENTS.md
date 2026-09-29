# Dr Drama

## Purpose

Dr Drama is a personalized K-drama recommendation application. Users will record watched dramas, ratings, and preferences. The system will analyze that history, recommend unwatched dramas, and eventually estimate how likely a user is to enjoy each recommendation.

Potential signals include genres, release year, cast, episode count, public ratings, themes/tags, similarity to previously liked dramas, and personal viewing history. Choose and evaluate capabilities based on their usefulness, reliability, and maintainability.

## Current development phase

The project is in Phase 2: simple recommendation baselines and retrospective evaluation. Architecture choices below are planned unless implemented and verified in the repository; do not assume services or credentials already exist.

Repository foundation is implemented: package configuration, local environment, initial EDA notebook, and data-quality checks. The temporary MyDramaList adapter and interactive metadata preview/CSV save flow are implemented. Reproducible Excel import is implemented for existing personal history; prioritize it over a dedicated manual-entry interface. Database integration remains pending.

Current scope:

1. Establish a clean, documented repository.
2. Define the watch-history, preference, and metadata schemas.
3. Build and validate metadata retrieval.
4. Import and preserve existing personal ratings and preferences from Excel.
5. Begin exploratory data analysis (EDA).
6. Maintain a provisional candidate catalog, public-quality and content-similarity baselines, and leakage-aware retrospective evaluation. See `docs/baseline_recommender.md`. Supervised probability prediction and agents remain future work.

Limit Phase 2 to simple ranking baselines and evaluation unless the user explicitly expands the scope. Do not add an AI agent, RAG system, web application, or probability prediction model yet. Preserve existing work and Git history. Keep these instructions updated when architectural decisions or development phases change.

## Long-term architecture

### Data and storage

- Python is the primary language for ingestion, transformation, analysis, machine learning, and recommendation logic.
- Supabase PostgreSQL is the planned SQL database, replacing the earlier SQLite proposal. Keep schema changes in versioned SQL migrations.
- Replace the temporary adapter with the official MyDramaList API when official developer access becomes available, retaining the normalized schema.
- MyDramaList is the preferred metadata source. The initial candidate provider is the unofficial scraper project at https://github.com/B1PL0B/MyDramaList-Unofficial-API. Its demo at https://my-drama-list-api-ten.vercel.app was successfully tested for search, details, and cast during planning; this does not guarantee future availability or complete data.
- The provider's documentation requests a separate deployment for ongoing personal use. Do not assume that deployment has been created. Keep the provider base URL configurable and document its unofficial status.
- Isolate provider-specific requests and parsing behind a small adapter so another provider or file import can be added without rewriting analysis or watch-history logic.
- Use stable internal drama IDs and retain source IDs, source URLs, and retrieval timestamps. Label public ratings by source.
- Separate shared drama metadata from user-specific watch history, ratings, notes, and preferences. Metadata refreshes must never overwrite personal entries.
- Represent genres, cast, and keywords through related tables where appropriate. Keep provider tags separate from personal reactions.
- Treat missing values as unknown, not zero or dislike. Preserve unrated and dropped statuses without automatically assigning negative labels.
- The initial CSV contract uses `my_rating` (1–10 in 0.1 increments) and statuses `completed`, `dropped`, `unfinished`, and `watching`. Viewing and feedback dates are not collected. See `docs/watch_history_schema.md`. CSV is the current collection format; Supabase remains planned.
- Start with one user's record per series. Add season-specific ratings, detailed rewatch events, or additional user flows only when needed.
- Preserve reproducible analysis snapshots with provenance. Do not make historical experiments silently depend on changing live metadata.

### Data science and recommendations

Follow a reproducible data science pipeline:

1. Define the question, prediction target, and meaning of "like."
2. Collect data and validate its quality.
3. Clean and transform data.
4. Explore distributions, missingness, sample sizes, and relationships.
5. Engineer features from information available at prediction time.
6. Establish simple recommendation and prediction baselines.
7. Train models only when data and a concrete question justify them.
8. Evaluate on withheld outcomes and document limitations.
9. Serve recommendations and collect subsequent user feedback.

- Maintain an unwatched candidate catalog; watched titles alone cannot provide new recommendations.
- Start with explicit filters and content-based ranking before more complex methods. Collaborative filtering requires cross-user behavior that a single personal history does not provide.
- Exclude watched titles and enforce the user's explicit constraints in application logic.
- Keep ranking scores, predicted ratings, and probabilities distinct. Do not present similarity or an arbitrary match score as a probability of enjoyment.
- Evaluate probability calibration before claiming reliable enjoyment probabilities. Be candid about uncertainty with a small dataset.
- Prevent data leakage: fit transformations and build preference/similarity features using training information only. Prefer chronological evaluation when reliable viewing dates exist.
- Evaluate ranking quality, prediction quality, and probability calibration as appropriate. Compare against simple baselines.
- Distinguish descriptive associations from causal conclusions. Report group sample sizes and overlapping genre membership in EDA.
- Train and evaluate models separately from conversational requests; version model artifacts and evaluation results.

### Agent, MCP tools, and RAG

- Plan for one orchestration agent that interprets natural-language requests, chooses tools, and combines their results. Multiple agents are not required by this architecture.
- Expose tested application functions through a Dr Drama Model Context Protocol (MCP) server when the agent phase begins. Ordinary Python functions are not MCP tools until actually exposed through that interface.
- The agent application hosts an MCP client that connects to the server. MCP standardizes tool discovery and invocation; it is not the recommendation algorithm or orchestration policy.
- Planned tools include history retrieval, preference retrieval, metadata search, recommendation ranking, enjoyment prediction, and evidence retrieval.
- The recommendation/model code calculates rankings and predictions. The language model must not invent numerical predictions.
- Use retrieval-augmented generation (RAG) to ground explanations in relevant drama metadata, descriptions, and user notes, with source references. RAG is not a substitute for a recommendation model.
- Consider embeddings for semantic retrieval only after establishing a simpler keyword/tag baseline. Supabase pgvector is a future option, not an initial requirement.
- Separate retrieved narrative context from actual model explanations. Do not claim a feature drove a prediction unless supported by the model or ranking logic.
- Evaluate retrieval relevance and agent tool selection, constraint compliance, and factual grounding separately from model performance.
- Add a simple web interface later. Keep personal data scoped to the current user; use appropriate authorization and Supabase row-level security before exposing user data through a client.

## Code organization and conventions

- Prefer small, modular, readable functions with explicit inputs and outputs. Use descriptive names and straightforward control flow.
- Use type hints where they clarify interfaces and data structures. Write docstrings for important functions, including non-obvious assumptions and failure behavior.
- Keep reusable logic in importable Python modules. Notebooks should call those modules and explain experiments rather than duplicate production logic.
- Keep network access, database access, transformations, recommendation logic, and presentation separate so they can be tested independently.
- Maintain clear boundaries between raw data, processed data, analysis, ML, agents, and application code. A suitable evolving layout is:

```text
data/raw/                 # Original responses/imports; normally ignored by Git
data/processed/           # Cleaned datasets/snapshots; normally ignored by Git
data/examples/            # Small synthetic examples safe to publish
src/dr_drama/tools/       # Provider adapters and application tools
src/dr_drama/data/        # Validation, transformations, persistence
src/dr_drama/analysis/    # Reusable exploratory analysis
src/dr_drama/models/          # Future features, training, prediction, evaluation
src/dr_drama/recommendations/ # Future candidate filtering and ranking
src/dr_drama/agents/      # Future orchestration and MCP integration
src/dr_drama/retrieval/   # Future evidence retrieval for RAG
src/dr_drama/app/         # CLI initially; web application later
notebooks/               # EDA and documented experiments
supabase/migrations/     # Versioned database schema changes
tests/                   # Meaningful automated behavior checks
docs/                    # Architecture, data dictionary, operational guides
reports/                 # Shareable findings and figures
```

- This layout describes boundaries, not a requirement to create empty future modules. Adapt names to the actual repository without unnecessary churn.
- Validate external data at boundaries. Handle absent fields, malformed values, ambiguous title matches, and duplicates explicitly.
- Use request timeouts and bounded retries for transient failures; avoid aggressive repeated requests. Store fetched metadata locally in the data layer rather than refetching during every analysis.
- Keep database operations explicit and parameterized. Avoid coupling the agent to unrestricted SQL execution.

## Secrets, privacy, and configuration

- Read API keys, database credentials, and service configuration from environment variables.
- Provide an `.env.example` containing placeholders only. Ignore real `.env` files and credentials in Git.
- Never commit secrets, include them in logs, or expose privileged Supabase credentials to a browser or language-model prompt.
- Keep personal viewing history and notes out of Git by default. Use synthetic examples in the public repository; only publish real personal data with explicit user authorization.
- Do not silently upload personal notes or history to an external AI service. Make the intended data flow clear when implementing that integration.

## Testing and reproducibility

- Test important transformation and API logic: type conversion, missing fields, response parsing, error handling, duplicate imports, and protection of personal ratings during metadata refresh.
- Use fixtures or mocked responses for routine API tests so tests do not depend on service availability or issue unnecessary requests. Keep optional live integration checks separate.
- Test database constraints and recommendation exclusions when those capabilities are introduced.
- Add meaningful tests for important behavior, not tests that merely mirror implementation or inflate coverage.
- Document setup, required configuration, commands, data sources, and limitations. Record dependencies and experiment settings sufficiently to reproduce results.

## Documentation

Keep tracked documentation focused on product behavior, setup, architecture, data contracts, operations, and limitations. Comments and docstrings should describe implementation behavior and non-obvious constraints.

Keep personal tutorials and explanatory notes in `docs/private/`, which must remain in `.gitignore`. If `docs/private/README.md` exists, read it for local communication preferences. Do not commit files from this folder.

## Scope and complexity

- Avoid unnecessary complexity. Do not add frameworks just because they are popular.
- Prefer ordinary Python functions, SQL, and a small dependency set until a demonstrated need justifies more infrastructure.
- Do not add deep learning, vector infrastructure, agent frameworks, multiple services, or a full frontend simply to satisfy a technology checklist.
- Keep the long-term architecture in view while implementing only the authorized phase. Clearly distinguish proposed, implemented, and verified capabilities in documentation and explanations.
