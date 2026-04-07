# QuantumPools — Competitive Research (March 2026)

## Market Landscape

### Pool-Specific Software
| Platform | Strength | Weakness | Pricing |
|---|---|---|---|
| **Skimmer** | Market leader, Orenda LSI, LaMotte integration, Sunbit financing, best service emails | No profitability analysis, no AI, limited reporting on lower tiers | $1-3/location/mo (min $49) |
| **Pool Brain** | Best profitability reports, tech scorecards, open API, guided workflows | Smaller market share, no financing, no marketing tools | $60/mo + $10/admin, all features |
| **Pool Office Manager** | Inventory with barcode, e-signatures, GPS tracking, good scheduling | Less modern UI, pricing not transparent | Demo required |
| **PoolCarePRO** | Route profit reports, tech pay calc, guided workflows | Older platform, limited integrations | $39.95-99.95/mo |
| **Pool Shark H2O** | Tamper-proof electronic logs, health dept compliance, commercial focus | Narrow scope — compliance only, not full business management | Not listed |

### General FSM (Pool-Capable)
| Platform | Strength | Weakness | Pricing |
|---|---|---|---|
| **ServiceTitan** | Most sophisticated overall, real-time job costing, marketing attribution | $245-500/tech/mo + $5-50K implementation, no pool chemistry | Enterprise only |
| **Jobber** | AI Copilot, marketing suite, website builder, Google review requests | No pool-specific features (chemistry, equipment) | $39-199/mo |
| **Housecall Pro** | AI voice receptionist, Instapay, good proposals | Limited reporting, no pool chemistry | $59-189/mo |
| **FieldPulse** | Fleet tracking with dashcam, AI voice/chat, dynamic proposals | Not pool-specific, newer/smaller | $89/mo + fleet add-ons |
| **Service Fusion** | SOC 2 compliant, advanced route optimization (traffic/weather), unlimited users | Being acquired/consolidated, no pool features | Custom pricing |

## Table Stakes (every competitor has these)
1. Customer/property management
2. Scheduling with calendar views
3. Route optimization
4. Mobile app (iOS + Android)
5. Invoicing and billing
6. Payment processing (credit card minimum)
7. QuickBooks integration
8. Photo documentation
9. Proposals/estimates
10. Basic reporting/analytics
11. GPS tracking (at least basic)

## Features Only 1-2 Platforms Have
| Feature | Who | Our Plan |
|---|---|---|
| Consumer financing (Sunbit/GreenSky) | Skimmer, ServiceTitan | Phase 10 (nice to have) |
| LaMotte Spin Touch | Skimmer, Pool Brain | Phase 10 (nice to have) |
| Orenda LSI with dosing | Skimmer | Phase 3d (critical — our Chemistry Advisor AI is better) |
| AI voice receptionist | Jobber, HCP, FieldPulse | Phase 10 |
| Guided mandatory workflows | Pool Brain, PoolCarePRO | Phase 3d (critical) |
| Filter/salt auto-scheduling | Pool Brain, PoolCarePRO | Phase 3d (critical) |
| Tech scorecards | Pool Brain, PoolCarePRO | Phase 9 (recommended) |
| Fleet tracking with dashcam | FieldPulse | Phase 10 |
| Tamper-proof electronic logs | Pool Shark H2O | Phase 5 (via Compliance Advisor) |
| Good-better-best proposals | ServiceTitan, Jobber, HCP, FieldPulse | Phase 9 (recommended) |
| Google review auto-requests | Jobber | Phase 9 (recommended) |
| Open API | Pool Brain, Jobber | Phase 10 |

## Features NO Competitor Has (Our Differentiators)

> **Status key:** BUILT = in production, PARTIAL = foundation exists, PLANNED = in roadmap

1. **AI-powered profitability analysis** with pricing recommendations — **BUILT** (profitability service + dashboard)
2. **Satellite pool/vegetation detection** from imagery — **BUILT** (Claude Vision 2-pass, per-WF)
3. **Inspection intelligence** (Pool Scout) — **BUILT** (scraper, PDF extractor, 908 facilities)
4. **Jurisdiction-aware bather load calculator** with estimation chain — **BUILT** (10 jurisdictions seeded)
5. **Account health scoring** with churn prediction — **PLANNED** (Customer Intelligence agent, Phase 9-10)
6. **AI Chemistry Advisor** (explains WHY, not just what dose) — **PARTIAL** (dosing engine exists, DeepBlue has dosing tool)
7. **AI Service Narrator** (customer-facing reports written by AI, not templates) — **PLANNED** (Phase 3c)
8. **Predictive equipment failure** — **PLANNED** (Equipment Oracle agent, Phase 9)
9. **Route strategy AI** (which stops on which routes, not just stop order) — **PARTIAL** (OR-Tools VRP built, no AI strategy layer)
10. **Automated property assessment from satellite imagery** — **BUILT** (satellite + difficulty scoring)
11. **Price increase impact modeling** — **PLANNED** (Phase 10)
12. **Whale curve profitability visualization** — **BUILT** (Recharts whale curve on profitability dashboard)

## Key Customer Pain Points (from forums, reviews, industry publications)

### Most Frequently Cited (address these first)
- **Don't know true cost per account** — most underestimate by 30-60% (→ Profitability Analyst)
- **Underpriced accounts** — afraid to raise rates, don't know which ones (→ Profitability Analyst)
- **Getting paid on time** — cash flow killer (→ AutoPay, recurring billing)
- **Finding/retaining good techs** — #1 operational challenge (→ guided workflows reduce training time)
- **Tech accountability** — did they actually do the work? (→ workflows, photos, GPS, scorecards)
- **Chemical waste** — over-dosing is expensive, under-dosing causes callbacks (→ Chemistry Advisor)
- **Rising chemical costs** — eating margins (→ Profitability Analyst tracks this)
- **Scaling from solo to multi-tech** — systems break at 50-100 pools (→ enterprise architecture from day 1)

### Frequently Cited
- Software is too expensive (ServiceTitan) or too limited (Housecall Pro)
- QuickBooks integration never works as advertised
- Mobile apps are buggy or slow offline
- Can't easily import data from old systems
- Customer communication is manual and time-consuming
- Commercial compliance record-keeping is tedious
- No way to predict seasonal workload changes

### Our Advantage Per Pain Point
| Pain Point | Competitor Solution | Our Solution |
|---|---|---|
| Don't know true costs | Pool Brain shows route profit reports | AI Profitability Analyst explains WHY and recommends actions |
| Underpriced accounts | None recommend specific prices | AI generates specific rate recommendations with justification |
| Chemical waste | Skimmer has Orenda dosing formulas | Chemistry Advisor AI explains reasoning, catches patterns, troubleshoots |
| Tech accountability | Checklists, photos, GPS | Guided workflows + AI Service Narrator generates proof-of-service |
| Scaling difficulty | Software works or doesn't | Enterprise multi-tenant architecture, AI reduces training burden |
| Data import pain | Basic CSV import | Onboarding Assistant AI fuzzy-matches messy data, reads photos |
| Compliance headaches | Pool Shark H2O has logs | Compliance Advisor AI + Pool Scout = proactive, not reactive |
