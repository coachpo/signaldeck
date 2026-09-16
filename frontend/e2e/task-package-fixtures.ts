import { expect, type APIRequestContext } from "@playwright/test";
import { stringify } from "yaml";
import { apiBase } from "./platform-fixtures";

type Schema = Record<string, unknown>;
type Tool = { toolId: string; inputSchema: Schema; outputSchema: Schema; resourceRequirements: string[] };
const object = (properties: Record<string, Schema>, required = Object.keys(properties)) => ({ type: "object", properties, required });
const ref = (value: string) => ({ ref: value });
const field = (tool: Tool, name: string) => (tool.inputSchema.properties as Record<string, Schema>)[name];
const text = { type: "string" };

// These fixtures consume the plugins' public contracts and declare only the DAGs
// needed by browser acceptance; every caller explicitly imports its own package.
async function toolContract(request: APIRequestContext, kind: string, port: string, toolId: string) {
  const response = await request.get(`http://127.0.0.1:${process.env[`SIGNALDECK_E2E_${kind}_PORT`] ?? port}/release`);
  expect(response.ok(), await response.text()).toBe(true);
  const release: { tools: Tool[] } = await response.json();
  const tool = release.tools.find(item => item.toolId === toolId);
  expect(tool, `Public plugin tool ${toolId}`).toBeDefined();
  return tool!;
}

function deterministic(tool: Tool, name: string) {
  return {
    name, inputSchema: tool.inputSchema, outputSchema: tool.outputSchema,
    strategy: { kind: "deterministic", toolId: tool.toolId, inputMapping: ref("agent.input"), outputMapping: ref("tool.output") },
    tools: [tool.toolId], resources: tool.resourceRequirements,
  };
}

function sections(tool: Tool, field: string, label: string, linkLabel: string, linkKey: string) {
  return [
    { kind: "markdown", label, ref: `nodes.save.output.${field}`, required: true },
    { kind: "receipt", label: "保存回执", ref: "nodes.save.output", required: true },
    { kind: "link", label: linkLabel, ref: "nodes.save.output", toolId: tool.toolId, linkKey, required: true },
  ];
}

async function notePackage(request: APIRequestContext, key: string) {
  const writer = await toolContract(request, "NOTES", "18082", "example/notes/create");
  const inputSchema = object({
    title: { ...field(writer, "title"), title: "标题" },
    text: { ...field(writer, "text"), title: "原文" },
  });
  return {
    apiVersion: "signaldeck.workflowPackage/v2", metadata: { key, name: "浏览器资料保存验证" },
    agents: { writer: deterministic(writer, "保存资料") },
    workflows: {
      retain: {
        name: `保存资料 ${key}`, inputSchema, outputSchema: writer.outputSchema,
        nodes: { save: { uses: "writer", inputMapping: { object: { title: ref("workflow.input.title"), text: ref("workflow.input.text") } } } },
        outputMapping: ref("nodes.save.output"),
        presentation: {
          version: "signaldeck.presentation/1", title: { kind: "input", ref: "workflow.input.title" },
          inputHints: [{ ref: "workflow.input.title", control: "text" }, { ref: "workflow.input.text", control: "textarea" }],
          sections: sections(writer, "text", "笔记正文", "打开笔记", "note"),
        },
      },
    },
  };
}

async function saveTaskPackage(request: APIRequestContext, definition: { metadata: { key: string } }) {
  const saved = await request.post(`${apiBase}/workflow-packages`, {
    data: { manifestSource: stringify(definition, { aliasDuplicateObjects: false }) },
  });
  expect(saved.ok(), await saved.text()).toBe(true);
  return saved.json();
}

export async function seedNoteTask(request: APIRequestContext) {
  const key = `browser-notes-${crypto.randomUUID().slice(0, 8)}`;
  await saveTaskPackage(request, await notePackage(request, key));
  return key;
}

