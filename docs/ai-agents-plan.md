# QuantumPools — AI Agent Architecture

> **Status as of 2026-04-07:** The agent *infrastructure* is built (DeepBlue conversational AI, email triage pipeline, agent learning system, tool execution framework). The 10 specialized domain agents below are the product roadmap — they represent the target architecture that DeepBlue tools and services are evolving toward. Several have partial implementations via DeepBlue tool executors in `deepblue/tools.py`.

## Implementation Status

| # | Agent | Status | Current Implementation |
|---|-------|--------|----------------------|
| 1 | Chemistry Advisor | **Partial** | `dosing_engine.py` exists, DeepBlue has `_exec_dosing()` tool. No standalone agent yet. |
| 2 | Profitability Analyst | **Partial** | `profitability_service.py` + `pricing_service.py` do calculations. No AI narrative generation yet. |
| 3 | Inspection Intelligence | **Partial** | Scraper, PDF extractor, facility matching all built. No AI summarization agent yet. |
| 4 | Service Narrator | **Not started** | No implementation. Planned for Phase 3c. |
| 5 | Route Strategist | **Partial** | OR-Tools VRP optimization built. No AI strategic reasoning yet. |
| 6 | Equipment Oracle | **Partial** | Equipment catalog + items + events tracked. DeepBlue has equipment tools. No predictive agent. |
| 7 | Customer Intelligence | **Not started** | No churn prediction or upsell identification. Planned for Phase 9-10. |
| 8 | Onboarding Assistant | **Not started** | CSV import exists (`reimport_pss_csv.py`). No AI-guided onboarding. |
| 9 | Satellite Analyst | **Partial** | Claude Vision analysis built (2-pass Haiku). No contextual narrative agent. |
| 10 | Compliance Advisor | **Not started** | Inspection data exists but no compliance checking agent. |

### What IS Built (not in the plan but exists)
- **Email Triage Agent** — classifies inbound emails, auto-drafts responses (`classifier.py`, `triage_agent.py`)
- **Customer Matcher** — fuzzy-matches emails to customers (`customer_matcher.py`)
- **Command Executor** — executes structured commands from threads (`command_executor.py`)
- **Health Monitor** — monitors agent success rates and alerts (`health_monitor.py`)
- **DeepBlue** — conversational AI assistant with 29 tool executors covering most agent domains
- **Agent Learning** — learns from human corrections to improve over time (`agent_learning_service.py`)

### Architectural Note
DeepBlue currently serves as a **unified agent** that covers multiple domain agent responsibilities via its tool system. The 10 agents below represent the target where each domain gets its own focused agent with dedicated prompts, context, and tool sets. The refactoring path: split `deepblue/tools.py` by domain → each domain tool set becomes the foundation for its dedicated agent.

---

## Design Principles
1. **Each agent has ONE job** — focused, testable, replaceable
2. **Never expand an agent's scope** — if a new need arises, evaluate whether it's a new agent
3. **AI is the ace card** — every feature starts with "how does AI make this better?"
4. **Agents communicate via services** — they don't call each other directly; the app orchestrates
5. **Each agent has its own system prompt, context window, and tool set**
6. **Cost-aware** — right-size the model per agent (Haiku for simple, Sonnet for moderate, Opus for complex)

---

## Agent Registry

### 1. CHEMISTRY ADVISOR
_"What should the tech do with this water?"_

**Scope:** Water chemistry analysis, dosing recommendations, and chemical troubleshooting.

**Inputs:**
- Chemical readings (pH, FC, TC, CYA, TA, CH, TDS, temp, salt, phosphates)
- Pool characteristics (gallons, type, body of water, indoor/outdoor, bather load)
- Chemical product inventory (what the company stocks)
- Historical readings for this body of water

**Outputs:**
- LSI calculation with plain-English interpretation ("Your water is slightly corrosive — calcium is low")
- Prioritized dosing instructions ("Add 12oz muriatic acid first, wait 30min, then add 2lbs calcium chloride")
- Chemical interaction warnings ("Do NOT add chlorine and acid at the same time")
- Trend alerts ("pH has been climbing for 3 weeks — check CO2 outgassing or aeration")
- Root cause analysis ("Recurring algae despite good chlorine → check phosphate levels and CYA")

