"""Bundled Workflow Packages installed only when their operator-owned key is absent."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.application.definitions import canonical_source
from app.domain.definition_parser import parse_package_source
from app.domain.definitions import CompiledPackage


class SeedStore(Protocol):
    def save_seed_package(
        self,
        package_key: str,
        source: str,
        definition: dict[str, Any],
        plan: dict[str, Any],
        package_hash: str,
    ) -> bool: ...


@dataclass(frozen=True)
class SeedPackage:
    source: str
    compiled: CompiledPackage


def load_seed_packages() -> tuple[SeedPackage, ...]:
    """Read complete packaged definitions without loading or contacting a business plugin."""
    return tuple(SeedPackage(source, parse_package_source(source)) for source in _SOURCES.values())


def seed_packages(store: SeedStore) -> list[str]:
    """Return inserted keys; existing keys, including operator edits, remain untouched."""
    inserted = []
    for seed in load_seed_packages():
        compiled = seed.compiled
        definition = compiled.package.model_dump(mode="json", by_alias=True)
        key = compiled.package.metadata.key
        if store.save_seed_package(
            key,
            canonical_source(definition),
            definition,
            {
                name: plan.model_dump(mode="json", by_alias=True)
                for name, plan in compiled.plans.items()
            },
            compiled.content_hash,
        ):
            inserted.append(key)
    return inserted


# Generated from demo/*.yaml by demo/sync_seeds.py. Source is shipped inside the Core artifact.
# seed-sources:start
_SOURCES: dict[str, str] = {
    "digital_oracle_researcher": """apiVersion: signaldeck.workflowPackage/v2
metadata:
  key: digital_oracle_researcher
  name: Digital Oracle research
  description: Run parallel specialist research with independently deployed Oracle tools and
    retain the final report in Finance.
agents:
  researcher:
    name: Digital Oracle specialist
    inputSchema:
      type: object
      properties:
        question:
          type: string
          minLength: 1
        focus:
          type: string
      required:
      - question
      - focus
    outputSchema:
      type: object
      properties:
        text:
          type: string
          minLength: 1
      required:
      - text
    strategy:
      kind: model
      modelRef: research-model
      prompt: Research the question using the granted Digital Oracle tools appropriate to the
        focus. Read tool schemas before choosing arguments. Cite returned sources and
        timestamps. State provider unavailability and distinguish facts from inference; never
        invent data when a provider is unavailable. Produce a concise research note.
    tools:
    - signaldeck/digital-oracle/prediction_markets_lookup
    - signaldeck/digital-oracle/sec_filings_lookup
    - signaldeck/digital-oracle/market_sentiment_lookup
    - signaldeck/digital-oracle/macro_rates_lookup
    - signaldeck/digital-oracle/crypto_derivatives_lookup
    - signaldeck/digital-oracle/cftc_positioning_lookup
    - signaldeck/digital-oracle/options_lookup
    resources: []
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
  editor:
    name: Cross-source research editor
    inputSchema:
      type: object
      properties:
        question:
          type: string
          minLength: 1
        macro:
          type: object
          properties:
            text:
              type: string
              minLength: 1
          required:
          - text
        company:
          type: object
          properties:
            text:
              type: string
              minLength: 1
          required:
          - text
      required:
      - question
      - macro
      - company
    outputSchema:
      type: object
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 160
        content:
          type: string
          minLength: 1
      required:
      - name
      - content
      unevaluatedProperties: false
    strategy:
      kind: model
      modelRef: research-model
      prompt: Synthesize the two research notes into one report with name and content. Preserve
        source attribution, disagreements, provider limitations and dates. Include unanswered
        questions. Keep the report name within 160 characters.
    tools: []
    resources: []
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
  save_report:
    name: Save Finance report
    inputSchema:
      type: object
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 160
        content:
          type: string
          minLength: 1
      required:
      - name
      - content
      unevaluatedProperties: false
    outputSchema:
      type: object
      properties:
        reportId:
          type: integer
        name:
          type: string
      required:
      - reportId
      - name
    strategy:
      kind: deterministic
      toolId: signaldeck/finance/reports_create
      inputMapping:
        ref: agent.input
      outputMapping:
        object:
          reportId:
            ref: tool.output.id
          name:
            ref: tool.output.name
    tools:
    - signaldeck/finance/reports_create
    resources: []
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
workflows:
  research:
    name: Cross-source research
    inputSchema:
      type: object
      properties:
        question:
          type: string
          minLength: 1
      required:
      - question
    outputSchema:
      type: object
      properties:
        reportId:
          type: integer
        name:
          type: string
      required:
      - reportId
      - name
    nodes:
      macro:
        uses: researcher
        inputMapping:
          object:
            question:
              ref: workflow.input.question
            focus:
              value: Macro rates, positioning, derivatives and prediction-market context
      company:
        uses: researcher
        inputMapping:
          object:
            question:
              ref: workflow.input.question
            focus:
              value: Company filings, market sentiment and options evidence
      editor:
        uses: editor
        inputMapping:
          object:
            question:
              ref: workflow.input.question
            macro:
              ref: nodes.macro.output
            company:
              ref: nodes.company.output
      save:
        uses: save_report
        inputMapping:
          ref: nodes.editor.output
    outputMapping:
      ref: nodes.save.output
    maxParallelNodes: 4
    deadlineSeconds: 900
    failurePolicy: continue_independent
