---
name: bootstrap-optimizer
description: Transform a natural language bootstrap.md project description into an optimized, structured instruction set ready for task list generation. Use this skill whenever the user mentions "bootstrap", "optimize bootstrap", "refine project description", "prepare project for task generation", or wants to turn a rough project idea into a well-defined specification. Also trigger when the user has a bootstrap.md file and wants to clarify requirements, fill in gaps, or make the description implementation-ready. This skill is the first step in a two-step pipeline — the output feeds into a task list generation skill.
---

# Bootstrap Optimizer

Transform a rough, natural language project description (`bootstrap.md`) into a comprehensive, optimized instruction set with all ambiguities resolved. This is step 1 of a 2-step pipeline — the optimized output feeds into a task list generation skill.

## Workflow

### 1. Locate and Read bootstrap.md

Look for the bootstrap file in this order:
1. `./bootstrap.md` (project root / current working directory)
2. `/mnt/user-data/uploads/bootstrap.md` (user uploads)

If not found, ask the user to provide or upload it.

Read the file completely. Parse out:
- **Project purpose** — what the project does and who it's for
- **Stated requirements** — anything explicitly mentioned
- **Implied requirements** — things referenced but not detailed
- **Gaps** — critical areas with no coverage at all

### 2. Assess Coverage

Before asking questions, evaluate which of these requirement domains are already covered in the bootstrap file and which need clarification:

| Domain | What to check |
|--------|--------------|
| **Technology Stack** | Languages, frameworks, libraries, databases, APIs |
| **Architecture** | Monolith vs microservices, frontend/backend split, data flow |
| **Security** | Authentication, authorization, data encryption, secrets management |
| **Deployment** | Hosting, CI/CD, environments, containerization, infrastructure-as-code |
| **Testing** | Unit, integration, e2e strategy, coverage targets, test frameworks |
| **Data** | Storage, migrations, backups, seed data, external data sources |
| **Integration** | Third-party services, APIs, webhooks, messaging |
| **Scalability** | Expected load, caching strategy, rate limiting, async processing |
| **Observability** | Logging, monitoring, alerting, error tracking |
| **Developer Experience** | Local setup, documentation, code style, linting |
| **Compliance & Constraints** | Licensing, regulatory, accessibility, browser support |

### 3. Ask Clarifying Questions

Present questions to the user organized by domain. Follow these rules:

- **Only ask about gaps.** If the bootstrap already specifies a technology stack in detail, don't re-ask about it.
- **Group questions by domain.** Present them in logical clusters, not a wall of 30 questions.
- **Prioritize high-impact gaps first.** Technology and architecture come before developer experience.
- **Offer sensible defaults.** For each question, suggest a reasonable default the user can accept or override.
- **Limit to 5-8 questions per round.** If there are many gaps, ask in rounds — resolve the most critical domains first, then move to secondary ones.
- **Never ask questions the bootstrap already answers.** Re-read the document before finalizing your question list.

#### Question Format

Use this format for each question:

```
**[Domain] — [Specific topic]**
[The question]
→ Default suggestion: [your recommended default based on the project context]
```

**Example:**
```
**Security — Authentication**
How should users authenticate? The bootstrap mentions user accounts but doesn't specify an auth mechanism.
→ Default suggestion: JWT-based auth with refresh tokens, using an established library (e.g., Passport.js for Node, or Django's built-in auth for Python)
```

#### Round Structure

**Round 1 — Critical foundations** (always ask):
- Technology stack gaps
- Architecture decisions
- Security requirements

**Round 2 — Operational requirements** (ask if gaps exist):
- Deployment & infrastructure
- Testing strategy
- Data management

**Round 3 — Quality & polish** (ask if gaps exist):
- Scalability & performance
- Observability
- Developer experience
- Compliance & constraints

After each round, wait for the user's answers before proceeding to the next round. Incorporate answers immediately into the working document.

### 4. Resolve Conflicts and Ambiguities

After gathering answers, check for:
- **Contradictions** — e.g., bootstrap says "simple SQLite database" but user wants "multi-region deployment"
- **Over-engineering** — requirements that seem excessive for the project scope
- **Under-specification** — areas still vague after questioning

Flag these to the user with a brief explanation and ask for resolution.

### 5. Generate Optimized Instructions