**Why AI, not just formulas:**
- Formulas calculate doses. AI explains WHY and catches patterns humans miss.
- A tech enters readings and gets a conversational explanation, not just numbers.
- Can factor in context that formulas can't: "This pool had algae last month, so maintain higher FC target"
- Troubleshooting: "Green pool despite high chlorine → likely CYA lock, recommend partial drain"

**Model:** Sonnet — needs reasoning but not creative. Structured output.
**Phase:** 3d (LSI/Dosing)

---

### 2. PROFITABILITY ANALYST
_"Which accounts are losing money and what should we do about it?"_

**Scope:** Account profitability analysis, pricing recommendations, and financial intelligence.

**Inputs:**
- Account cost breakdown (chemical, labor, travel, overhead)
- Difficulty scores and factors
- Historical margin trends
- Org cost settings and target margins
- Comparable accounts (similar size, type, location)

**Outputs:**
- Natural language pricing recommendations with reasoning ("Pointe on Bell is your worst margin at $0.0096/gal — 47% below average. A $110/mo increase to $500 brings it to target margin. This is justified by the 40,700 gal volume.")
- Rate increase strategy ("Raise these 5 accounts by 8-12% in April before peak season. Expected revenue gain: $380/mo even if you lose 1.")
- Account health narrative ("3 accounts trending toward unprofitability — rising chemical costs on aging equipment")
- Anomaly detection ("Brookside chemical cost jumped 40% this month — possible leak or equipment issue")
- Competitive context ("Your average rate of $0.018/gal is below the Sacramento market median of $0.022/gal")

**Why AI, not just calculations:**
- Calculations give numbers. AI gives actionable business advice with context and reasoning.
- Can synthesize multiple factors (margin + difficulty + trend + customer relationship) into a recommendation
- Generates the "what to do about it" that no competitor provides

**Model:** Sonnet — analytical, structured reasoning
**Phase:** 3b (Profitability Analysis)

---

### 3. INSPECTION INTELLIGENCE (Pool Scout)
_"What do these inspection reports mean and who needs help?"_

**Scope:** EMD inspection report analysis, violation interpretation, and compliance intelligence.

**Inputs:**
- Raw inspection report PDFs (extracted text)
- Violation codes and descriptions
- Historical inspection data per facility
- Regulatory requirements by jurisdiction

**Outputs:**
- Plain-English violation summaries ("3 critical violations: chlorine below minimum, no safety signage, broken drain cover")
- Risk scoring with explanation ("Score 7.2/10 — declining trend, 3rd consecutive failed inspection")
- Actionable recommendations per violation ("Drain cover violation requires VGB-compliant replacement within 30 days")
- Facility trend analysis ("This facility has improved from 5 violations to 2 over 12 months — focus remaining on chemical compliance")
- Sales intelligence ("12 facilities in Elk Grove failed inspection this quarter — potential new clients")

**Why AI, not just data display:**
- Raw inspection data is bureaucratic and hard to parse
- AI translates legalese into actionable steps
- Pattern recognition across facilities and time periods
- Generates sales opportunities from compliance gaps

**Model:** Sonnet — document comprehension and summarization
**Phase:** 5 (Pool Scout)

---

### 4. SERVICE NARRATOR
_"Explain to the customer what we did and why"_

**Scope:** Generating customer-facing service reports from visit data.

**Inputs:**
- Visit checklist completion data
- Chemical readings (before/after if available)
- Dosing applied
- Tech notes
- Photos taken
- Issues found
- Equipment observations
- Weather/environmental context

**Outputs:**
- Professional, branded service email narrative ("We serviced your pool today. Water chemistry was slightly off — pH was high at 7.8, so we added muriatic acid to bring it back to the 7.4-7.6 range. Your chlorine levels look great. We also noticed your pump is making a slight noise — we'll keep an eye on it.")
- Tone matching (professional for commercial property managers, friendly for residential homeowners)
- Issue escalation language ("We found a minor crack in the skimmer basket — not urgent, but we recommend replacing it within the next month to prevent debris from reaching your pump.")
- Upsell suggestions woven naturally ("Your filter is due for a deep clean next month — we'll include it on your next visit or can schedule separately.")

**Why AI, not just templates:**
- Templates are robotic and generic. AI writes like a knowledgeable human.
- Adapts tone and detail level per customer type
- Naturally weaves in upsell opportunities without being salesy
- Explains chemistry in terms the customer understands

**Model:** Haiku — straightforward generation, high volume (every visit), cost-sensitive
**Phase:** 3c (Service Email Reports)

---