""",
    "research_notes": """apiVersion: signaldeck.workflowPackage/v2
metadata:
  key: research_notes
  name: Research notes
  description: Search the research collection, optionally edit a note with a model, and store
    an immutable record. Save original text without a model using the capture workflow.
agents:
  find_notes:
    name: Search research collection
    inputSchema:
      type: object
      properties:
        query:
          type: string
          maxLength: 200
        limit:
          type: integer
          minimum: 1
          maximum: 50
      required: []
      unevaluatedProperties: false
    outputSchema:
      type: object
      properties:
        notes:
          type: array
          items:
            type: object
            properties:
              id:
                type: string
              collection:
                type: string
              title:
                type: string
              text:
                type: string
            required:
            - id
            - collection
            - title
            - text
            unevaluatedProperties: false
      required:
      - notes
      unevaluatedProperties: false
    strategy:
      kind: deterministic
      toolId: example/notes/search
      inputMapping:
        ref: agent.input
      outputMapping:
        ref: tool.output
    tools:
    - example/notes/search
    resources:
    - notes-workspace
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
  summarize:
    name: Research note editor
    inputSchema:
      type: object
      properties:
        text:
          type: string
          maxLength: 100000
        priorNotes:
          type: object
          properties:
            notes:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  collection:
                    type: string
                  title:
                    type: string
                  text:
                    type: string
                required:
                - id
                - collection
                - title
                - text
                unevaluatedProperties: false
          required:
          - notes
          unevaluatedProperties: false
      required:
      - text
      - priorNotes
    outputSchema:
      type: object
      properties:
        text:
          type: string
          maxLength: 100000
      required:
      - text
    strategy:
      kind: model
      modelRef: research-model
      prompt: Edit the supplied research text into a clear note. Use prior notes only as
        attributed context and retain uncertainty. Do not invent external facts or claim new
        research. Keep the text under 100000 characters.
    tools: []
    resources: []
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
  write_note:
    name: Save immutable research note
    inputSchema:
      type: object
      properties:
        title:
          type: string
          minLength: 1
          maxLength: 200
        text:
          type: string
          maxLength: 100000
      required:
      - title
      - text
      unevaluatedProperties: false
    outputSchema:
      type: object
      properties:
        id:
          type: string
        collection:
          type: string
        title:
          type: string
        text:
          type: string
      required:
      - id
      - collection
      - title
      - text
      unevaluatedProperties: false
    strategy:
      kind: deterministic
      toolId: example/notes/create
      inputMapping:
        ref: agent.input
      outputMapping:
        ref: tool.output
    tools:
    - example/notes/create
    resources:
    - notes-workspace
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
workflows:
  research:
    name: Review and save a note
    inputSchema:
      type: object
      properties:
        title:
          type: string
          minLength: 1
          maxLength: 200
        text:
          type: string
          maxLength: 100000
        query:
          type: string
          maxLength: 200
        summarize:
          type: boolean
      required:
      - title
      - text
      - query
      - summarize
    outputSchema:
      type: object
      properties:
        id:
          type: string
        collection:
          type: string
        title:
          type: string
        text:
          type: string
      required:
      - id
      - collection
      - title
      - text
      unevaluatedProperties: false
    nodes:
      prior:
        uses: find_notes
        inputMapping:
          object:
            query:
              ref: workflow.input.query
            limit:
              value: 20
      edit:
        uses: summarize
        inputMapping:
          object:
            text:
              ref: workflow.input.text
            priorNotes:
              ref: nodes.prior.output
        condition:
          op: eq
          args:
          - ref: workflow.input.summarize
          - value: true
      save:
        uses: write_note
        dependsOn:
        - prior
        acceptUpstreamStates:
        - succeeded
        - skipped
        inputMapping:
          object:
            title:
              ref: workflow.input.title
            text:
              ref: nodes.edit.output.text
              onMissing:
                ref: workflow.input.text
    outputMapping:
      ref: nodes.save.output
    maxParallelNodes: 4
    deadlineSeconds: 900
    failurePolicy: continue_independent
  capture:
    name: Save original text
    inputSchema:
      type: object
      properties:
        title:
          type: string
          minLength: 1
          maxLength: 200
        text:
          type: string
          maxLength: 100000
      required:
      - title
      - text
      unevaluatedProperties: false
    outputSchema:
      type: object
      properties:
        id:
          type: string
        collection:
          type: string
        title:
          type: string
        text:
          type: string
      required:
      - id
      - collection
      - title
      - text
      unevaluatedProperties: false
    nodes:
      save:
        uses: write_note
        inputMapping:
          ref: workflow.input
    outputMapping:
      ref: nodes.save.output
    maxParallelNodes: 4
    deadlineSeconds: 900
    failurePolicy: continue_independent