async function summaryPackage(request: APIRequestContext, key: string) {
  const writer = await toolContract(request, "NOTES", "18082", "example/notes/create");
  const search = await toolContract(request, "NOTES", "18082", "example/notes/search");
  const inputSchema = object({
    title: { ...field(writer, "title"), title: "标题" },
    passage: { type: "string", title: "本次资料" },
    query: { ...field(search, "query"), title: "查找已有笔记" },
    includeDetails: { type: "boolean", title: "保留详细信息" },
  });
  const content = object({ content: field(writer, "text") });
  return {
    apiVersion: "signaldeck.workflowPackage/v2", metadata: { key, name: "浏览器模型整理验证" },
    agents: {
      search: deterministic(search, "读取已有资料"), writer: deterministic(writer, "保存整理内容"),
      summarize: {
        name: "整理资料", inputSchema: object({ passage: text, includeDetails: { type: "boolean" }, sources: search.outputSchema }), outputSchema: content,
        strategy: { kind: "model", modelRef: "research-model", prompt: "Summarize the supplied passage and retrieved notes using the requested detail level." },
      },
    },
    workflows: {
      summarize: {
        name: "整理资料", inputSchema, outputSchema: writer.outputSchema,
        nodes: {
          search: { uses: "search", inputMapping: { object: { query: ref("workflow.input.query") } } },
          summarize: { uses: "summarize", inputMapping: { object: { passage: ref("workflow.input.passage"), includeDetails: ref("workflow.input.includeDetails"), sources: ref("nodes.search.output") } } },
          save: { uses: "writer", inputMapping: { object: { title: ref("workflow.input.title"), text: ref("nodes.summarize.output.content") } } },
        },
        outputMapping: ref("nodes.save.output"),
        presentation: {
          version: "signaldeck.presentation/1", title: { kind: "input", ref: "workflow.input.title" },
          inputHints: [{ ref: "workflow.input.title", control: "text" }, { ref: "workflow.input.passage", control: "textarea" }, { ref: "workflow.input.query", control: "text" }],
          sections: sections(writer, "text", "笔记正文", "打开笔记", "note"),
        },
      },
    },
  };
}

async function reportPackage(request: APIRequestContext, key: string, oracle: boolean) {
  const writer = await toolContract(request, "FINANCE", "18083", "signaldeck/finance/reports_create");
  const quote = await toolContract(request, "FINANCE", "18083", "signaldeck/finance/market_data_quote_lookup");
  const question = { ...field(writer, "name"), title: "想了解什么" };
  const inputSchema = object(oracle ? { question } : {
    question,
    symbols: { ...field(quote, "symbols"), title: "研究对象" },
    includeDetails: { type: "boolean", title: "包含详细信息", "x-signaldeck-schema": "signaldeck.schema/2", default: true },
  });
  const content = object({ content: field(writer, "content") });
  const analyst = {
    name: "编写报告", inputSchema: oracle ? inputSchema : object({ question, includeDetails: { type: "boolean" }, quotes: quote.outputSchema }), outputSchema: content,
    strategy: { kind: "model", modelRef: "research-model", prompt: "Use the supplied evidence or available read tool to answer the question in a concise report." },
    tools: oracle ? ["signaldeck/digital-oracle/market_sentiment_lookup"] : [],
  };
  return {
    apiVersion: "signaldeck.workflowPackage/v2", metadata: { key, name: "浏览器插件报告验证" },
    agents: { analyst, writer: deterministic(writer, "保存报告"), ...(!oracle && { quote: deterministic(quote, "读取行情") }) },
    workflows: {
      report: {
        name: oracle ? "外部信号报告" : "行情报告", inputSchema, outputSchema: writer.outputSchema,
        nodes: {
          ...(!oracle && { quote: { uses: "quote", inputMapping: { object: { symbols: ref("workflow.input.symbols") } } } }),
          analyze: { uses: "analyst", inputMapping: oracle ? ref("workflow.input") : { object: { question: ref("workflow.input.question"), includeDetails: ref("workflow.input.includeDetails"), quotes: ref("nodes.quote.output") } } },
          save: { uses: "writer", inputMapping: { object: { name: ref("workflow.input.question"), content: ref("nodes.analyze.output.content") } } },
        },
        outputMapping: ref("nodes.save.output"),
        presentation: {
          version: "signaldeck.presentation/1", title: { kind: "input", ref: "workflow.input.question" },
          inputHints: [{ ref: "workflow.input.question", control: "textarea" }],
          sections: sections(writer, "content", "研究报告", "在 Finance 中查看报告", "report"),
        },
      },
    },
  };
}

export async function seedTaskScenarios(request: APIRequestContext) {
  const suffix = crypto.randomUUID().slice(0, 8);
  const cases = [
    { title: `保存资料 ${suffix}`, key: `browser-capture-${suffix}`, workflow: "retain", kind: "capture", section: "笔记正文" },
    { title: `整理资料 ${suffix}`, key: `browser-summary-${suffix}`, workflow: "summarize", kind: "summary", section: "笔记正文" },
    { title: `行情报告 ${suffix}`, key: `browser-quotes-${suffix}`, workflow: "report", kind: "finance", section: "研究报告" },
    { title: `外部信号报告 ${suffix}`, key: `browser-signals-${suffix}`, workflow: "report", kind: "oracle", section: "研究报告" },
  ] as const;
  const definitions = [
    await notePackage(request, cases[0].key), await summaryPackage(request, cases[1].key),
    await reportPackage(request, cases[2].key, false), await reportPackage(request, cases[3].key, true),
  ];
  for (const [index, definition] of definitions.entries()) {
    Object.values(definition.workflows)[0].name = cases[index].title;
    await saveTaskPackage(request, definition);
  }
  return cases;
}