### 5. ROUTE STRATEGIST
_"How should we restructure routes for maximum efficiency and profit?"_

**Scope:** Route intelligence beyond basic optimization — strategic route planning.

**Inputs:**
- Current route assignments and schedules
- Property locations with profitability data
- Tech skills and certifications
- Service time per stop (historical)
- Drive time between stops
- Customer schedule preferences
- Seasonal patterns

**Outputs:**
- Route restructuring recommendations ("Moving Cottage Meadows from Shane's Tuesday to Chance's Tuesday saves 22 min drive time and groups it with 3 nearby accounts")
- New customer placement ("New lead at 4500 Madison Ave fits best on Shane's Wednesday route — 0.3 miles from existing stop")
- Unprofitable route segment identification ("Shane's Thursday route has 4 stops in Elk Grove that cost more in drive time than they earn — consider dropping or raising rates")
- Seasonal adjustment suggestions ("Summer volume increase — recommend splitting Route 3 into 3A/3B and hiring a part-time tech")
- "What if" modeling ("If you drop the 3 worst-margin accounts, Route 2 becomes 18% more profitable and 25 min shorter")

**Why AI, not just OR-Tools:**
- OR-Tools optimizes stop ORDER within a route. AI optimizes which stops should be on which route.
- Strategic decisions (drop accounts, hire techs, restructure days) require reasoning, not just math.
- Can factor in soft constraints (customer relationships, tech preferences, growth strategy)

**Model:** Sonnet — multi-factor reasoning with data
**Phase:** 3b (Profitability) + ongoing

---

### 6. EQUIPMENT ORACLE
_"What's going to break and when?"_

**Scope:** Equipment lifecycle intelligence — predicting failures, recommending replacements, estimating costs.

**Inputs:**
- Equipment records (type, brand, model, install date, warranty)
- Maintenance history
- Chemical readings (salt cell performance correlates with readings)
- Tech notes mentioning equipment issues
- Environmental factors (shade, trees, indoor/outdoor)
- Manufacturer specs and typical lifespans

**Outputs:**
- Failure predictions ("This Hayward pump was installed 2019, typical lifespan 8-12 years. Based on the noise noted in last 3 visits, recommend budgeting for replacement within 6 months.")
- Proactive upsell opportunities ("14 salt cells across your accounts are over 4 years old — batch replacement saves 15% on parts")
- Warranty alerts ("Filter warranty expires in 30 days — any existing issues should be claimed now")
- Cost estimates for proposals ("Replacing the S8M150 filter at Arbor Ridge: parts $450-600, labor 2hrs, suggest quoting $850-1100")
- Equipment comparison ("Customer asking about variable speed pump upgrade — ROI payback in 14 months from energy savings")

**Why AI, not just age tracking:**
- Age alone doesn't predict failure. AI combines age + usage + environmental factors + tech observations.
- Generates customer-ready language for proposals
- Identifies batch opportunities across accounts
- ROI calculations for upgrade recommendations

**Model:** Haiku for simple alerts, Sonnet for analysis and proposals
**Phase:** 9 (Equipment Tracking)

---

### 7. CUSTOMER INTELLIGENCE
_"Who's about to leave and who's ready to buy more?"_

**Scope:** Customer relationship intelligence — churn prediction, upsell identification, communication optimization.

**Inputs:**
- Payment history (on-time, late, missed)
- Service request frequency and tone
- Callback/complaint history
- Chemical reading trends (neglected pool = disengaged customer)
- Portal login activity
- Communication response rates
- Account age and lifetime value
- Feedback scores

**Outputs:**
- Churn risk scoring with reasoning ("High risk: 2 late payments, 3 complaints in 60 days, hasn't logged into portal in 3 months")
- Retention actions ("Call Mrs. Johnson personally — she's been unhappy with service time. Offer a complimentary filter clean.")
- Upsell readiness ("The Smiths just asked about heating options — they're a good candidate for the heater install + monthly maintenance upgrade")
- Communication timing ("Best time to send rate increase notice: after a positive service report, not after a complaint")
- Win-back campaigns ("12 customers cancelled in the last 6 months — 4 cited pricing. Reach out with competitive comparison.")

**Why AI, not just dashboards:**
- Dashboards show data. AI interprets signals and recommends specific actions.
- Combines quantitative signals (payment patterns) with qualitative (complaint tone)
- Generates the actual outreach language, not just "contact this customer"