""",
    "tradingagents_advisory_research": """apiVersion: signaldeck.workflowPackage/v2
metadata:
  key: tradingagents_advisory_research
  name: Market advisory research
  description: Collect current quotes, run independent opportunity and risk reviews, and save
    an evidence-based report in Finance.
agents:
  collect_quotes:
    name: Collect fresh market quotes
    inputSchema:
      type: object
      properties:
        symbols:
          type: array
          items:
            type: string
          minItems: 1
          maxItems: 10
      required:
      - symbols
      unevaluatedProperties: false
    outputSchema:
      type: object
      properties:
        toolKey:
          const: signaldeck/finance/market_data_quote_lookup
          type: string
        quotes:
          type: array
          items:
            type: object
            properties:
              symbol:
                type: string
              name:
                type: string
              price:
                type: string
              currency:
                type: string
              provider:
                type: string
              asOf:
                type: string
              isStale:
                type: boolean
              previousClose:
                type: string
            required:
            - symbol
            - price
            - currency
            - provider
            - isStale
            unevaluatedProperties: false
        warnings:
          type: array
          items:
            type: object
            properties:
              code:
                type: string
              message:
                type: string
              details:
                type: array
                items:
                  type: object
                  properties:
                    key:
                      type: string
                    value:
                      type: string
                  required:
                  - key
                  - value
                  unevaluatedProperties: false
            required:
            - code
            - message
            - details
            unevaluatedProperties: false
      required:
      - quotes
      unevaluatedProperties: false
    strategy:
      kind: deterministic
      toolId: signaldeck/finance/market_data_quote_lookup
      inputMapping:
        ref: agent.input
      outputMapping:
        ref: tool.output
    tools:
    - signaldeck/finance/market_data_quote_lookup
    resources:
    - finance-market-data
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
  analyst:
    name: Market evidence analyst
    inputSchema:
      type: object
      properties:
        question:
          type: string
          minLength: 1
        perspective:
          type: string
        market:
          type: object
          properties:
            toolKey:
              const: signaldeck/finance/market_data_quote_lookup
              type: string
            quotes:
              type: array
              items:
                type: object
                properties:
                  symbol:
                    type: string
                  name:
                    type: string
                  price:
                    type: string
                  currency:
                    type: string
                  provider:
                    type: string
                  asOf:
                    type: string
                  isStale:
                    type: boolean
                  previousClose:
                    type: string
                required:
                - symbol
                - price
                - currency
                - provider
                - isStale
                unevaluatedProperties: false
            warnings:
              type: array
              items:
                type: object
                properties:
                  code:
                    type: string
                  message:
                    type: string
                  details:
                    type: array
                    items:
                      type: object
                      properties:
                        key:
                          type: string
                        value:
                          type: string
                      required:
                      - key
                      - value
                      unevaluatedProperties: false
                required:
                - code
                - message
                - details
                unevaluatedProperties: false
          required:
          - quotes
          unevaluatedProperties: false
      required:
      - question
      - perspective
      - market
    outputSchema:
      type: object
      properties:
        text:
          type: string
          minLength: 1
      required:
      - text
    strategy:
      kind: model
      modelRef: research-model
      prompt: Analyze the supplied market snapshot for the requested perspective. Use only
        supplied prices and source timestamps; distinguish stale or missing data. Do not invent
        facts. Write a concise evidence-based assessment and uncertainties; do not execute
        trades.
    tools: []
    resources: []
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
  synthesize:
    name: Advisory report editor
    inputSchema:
      type: object
      properties:
        question:
          type: string
          minLength: 1
        market:
          type: object
          properties:
            toolKey:
              const: signaldeck/finance/market_data_quote_lookup
              type: string
            quotes:
              type: array
              items:
                type: object
                properties:
                  symbol:
                    type: string
                  name:
                    type: string
                  price:
                    type: string
                  currency:
                    type: string
                  provider:
                    type: string
                  asOf:
                    type: string
                  isStale:
                    type: boolean
                  previousClose:
                    type: string
                required:
                - symbol
                - price
                - currency
                - provider
                - isStale
                unevaluatedProperties: false
            warnings:
              type: array
              items:
                type: object
                properties:
                  code:
                    type: string
                  message:
                    type: string
                  details:
                    type: array
                    items:
                      type: object
                      properties:
                        key:
                          type: string
                        value:
                          type: string
                      required:
                      - key
                      - value
                      unevaluatedProperties: false
                required:
                - code
                - message
                - details
                unevaluatedProperties: false
          required:
          - quotes
          unevaluatedProperties: false
        opportunity:
          type: object
          properties:
            text:
              type: string
              minLength: 1
          required:
          - text
        risk:
          type: object
          properties:
            text:
              type: string
              minLength: 1
          required:
          - text
      required:
      - question
      - market
      - opportunity
      - risk
    outputSchema:
      type: object
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 160
        content:
          type: string
          minLength: 1
      required:
      - name
      - content
      unevaluatedProperties: false
    strategy:
      kind: model
      modelRef: research-model
      prompt: Create a research report with name and content. Compare opportunity and risk
        evidence, identify stale data and missing risk review, include the question, quoted
        observations, uncertainties and practical follow-up research. Never claim a skipped
        risk review occurred. Return a report title of at most 160 characters.
    tools: []
    resources: []
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
  save_report:
    name: Save Finance report
    inputSchema:
      type: object
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 160
        content:
          type: string
          minLength: 1
      required:
      - name
      - content
      unevaluatedProperties: false
    outputSchema:
      type: object
      properties:
        reportId:
          type: integer
        name:
          type: string
      required:
      - reportId
      - name
    strategy:
      kind: deterministic
      toolId: signaldeck/finance/reports_create
      inputMapping:
        ref: agent.input
      outputMapping:
        object:
          reportId:
            ref: tool.output.id
          name:
            ref: tool.output.name
    tools:
    - signaldeck/finance/reports_create
    resources: []
    budget:
      maxModelRequests: 6
      maxToolCalls: 8
      maxTokens: 18000
      deadlineSeconds: 180
      maxParallelTools: 3