Once all gaps are resolved, produce the optimized instruction document. Write it to `./bootstrap-optimized.md`.

Use this exact structure:

```markdown
# [Project Name] — Optimized Project Specification

## Project Overview
[2-3 sentence summary of what the project does, who it's for, and core value proposition]

## Technology Stack
- **Language(s):** [specific versions]
- **Framework(s):** [with versions]
- **Database:** [type and version]
- **Key Libraries:** [list with purpose]
- **Package Manager:** [name]

## Architecture
[Describe the high-level architecture: components, how they communicate, data flow diagram in text form]

### Component Breakdown
[List each major component/service with a one-line description of its responsibility]

## Security Requirements
- **Authentication:** [mechanism and implementation approach]
- **Authorization:** [role/permission model]
- **Data Protection:** [encryption at rest/in transit, PII handling]
- **Secrets Management:** [approach for API keys, credentials]
- **Security Headers / CORS:** [policy]

## Deployment & Infrastructure
- **Hosting:** [platform/provider]
- **Environments:** [list: dev, staging, prod, etc.]
- **CI/CD:** [pipeline approach]
- **Containerization:** [Docker, etc. if applicable]
- **Domain / DNS:** [if applicable]

## Testing Strategy
- **Unit Tests:** [framework, coverage target]
- **Integration Tests:** [approach]
- **E2E Tests:** [framework, key flows to cover]
- **Test Data:** [seeding approach]

## Data Management
- **Primary Storage:** [database details]
- **Migrations:** [strategy and tooling]
- **Backups:** [approach and frequency]
- **Seed Data:** [what's needed for development]

## External Integrations
[List each third-party service/API with: purpose, auth method, key endpoints used]

## Scalability & Performance
- **Expected Load:** [users, requests/sec, data volume]
- **Caching:** [strategy if applicable]
- **Rate Limiting:** [approach if applicable]
- **Background Jobs:** [queue system if applicable]

## Observability
- **Logging:** [framework and approach]
- **Monitoring:** [tool and key metrics]
- **Error Tracking:** [service if applicable]
- **Alerting:** [key conditions]

## Developer Experience
- **Local Setup:** [key steps or tooling]
- **Code Style:** [linter, formatter, conventions]
- **Documentation:** [approach — inline, ADRs, wiki, etc.]

## Constraints & Compliance
- **Browser Support:** [if web]
- **Accessibility:** [standard — WCAG level if applicable]
- **Licensing:** [project license and dependency concerns]
- **Regulatory:** [GDPR, HIPAA, etc. if applicable]

## Key Decisions & Rationale
[List non-obvious decisions made during optimization and why — this helps the task list generator understand intent]

## Original Requirements Preserved
[Any specific requirements from the bootstrap that must not be altered or reinterpreted during task generation]
```

**Important rules for the optimized output:**
- Preserve the user's intent from the original bootstrap — never overwrite their stated preferences with defaults.
- Mark any sections where the user explicitly said "don't care" or "skip" as `[Deferred — not in scope for initial build]`.
- Keep language precise and implementation-oriented — avoid vague phrases like "should be scalable" in favor of "use Redis caching for session data with a 15-minute TTL".
- The document must be self-contained — a reader should understand the full project without needing the original bootstrap.md.

### 6. Present and Confirm

After generating the optimized document:
1. Save it to `./bootstrap-optimized.md`
2. Present a brief summary to the user highlighting:
   - Key decisions made
   - Defaults that were applied
   - Anything marked as deferred
3. Ask the user to review and confirm, or request changes
4. Iterate if needed until the user approves

Once approved, inform the user that the optimized specification is ready for the next step: task list generation.

## Edge Cases

**Bootstrap is just a one-liner:** Treat it as a seed idea. Ask all rounds of questions. The optimization adds maximum value here.

**Bootstrap is already very detailed:** Skip domains that are fully covered. Focus only on genuine gaps. The optimization may be mostly structural — reformatting into the standard template.

**User wants to skip questions:** Respect this. Apply sensible defaults for all gaps, clearly mark them as `[Default — not confirmed by user]`, and generate the output. Note: the user can always come back and refine.

**Multiple bootstrap files:** Ask the user which one to use, or if they should be merged.

**Bootstrap references external docs:** Ask the user to provide them or summarize the key points you need.