**Model:** Sonnet — requires nuanced reasoning about human behavior
**Phase:** 9 (Customer Feedback) + 10 (Churn Prediction)

---

### 8. ONBOARDING ASSISTANT
_"Help new users get their business into the system fast"_

**Scope:** Intelligent data import, setup guidance, and initial configuration.

**Inputs:**
- Uploaded spreadsheets/CSVs (customer lists, route sheets, chemical logs)
- Photos of paper records
- Existing software export files (Skimmer, Pool Brain, etc.)
- Business description and preferences

**Outputs:**
- Column mapping for imports ("I detected 'Monthly Rate' in column G and 'Pool Gallons' in column F — confirm mapping?")
- Data cleaning suggestions ("Found 12 entries with no gallons — estimate from address using satellite detection?")
- Initial route optimization ("Based on your 85 customers, I recommend 4 routes: Mon/Thu North, Mon/Thu South, Tue/Fri East, Tue/Fri West")
- Settings recommendations ("Based on your location and business size, I recommend: California bather load method, $32/hr burdened labor rate, 35% target margin")
- Migration from competitor software ("I can import your Skimmer export — mapping 847 customers, 12 techs, 6 months of chemical history")

**Why AI, not just import wizards:**
- Import wizards require exact column matches. AI fuzzy-matches messy real-world data.
- Can read photos of paper route sheets and extract structured data
- Makes intelligent default recommendations based on business context
- Dramatically reduces time-to-value for new customers (biggest churn point for SaaS)

**Model:** Sonnet — data interpretation and reasoning
**Phase:** 7 (Data Migration) + 8 (Onboarding)

---

### 9. SATELLITE ANALYST
_"What can we learn about this property from above?"_

**Scope:** Interpreting satellite imagery analysis results with contextual intelligence.

**Note:** The actual computer vision (OpenCV/SAM) runs as a deterministic service, NOT an LLM agent. This agent interprets the CV results and adds intelligence.

**Inputs:**
- CV pipeline outputs (pool contour, sqft, vegetation %, overhang %, hardscape ratio, confidence scores)
- Property address and context
- Known property characteristics (if any)
- Comparable properties in the area

**Outputs:**
- Property assessment narrative ("Large commercial pool ~840 sqft, moderate tree coverage on the south side. Expect above-average debris load and partial afternoon shade reducing chlorine consumption slightly.")
- Difficulty factor recommendations ("Based on canopy coverage of 45% and overhang of 22%, I recommend: shade_exposure=partial_shade, tree_debris_level=moderate, adding ~$25-35/mo to service cost")
- Confidence caveats ("Image appears to be winter — tree canopy may be underestimated. Recommend verifying debris level on first visit.")
- Comparison to similar properties ("This pool is 15% larger than average for your commercial accounts but priced 8% below average — flag for rate review")

**Why a separate agent from the CV pipeline:**
- CV gives measurements. AI gives meaning and business context.
- Can reason about seasonal image quality issues
- Connects satellite findings to profitability and pricing

**Model:** Haiku — interpretation of structured data, not heavy reasoning
**Phase:** 3b (Satellite Analysis)

---

### 10. COMPLIANCE ADVISOR
_"Are we meeting requirements and what's changing?"_

**Scope:** Regulatory compliance guidance for commercial pools.

**Inputs:**
- Jurisdiction/locality
- Pool type (commercial, public, semi-public)
- Current chemical logs and testing frequency
- Bather load calculations
- Equipment certifications
- Inspection history
- Regulatory updates (can be fed new regulations)

**Outputs:**
- Compliance status per property ("Arbor Ridge: COMPLIANT — all chemical logs current, testing frequency meets Sacramento County requirements")
- Gap identification ("Missing: monthly bacteria test required for pools >30,000 gal in Sacramento County")
- Regulatory change alerts ("California AB-1234 effective July 2026 requires CYA testing weekly for commercial pools, up from monthly")
- Inspection preparation ("EMD inspection likely within 60 days — ensure: signage current, chemical logs accessible, VGB compliance documented")
- Documentation generation (compliance reports, chemical log summaries for inspectors)

**Why AI, not just checklists:**
- Regulations change and vary by jurisdiction. AI adapts to context.
- Can interpret new regulatory text and map to specific action items
- Generates inspection-ready documentation
- Connects with Pool Scout data for proactive compliance

**Model:** Sonnet — regulatory interpretation requires careful reasoning
**Phase:** 5 (Pool Scout) + 3d (Commercial compliance)