workflows:
  research:
    name: Market advisory report
    inputSchema:
      type: object
      properties:
        symbols:
          type: array
          items:
            type: string
          minItems: 1
          maxItems: 10
        question:
          type: string
          minLength: 1
        includeRisk:
          type: boolean
      required:
      - symbols
      - question
      - includeRisk
    outputSchema:
      type: object
      properties:
        reportId:
          type: integer
        name:
          type: string
      required:
      - reportId
      - name
    nodes:
      collect:
        uses: collect_quotes
        inputMapping:
          object:
            symbols:
              ref: workflow.input.symbols
      opportunity:
        uses: analyst
        dependsOn:
        - collect
        inputMapping:
          object:
            question:
              ref: workflow.input.question
            perspective:
              value: Opportunity and upside evidence
            market:
              ref: nodes.collect.output
      risk:
        uses: analyst
        inputMapping:
          object:
            question:
              ref: workflow.input.question
            perspective:
              value: Downside, uncertainty and disconfirming evidence
            market:
              ref: nodes.collect.output
        condition:
          op: all
          args:
          - op: exists
            args:
            - ref: nodes.collect.output.quotes
          - op: eq
            args:
            - ref: workflow.input.includeRisk
            - value: true
      summary:
        uses: synthesize
        acceptUpstreamStates:
        - succeeded
        - skipped
        inputMapping:
          object:
            question:
              ref: workflow.input.question
            market:
              ref: nodes.collect.output
              onMissing:
                value:
                  quotes: []
            opportunity:
              ref: nodes.opportunity.output
              onMissing:
                value:
                  text: Opportunity assessment is unavailable.
            risk:
              ref: nodes.risk.output
              onMissing:
                value:
                  text: Risk review was not requested and was skipped.
      save:
        uses: save_report
        inputMapping:
          ref: nodes.summary.output
    outputMapping:
      ref: nodes.save.output
    maxParallelNodes: 4
    deadlineSeconds: 900
    failurePolicy: continue_independent
""",
}
# seed-sources:end
