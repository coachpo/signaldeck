import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import { LaunchInputs } from "./launch-inputs";
import { supportsTaskForm, taskConstraintErrors, taskDefaults, availableTasks } from "./task-catalog";
import type { Json, JsonObject, WorkflowPackage } from "@/lib/types/workflow-platform";
function Form({ schema, initial }: { schema: JsonObject; initial: Json }) {
  const [value, setValue] = useState(initial);
  return <><LaunchInputs onDirtyChange={() => {}} schema={schema} value={value} onChange={setValue} inputHints={[{ref:"workflow.input.renamed",control:"textarea",placeholder:"Enter source"}]} /><output>{JSON.stringify(value)}</output></>;
}
it("uses declared labels and static hints after fields are renamed, preserving whitespace", () => {
  render(<Form schema={{type:"object",properties:{renamed:{type:"string",title:"Source text"}},required:["renamed"]}} initial={{renamed:""}} />);
  expect(screen.getByPlaceholderText("Enter source").tagName).toBe("TEXTAREA");
  fireEvent.change(screen.getByLabelText("Source text"),{target:{value:"  raw\n\ntext  "}});
  expect(JSON.parse(screen.getByRole("status").textContent!)).toEqual({renamed:"  raw\n\ntext  "});
});
it("preserves omitted defaults, nullable and unknown fields when editing siblings", () => {
  render(<Form schema={{type:"object",properties:{title:{type:"string"},optional:{type:"string","x-signaldeck-schema":"signaldeck.schema/2",default:"seed"},query:{type:["string","null"]}},required:["title"]}} initial={{title:"old",query:null,legacy:"keep"}} />);
  fireEvent.change(screen.getByLabelText("title"),{target:{value:"new"}});
  expect(JSON.parse(screen.getByRole("status").textContent!)).toEqual({title:"new",query:null,legacy:"keep"});
});
it("edits arrays using the shared form without delimiter parsing", () => {
  render(<Form schema={{type:"object",properties:{collection:{type:"array",items:{type:"string"}}},required:["collection"]}} initial={{collection:["A,B"]}} />);
  fireEvent.click(screen.getByRole("button",{name:"Add Item"}));
  fireEvent.change(screen.getByLabelText("Item 2"),{target:{value:"C"}});
  expect(JSON.parse(screen.getByRole("status").textContent!)).toEqual({collection:["A,B","C"]});
});
it("treats includeRisk/reportId/collection as ordinary data; only declared defaults seed drafts", () => {
  const schema: JsonObject={type:"object",properties:{includeRisk:{type:"boolean"},reportId:{type:"string"},collection:{type:"array",items:{type:"string"}}},required:["includeRisk","reportId","collection"]};
  expect(taskDefaults(schema)).toEqual({includeRisk:false,reportId:"",collection:[]});
  expect(taskDefaults({...schema,properties:{includeRisk:{type:"boolean","x-signaldeck-schema":"signaldeck.schema/2",default:true}},required:["includeRisk"]})).toEqual({includeRisk:true});
});
it("discovers new package and workflow names including unsupported legal roots", () => {
  const pkg={key:"unseen",definition:{metadata:{key:"unseen",name:"New package"},workflows:{custom:{name:"New task",description:"From package data",inputSchema:{type:"object",properties:{renamed:{type:"string",minLength:1}},required:["renamed"]}},scalar:{name:"Scalar",inputSchema:{type:"array",items:{type:"string"}}}}}} as unknown as WorkflowPackage;
  const tasks=availableTasks([pkg]);
  expect(tasks.map(t=>[t.workflowKey,t.title,t.supported])).toEqual([["custom","New task",true],["scalar","Scalar",false]]);
  expect(supportsTaskForm(tasks[0].workflow.inputSchema)).toBe(true);
  expect(taskConstraintErrors(tasks[0].workflow.inputSchema,{renamed:""})).toEqual({"parameters.renamed":"请至少填写 1 个字符。"});
});

it("keeps array item defaults omitted while editing another item", () => {
  render(<Form schema={{type:"object",properties:{items:{type:"array",items:{type:"object",properties:{title:{type:"string"},optional:{type:"string","x-signaldeck-schema":"signaldeck.schema/2",default:"seed"}},required:["title"]}}},required:["items"]}} initial={{items:[{title:"first",legacy:"keep"},{title:"second"}]}} />);
  fireEvent.change(screen.getAllByLabelText("title")[1],{target:{value:"edited"}});
  expect(JSON.parse(screen.getByRole("status").textContent!)).toEqual({items:[{title:"first",legacy:"keep"},{title:"edited"}]});
});

it("matches JSON Schema Unicode code point length constraints", () => {
  expect(taskConstraintErrors({type:"string",maxLength:1},"😀")).toEqual({});
  expect(taskConstraintErrors({type:"string",minLength:2},"😀")).toEqual({parameters:"请至少填写 2 个字符。"});
});