---

## Agent Infrastructure

### Shared Components
- **Agent Router** — service layer that routes requests to the correct agent
- **Prompt Registry** — versioned system prompts per agent, stored in DB (not hardcoded)
- **Context Builder** — assembles relevant context for each agent call (customer data, readings, history)
- **Response Parser** — extracts structured data from agent responses (for UI rendering and storage)
- **Cost Tracker** — logs every API call with model, tokens, cost, agent_id, org_id
- **Cache Layer** — Redis cache for repeated/similar queries (e.g., same dosing question within 24h)
- **Feedback Loop** — users can rate agent responses (thumbs up/down), feeds into prompt improvement

### API Pattern
```
POST /api/v1/ai/{agent_name}/query
{
  "context": { ... },  // agent-specific input
  "mode": "full" | "quick",  // quick = Haiku, full = Sonnet/Opus
  "stream": true | false
}

Response:
{
  "response": "...",  // natural language
  "structured": { ... },  // parsed actionable data
  "confidence": 0.87,
  "model": "claude-sonnet-4-6",
  "tokens_used": 1240,
  "cost": 0.0037,
  "agent": "chemistry_advisor",
  "cache_hit": false
}
```

### Cost Management
- **Per-org usage tracking** — agents count toward subscription limits
- **Model tiering** — Haiku for high-volume/simple, Sonnet for analytical, Opus only if needed
- **Aggressive caching** — same question within window = cached response
- **Batch processing** — group similar requests (e.g., end-of-day dosing summaries)
- **Rate limiting per org** — prevent runaway costs

### Platform Admin Visibility
- Agent usage dashboard (calls/day, cost/day, by agent, by org)
- Response quality metrics (user feedback ratings)
- Prompt version management (A/B testing prompts)
- Cost projection and alerting

---

## Agent-to-Feature Mapping

| Feature | Primary Agent | Supporting Agent |
|---|---|---|
| Chemical readings entry | Chemistry Advisor | — |
| Dosing recommendations | Chemistry Advisor | — |
| LSI calculation + explanation | Chemistry Advisor | — |
| Water trouble diagnosis | Chemistry Advisor | — |
| Profitability dashboard insights | Profitability Analyst | — |
| Pricing recommendations | Profitability Analyst | Route Strategist |
| Rate increase strategy | Profitability Analyst | Customer Intelligence |
| Account health scoring | Profitability Analyst | Customer Intelligence |
| EMD report summarization | Inspection Intelligence | Compliance Advisor |
| Facility risk scoring | Inspection Intelligence | — |
| Sales lead generation from EMD | Inspection Intelligence | Customer Intelligence |
| Post-visit service email | Service Narrator | Chemistry Advisor (for reading explanations) |
| Customer communication drafting | Service Narrator | — |
| Route restructuring | Route Strategist | Profitability Analyst |
| New customer route placement | Route Strategist | — |
| "What if" scenario modeling | Route Strategist | Profitability Analyst |
| Equipment failure prediction | Equipment Oracle | — |
| Repair/upgrade proposals | Equipment Oracle | Service Narrator (for customer language) |
| Warranty management | Equipment Oracle | — |
| Churn prediction | Customer Intelligence | — |
| Upsell identification | Customer Intelligence | Equipment Oracle |
| Retention actions | Customer Intelligence | Service Narrator |
| Data import/migration | Onboarding Assistant | — |
| New org setup guidance | Onboarding Assistant | — |
| Satellite image interpretation | Satellite Analyst | — |
| Property difficulty assessment | Satellite Analyst | Profitability Analyst |
| Compliance checking | Compliance Advisor | Inspection Intelligence |
| Inspection preparation | Compliance Advisor | — |
| Regulatory change alerts | Compliance Advisor | — |

---

## Build Order (aligned with phases)

| Phase | Agents Built |
|---|---|
| 3b | **Profitability Analyst**, **Satellite Analyst** + Agent Infrastructure (router, prompts, cost tracking) |
| 3c | **Service Narrator** |
| 3d | **Chemistry Advisor** |
| 4 | (no new agents — portal uses existing) |
| 5 | **Inspection Intelligence**, **Compliance Advisor** |
| 6 | Platform admin agent monitoring dashboard |
| 7-8 | **Onboarding Assistant** |
| 9 | **Equipment Oracle**, **Customer Intelligence**, **Route Strategist** |
