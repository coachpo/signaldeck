const serviceNames: Record<string, string> = {
  "research-model": "研究服务",
  "oracle-research-model": "综合研究服务",
  "finance-market-data": "行情与报告服务",
  "notes-workspace": "笔记保存位置",
  "example/notes": "笔记服务",
  "signaldeck/finance": "行情与报告服务",
  "signaldeck/digital-oracle": "综合资料服务",
};

export function connectionName(name: string, id: string) {
  return name && name !== id ? name : (serviceNames[id] ?? id);
}
