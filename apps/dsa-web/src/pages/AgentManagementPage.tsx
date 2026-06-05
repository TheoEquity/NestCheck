import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, Input, PageHeader, Select, Textarea } from '../components/common';
import {
  agentManagementApi,
  type AgentManagementAgent,
  type AgentManagementOverview,
  type AgentManagementProfile,
  type AgentManagementSkill,
  type AgentSkillTextResponse,
  type AgentManagementTool,
} from '../api/agentManagement';
import { getParsedApiError, type ParsedApiError } from '../api/error';

type TabKey = 'profiles' | 'agents' | 'tools' | 'skills';
type AgentFormState = {
  id: string;
  name: string;
  display_name: string;
  description: string;
  type: string;
  max_steps: string;
  tools: string[];
  skills_routing: string;
  skills: string[];
  prompt_system: string;
};
type ProfileFormState = {
  id: string;
  name: string;
  asset_type: string;
  status: string;
  mode: string;
  workflow: string[];
  description: string;
};
type SkillEditorState = {
  skill: AgentManagementSkill;
  content: string;
  sourcePath: string;
};

const tabs: Array<{ key: TabKey; label: string; description: string }> = [
  { key: 'profiles', label: '分析方案', description: '配置单 Agent / 多 Agent 模式与执行 workflow' },
  { key: 'agents', label: '专业 Agent', description: '配置专业 Agent、步骤、tools 与 skills' },
  { key: 'tools', label: 'Tools', description: '查看所有 runtime tools，并进入 YAML 配置源编辑' },
  { key: 'skills', label: 'Skills', description: '查看所有 skills，并进入 YAML 配置源编辑' },
];

const categoryLabels: Record<string, string> = {
  data: '数据',
  analysis: '分析',
  search: '搜索',
  market: '市场',
  backtest: '回测',
  trend: '趋势',
  pattern: '形态',
  reversal: '反转',
  framework: '框架',
};

function labelFor(value: string, labels: Record<string, string>) {
  return labels[value] ?? value;
}

function toAgentForm(agent?: AgentManagementAgent): AgentFormState {
  const skillItems = Array.isArray(agent?.skills?.items) ? agent.skills.items.map(String) : [];
  return {
    id: agent?.id ?? '',
    name: agent?.name ?? '',
    display_name: agent?.display_name ?? '',
    description: agent?.description ?? '',
    type: agent?.type ?? 'llm_agent',
    max_steps: agent?.max_steps == null ? '' : String(agent.max_steps),
    tools: agent?.tools ?? [],
    skills_routing: String(agent?.skills?.routing ?? 'manual'),
    skills: skillItems,
    prompt_system: String(agent?.prompt?.system ?? ''),
  };
}

function buildAgentYaml(form: AgentFormState) {
  const tools = form.tools.map((item) => item.trim()).filter(Boolean);
  const skills = form.skills.map((item) => item.trim()).filter(Boolean);
  const maxSteps = form.max_steps.trim() || 'null';
  const promptLines = form.prompt_system.trimEnd().split('\n');
  const toolsLines = tools.length ? ['    tools:', ...tools.map((tool) => `      - ${tool}`)] : ['    tools: []'];
  const skillLines = skills.length ? ['      items:', ...skills.map((skill) => `        - ${skill}`)] : ['      items: []'];
  return [
    `  - id: ${form.id.trim()}`,
    `    name: ${form.name.trim()}`,
    `    display_name: ${JSON.stringify(form.display_name.trim())}`,
    `    description: ${JSON.stringify(form.description.trim())}`,
    `    type: ${form.type.trim() || 'llm_agent'}`,
    `    max_steps: ${maxSteps}`,
    ...toolsLines,
    '    skills:',
    `      routing: ${form.skills_routing.trim() || 'manual'}`,
    ...skillLines,
    '    prompt:',
    '      system: |',
    ...(promptLines.length && promptLines[0] ? promptLines.map((line) => `        ${line}`) : ['        ']),
  ].join('\n');
}

function toProfileForm(profile?: AgentManagementProfile): ProfileFormState {
  return {
    id: profile?.id ?? '',
    name: profile?.name ?? '',
    asset_type: profile?.asset_type ?? 'stock',
    status: profile?.status ?? 'planned',
    mode: profile?.mode ?? '',
    workflow: profile?.workflow ?? [],
    description: profile?.description ?? '',
  };
}

function buildProfileYaml(form: ProfileFormState) {
  const workflow = form.workflow.map((item) => item.trim()).filter(Boolean);
  return [
    `  - id: ${form.id.trim()}`,
    `    name: ${JSON.stringify(form.name.trim())}`,
    `    asset_type: ${form.asset_type.trim() || 'stock'}`,
    `    status: ${form.status.trim() || 'planned'}`,
    `    mode: ${form.mode.trim() || form.id.trim()}`,
    ...(workflow.length ? ['    workflow:', ...workflow.map((node) => `      - ${node}`)] : ['    workflow: []']),
    `    description: ${JSON.stringify(form.description.trim())}`,
  ].join('\n');
}

function upsertProfileYaml(content: string, originalId: string | null, form: ProfileFormState) {
  const nextBlock = `${buildProfileYaml(form)}\n`;
  if (originalId) {
    const itemStart = content.search(new RegExp(`^\\s*- id: ${originalId}\\s*$`, 'm'));
    if (itemStart >= 0) {
      const nextItemRelative = content.slice(itemStart + 1).search(/^\s*- id: \S+\s*$/m);
      const itemEnd = nextItemRelative >= 0 ? itemStart + 1 + nextItemRelative : content.length;
      return `${content.slice(0, itemStart)}${nextBlock}${content.slice(itemEnd)}`;
    }
  }

  const profilesIndex = content.search(/^profiles:\s*$/m);
  if (profilesIndex < 0) return `profiles:\n${nextBlock}\n${content.trimEnd()}`;
  const agentsIndex = content.search(/^agents:\s*$/m);
  if (agentsIndex >= 0) {
    return `${content.slice(0, agentsIndex).trimEnd()}\n\n${nextBlock}\n${content.slice(agentsIndex)}`;
  }
  return `${content.trimEnd()}\n\n${nextBlock}`;
}

function upsertAgentYaml(content: string, originalId: string | null, form: AgentFormState) {
  const nextBlock = `${buildAgentYaml(form)}\n`;
  if (originalId) {
    const itemStart = content.search(new RegExp(`^\\s*- id: ${originalId}\\s*$`, 'm'));
    if (itemStart >= 0) {
      const nextItemRelative = content.slice(itemStart + 1).search(/^\s*- id: \S+\s*$/m);
      const itemEnd = nextItemRelative >= 0 ? itemStart + 1 + nextItemRelative : content.length;
      return `${content.slice(0, itemStart)}${nextBlock}${content.slice(itemEnd)}`;
    }
  }

  const agentsIndex = content.search(/^agents:\s*$/m);
  if (agentsIndex < 0) return `${content.trimEnd()}\nagents:\n${nextBlock}`;
  return `${content.trimEnd()}\n\n${nextBlock}`;
}

function WorkflowLine({ items }: { items: string[] }) {
  if (!items.length) {
    return <span className="text-secondary-text">暂无流程</span>;
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {items.map((item, index) => (
        <span key={`${item}-${index}`} className="flex items-center gap-2">
          <Badge variant="info">{item}</Badge>
          {index < items.length - 1 ? <span className="text-secondary-text">→</span> : null}
        </span>
      ))}
    </div>
  );
}

function RuntimeCard({ overview }: { overview: AgentManagementOverview }) {
  const { runtime, summary } = overview;
  return (
    <Card variant="gradient" padding="lg">
      <div className="grid gap-4 md:grid-cols-4">
        <div>
          <span className="label-uppercase">当前架构</span>
          <div className="mt-2 flex items-center gap-2">
            <p className="text-2xl font-semibold text-foreground">{runtime.agent_arch}</p>
            <Badge variant={runtime.agent_available ? 'success' : 'warning'}>{runtime.agent_available ? '可用' : '待配置'}</Badge>
          </div>
          <p className="mt-2 text-sm text-secondary-text">当前后端 Agent 运行配置；问股入口按该配置创建执行器。</p>
        </div>
        <div>
          <span className="label-uppercase">编排模式</span>
          <p className="mt-2 text-2xl font-semibold text-foreground">{runtime.orchestrator_mode}</p>
          <p className="mt-2 text-sm text-secondary-text">最大步骤：{runtime.max_steps}</p>
        </div>
        <div>
          <span className="label-uppercase">默认模型</span>
          <p className="mt-2 break-all text-lg font-semibold text-foreground">{runtime.effective_model || '未配置'}</p>
          <p className="mt-2 text-sm text-secondary-text">Catalog / Profiles 用于管理配置与 profile_id 映射。</p>
        </div>
        <div>
          <span className="label-uppercase">资产规模</span>
          <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
            <span className="rounded-xl bg-elevated/70 px-3 py-2">{summary.profile_count} Profiles</span>
            <span className="rounded-xl bg-elevated/70 px-3 py-2">{summary.agent_count} Agents</span>
            <span className="rounded-xl bg-elevated/70 px-3 py-2">{summary.tool_count} Tools</span>
            <span className="rounded-xl bg-elevated/70 px-3 py-2">{summary.skill_count} Skills</span>
          </div>
        </div>
      </div>
    </Card>
  );
}

function CatalogEditor({ value, sourcePath, busy, message, onChange, onReload, onSave }: {
  value: string;
  sourcePath: string;
  busy: boolean;
  message: string;
  onChange: (value: string) => void;
  onReload: () => void;
  onSave: () => void;
}) {
  return (
    <Card title="配置源编辑" subtitle={sourcePath} padding="lg">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-secondary-text">当前以 YAML 作为配置真源。结构化控件会同步改写下方 YAML，保存后立即刷新 overview。</p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onReload} disabled={busy}>重载</Button>
          <Button onClick={onSave} disabled={busy}>保存配置</Button>
        </div>
      </div>
      {message ? <p className="mt-3 rounded-xl border border-border/60 bg-elevated/60 px-3 py-2 text-sm text-secondary-text">{message}</p> : null}
      <Textarea
        className="mt-4 min-h-[360px] font-mono text-xs"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        spellCheck={false}
      />
    </Card>
  );
}

function ProfilesTab({
  profiles,
  agents,
  onApplyProfile,
}: {
  profiles: AgentManagementProfile[];
  agents: AgentManagementAgent[];
  onApplyProfile: (originalId: string | null, form: ProfileFormState) => void;
}) {
  const [selectedId, setSelectedId] = useState(profiles[0]?.id ?? '');
  const [editingNew, setEditingNew] = useState(false);
  const selectedProfile = profiles.find((profile) => profile.id === selectedId) ?? profiles[0];
  const [form, setForm] = useState<ProfileFormState>(() => toProfileForm(selectedProfile));

  const updateForm = (field: keyof ProfileFormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const updateWorkflow = (workflow: string[]) => {
    setForm((prev) => ({ ...prev, workflow }));
  };

  const startNewProfile = () => {
    setEditingNew(true);
    setSelectedId('');
    setForm({
      id: '',
      name: '',
      asset_type: 'stock',
      status: 'planned',
      mode: '',
      workflow: [],
      description: '',
    });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_220px]">
      <div className="space-y-4">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
          <Select
            label="选择 Profile"
            value={selectedId}
            placeholder="请选择 Profile"
            options={profiles.map((profile) => ({ value: profile.id, label: `${profile.name} (${profile.id})` }))}
            onChange={(value) => {
              const nextProfile = profiles.find((profile) => profile.id === value) ?? profiles[0];
              setEditingNew(false);
              setSelectedId(value);
              setForm(toProfileForm(nextProfile));
            }}
          />
          <div className="flex items-end">
            <Button variant="secondary" onClick={startNewProfile}>新增 Profile</Button>
          </div>
        </div>

        <Card title={editingNew ? '新增 Profile 配置' : `${form.name || form.id} 配置`} subtitle="workflow 从专业 Agent 清单中选择节点，应用到 YAML 后保存生效" padding="lg">
          <div className="grid gap-4 md:grid-cols-2">
            <Input label="id" value={form.id} onChange={(event) => updateForm('id', event.target.value)} placeholder="stock_quick" />
            <Input label="name" value={form.name} onChange={(event) => updateForm('name', event.target.value)} placeholder="个股技术分析" />
            <Select
              label="asset_type"
              value={form.asset_type}
              options={[
                { value: 'stock', label: 'stock' },
                { value: 'fund', label: 'fund' },
                { value: 'market', label: 'market' },
                { value: 'portfolio', label: 'portfolio' },
              ]}
              onChange={(value) => updateForm('asset_type', value)}
            />
            <Select
              label="status"
              value={form.status}
              options={[
                { value: 'available', label: 'available' },
                { value: 'planned', label: 'planned' },
              ]}
              onChange={(value) => updateForm('status', value)}
            />
            <Input label="mode" value={form.mode} onChange={(event) => updateForm('mode', event.target.value)} placeholder="quick / standard / full" />
          </div>
          <Textarea
            className="mt-4 min-h-[90px]"
            label="description"
            value={form.description}
            onChange={(event) => updateForm('description', event.target.value)}
          />
          <MultiSelectList
            title="workflow"
            items={agents.map((agent) => ({ id: agent.id, name: agent.display_name, description: agent.description }))}
            selected={form.workflow}
            onChange={updateWorkflow}
          />
          <div className="mt-4">
            <span className="label-uppercase">当前顺序</span>
            <div className="mt-2"><WorkflowLine items={form.workflow} /></div>
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={() => onApplyProfile(editingNew ? null : selectedProfile?.id ?? null, form)}>应用到 YAML</Button>
          </div>
        </Card>
      </div>

      <Card title="已有 Profile" subtitle={`${profiles.length} 个`} padding="lg">
        <div className="space-y-2">
          {profiles.map((profile) => (
            <button
              key={profile.id}
              type="button"
              className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${selectedId === profile.id && !editingNew ? 'border-primary bg-primary/10 text-foreground' : 'border-border/60 bg-elevated/45 text-secondary-text hover:text-foreground'}`}
              onClick={() => {
                setEditingNew(false);
                setSelectedId(profile.id);
                setForm(toProfileForm(profile));
              }}
            >
              <span className="block font-medium">{profile.name}</span>
              <span className="text-xs text-muted-text">{profile.id}</span>
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

function MultiSelectList({
  title,
  items,
  selected,
  onChange,
}: {
  title: string;
  items: Array<{ id: string; name: string; description?: string; category?: string }>;
  selected: string[];
  onChange: (selected: string[]) => void;
}) {
  const [draft, setDraft] = useState('');
  const selectedSet = new Set(selected);
  const selectedItems = selected.map((id) => items.find((item) => item.id === id) ?? { id, name: id });
  const availableItems = items.filter((item) => !selectedSet.has(item.id));
  const addDraft = () => {
    if (!draft || selectedSet.has(draft)) return;
    onChange([...selected, draft]);
    setDraft('');
  };
  const remove = (id: string) => {
    onChange(selected.filter((item) => item !== id));
  };

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="label-uppercase">{title}</span>
        <span className="text-xs text-muted-text">已选 {selected.length} / {items.length}</span>
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
        <Select
          value={draft}
          placeholder={`选择 ${title}`}
          options={availableItems.map((item) => ({ value: item.id, label: `${item.name} (${item.id})` }))}
          onChange={setDraft}
        />
        <Button variant="secondary" onClick={addDraft} disabled={!draft}>添加</Button>
      </div>
      <div className="mt-3 flex min-h-10 flex-wrap gap-2 rounded-2xl border border-border/60 bg-elevated/35 p-3">
        {selectedItems.length ? selectedItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-left text-xs text-foreground transition hover:border-danger/50 hover:text-danger"
            onClick={() => remove(item.id)}
            title="点击移除"
          >
            {item.name} ({item.id}) ×
          </button>
        )) : <span className="text-sm text-secondary-text">暂无已选 {title}</span>}
      </div>
    </div>
  );
}

function AgentsTab({
  agents,
  tools,
  skills,
  onApplyAgent,
}: {
  agents: AgentManagementAgent[];
  tools: AgentManagementTool[];
  skills: AgentManagementSkill[];
  onApplyAgent: (originalId: string | null, form: AgentFormState) => void;
}) {
  const [selectedId, setSelectedId] = useState(agents[0]?.id ?? '');
  const [editingNew, setEditingNew] = useState(false);
  const selectedAgent = agents.find((agent) => agent.id === selectedId) ?? agents[0];
  const [form, setForm] = useState<AgentFormState>(() => toAgentForm(selectedAgent));

  const updateForm = (field: keyof AgentFormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const updateListForm = (field: 'tools' | 'skills', value: string[]) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const startNewAgent = () => {
    setEditingNew(true);
    setSelectedId('');
    setForm({
      id: '',
      name: '',
      display_name: '',
      description: '',
      type: 'llm_agent',
      max_steps: '4',
      tools: [],
      skills_routing: 'manual',
      skills: [],
      prompt_system: '',
    });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_220px]">
      <div className="space-y-4">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
          <Select
            label="选择 Agent"
            value={selectedId}
            placeholder="请选择 Agent"
            options={agents.map((agent) => ({ value: agent.id, label: `${agent.display_name} (${agent.id})` }))}
            onChange={(value) => {
              const nextAgent = agents.find((agent) => agent.id === value) ?? agents[0];
              setEditingNew(false);
              setSelectedId(value);
              setForm(toAgentForm(nextAgent));
            }}
          />
          <div className="flex items-end">
            <Button variant="secondary" onClick={startNewAgent}>新增 Agent</Button>
          </div>
        </div>

        <Card title={editingNew ? '新增 Agent 配置' : `${form.display_name || form.id} 配置`} subtitle="应用到 YAML 后，点击页面底部保存配置生效" padding="lg">
          <div className="grid gap-4 md:grid-cols-2">
            <Input label="id" value={form.id} onChange={(event) => updateForm('id', event.target.value)} placeholder="intel" />
            <Input label="name" value={form.name} onChange={(event) => updateForm('name', event.target.value)} placeholder="IntelAgent" />
            <Input label="display_name" value={form.display_name} onChange={(event) => updateForm('display_name', event.target.value)} placeholder="情报分析 Agent" />
            <Input label="type" value={form.type} onChange={(event) => updateForm('type', event.target.value)} placeholder="llm_agent" />
            <Input label="max_steps" value={form.max_steps} onChange={(event) => updateForm('max_steps', event.target.value)} placeholder="4 或留空表示 null" />
            <Select
              label="skills.routing"
              value={form.skills_routing}
              options={[
                { value: 'auto', label: 'auto' },
                { value: 'manual', label: 'manual' },
              ]}
              onChange={(value) => updateForm('skills_routing', value)}
            />
          </div>
          <Textarea
            className="mt-4 min-h-[90px]"
            label="description"
            value={form.description}
            onChange={(event) => updateForm('description', event.target.value)}
          />
          <MultiSelectList
            title="tools"
            items={tools.map((tool) => ({ id: tool.id, name: tool.name, description: tool.description, category: tool.category }))}
            selected={form.tools}
            onChange={(next) => updateListForm('tools', next)}
          />
          <MultiSelectList
            title="skills"
            items={skills.map((skill) => ({ id: skill.id, name: skill.name, description: skill.description, category: skill.category }))}
            selected={form.skills}
            onChange={(next) => updateListForm('skills', next)}
          />
          <Textarea
            className="mt-4 min-h-[180px] font-mono text-xs"
            label="prompt.system"
            value={form.prompt_system}
            onChange={(event) => updateForm('prompt_system', event.target.value)}
          />
          <div className="mt-4 flex justify-end">
            <Button onClick={() => onApplyAgent(editingNew ? null : selectedAgent?.id ?? null, form)}>应用到 YAML</Button>
          </div>
        </Card>
      </div>

      <Card title="已有 Agent" subtitle={`${agents.length} 个`} padding="lg">
        <div className="space-y-2">
          {agents.map((agent) => (
            <button
              key={agent.id}
              type="button"
              className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${selectedId === agent.id && !editingNew ? 'border-primary bg-primary/10 text-foreground' : 'border-border/60 bg-elevated/45 text-secondary-text hover:text-foreground'}`}
              onClick={() => {
                setEditingNew(false);
                setSelectedId(agent.id);
                setForm(toAgentForm(agent));
              }}
            >
              <span className="block font-medium">{agent.display_name}</span>
              <span className="text-xs text-muted-text">{agent.id}</span>
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

function ToolsTab({ tools }: { tools: AgentManagementTool[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {tools.map((tool) => (
        <Card key={tool.id} padding="lg">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">{tool.name}</h3>
              <p className="mt-1 text-sm text-secondary-text">{tool.description}</p>
            </div>
            <Badge>{labelFor(tool.category, categoryLabels)}</Badge>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {tool.parameters.map((parameter) => (
              <Badge key={parameter.name} variant={parameter.required ? 'warning' : 'history'}>{parameter.name}: {parameter.type}</Badge>
            ))}
          </div>
          <p className="mt-4 text-xs text-muted-text">点击编辑请在下方 YAML 中调整引用关系；runtime tool 函数仍由后端注册表提供。</p>
        </Card>
      ))}
    </div>
  );
}

function SkillEditorModal({
  editor,
  busy,
  onChange,
  onClose,
  onSave,
}: {
  editor: SkillEditorState;
  busy: boolean;
  onChange: (content: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-3 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
      <Card className="max-h-[92vh] w-full max-w-5xl overflow-y-auto" padding="lg">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <span className="label-uppercase">编辑 Skill</span>
            <h3 className="mt-2 text-xl font-semibold text-foreground">{editor.skill.name}</h3>
            <p className="mt-1 break-all text-xs text-muted-text">{editor.sourcePath}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose} disabled={busy}>取消</Button>
            <Button onClick={onSave} disabled={busy}>保存 Skill</Button>
          </div>
        </div>
        <Textarea
          className="mt-4 min-h-[560px] font-mono text-xs"
          value={editor.content}
          onChange={(event) => onChange(event.target.value)}
          spellCheck={false}
        />
      </Card>
    </div>
  );
}

function SkillsTab({
  skills,
  editor,
  busy,
  onEditSkill,
  onChangeSkillContent,
  onCloseEditor,
  onSaveSkill,
}: {
  skills: AgentManagementSkill[];
  editor: SkillEditorState | null;
  busy: boolean;
  onEditSkill: (skill: AgentManagementSkill) => void;
  onChangeSkillContent: (content: string) => void;
  onCloseEditor: () => void;
  onSaveSkill: () => void;
}) {
  return (
    <>
      <div className="grid gap-3 md:grid-cols-2">
        {skills.map((skill) => (
          <Card key={skill.id} padding="lg">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-foreground">{skill.name}</h3>
                <p className="mt-1 text-sm text-secondary-text">{skill.description || '暂无说明'}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge>{labelFor(skill.category, categoryLabels)}</Badge>
                <Button variant="secondary" onClick={() => onEditSkill(skill)} disabled={busy}>编辑</Button>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {skill.default_active ? <Badge variant="success">默认激活</Badge> : null}
              {skill.default_router ? <Badge variant="info">自动路由</Badge> : null}
              {skill.user_invocable ? <Badge>用户可选</Badge> : null}
            </div>
            <p className="mt-4 break-all text-xs text-muted-text">Skill 内容来自 {skill.source_path || skill.source}，可通过右上角编辑按钮改写定义文件。</p>
          </Card>
        ))}
      </div>
      {editor ? (
        <SkillEditorModal
          editor={editor}
          busy={busy}
          onChange={onChangeSkillContent}
          onClose={onCloseEditor}
          onSave={onSaveSkill}
        />
      ) : null}
    </>
  );
}

const AgentManagementPage: React.FC = () => {
  const [overview, setOverview] = useState<AgentManagementOverview | null>(null);
  const [catalogText, setCatalogText] = useState('');
  const [catalogPath, setCatalogPath] = useState('');
  const [activeTab, setActiveTab] = useState<TabKey>('profiles');
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [skillEditor, setSkillEditor] = useState<SkillEditorState | null>(null);
  const [message, setMessage] = useState('');

  const activeTabMeta = useMemo(() => tabs.find((tab) => tab.key === activeTab) ?? tabs[0], [activeTab]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [overviewData, catalogData] = await Promise.all([
        agentManagementApi.getOverview(),
        agentManagementApi.getCatalog(),
      ]);
      setOverview(overviewData);
      setCatalogText(catalogData.content);
      setCatalogPath(catalogData.source_path);
      setError(null);
      setMessage('配置已加载');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const saveCatalog = async () => {
    setSaving(true);
    try {
      const result = await agentManagementApi.saveCatalog(catalogText);
      setOverview(result.overview);
      setMessage('配置已保存并刷新');
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const applyProfileConfig = (originalId: string | null, form: ProfileFormState) => {
    if (!form.id.trim() || !form.name.trim()) {
      setMessage('Profile 的 id、name 必填');
      return;
    }
    setCatalogText((prev) => upsertProfileYaml(prev, originalId, form));
    setMessage(`${form.name} 已应用到 YAML，保存后生效`);
  };

  const applyAgentConfig = (originalId: string | null, form: AgentFormState) => {
    if (!form.id.trim() || !form.name.trim() || !form.display_name.trim()) {
      setMessage('Agent 的 id、name、display_name 必填');
      return;
    }
    setCatalogText((prev) => upsertAgentYaml(prev, originalId, form));
    setMessage(`${form.display_name} 已应用到 YAML，保存后生效`);
  };

  const openSkillEditor = async (skill: AgentManagementSkill) => {
    setSaving(true);
    try {
      const data: AgentSkillTextResponse = await agentManagementApi.getSkill(skill.id);
      setSkillEditor({ skill, content: data.content, sourcePath: data.source_path });
      setMessage(`${skill.name} 已加载，可编辑后保存`);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const saveSkill = async () => {
    if (!skillEditor) return;
    setSaving(true);
    try {
      const result = await agentManagementApi.saveSkill(skillEditor.skill.id, skillEditor.content);
      setOverview(result.overview);
      setSkillEditor(null);
      setMessage(`${skillEditor.skill.name} 已保存并刷新`);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <AppPage className="space-y-5">
        <PageHeader eyebrow="Agent Platform" title="Agent 管理" description="正在读取当前 Agent runtime、catalog、skills 与 tools。" />
        <Card><p className="text-sm text-secondary-text">加载中...</p></Card>
      </AppPage>
    );
  }

  if (!overview) {
    return (
      <AppPage className="space-y-5">
        <PageHeader eyebrow="Agent Platform" title="Agent 管理" description="统一管理 Profiles、专业 Agent、Tools 和 Skills。" />
        {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}
        <EmptyState title="暂无 Agent 配置数据" description="后端尚未返回可展示的 Agent 管理信息。" />
      </AppPage>
    );
  }

  return (
    <AppPage className="space-y-5">
      <PageHeader
        eyebrow="Agent Platform"
        title="Agent 管理"
        description="按 Profiles、专业 Agent、Tools、Skills 四个页签管理轻量 Agent Platform 配置。"
      />

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}

      <Card padding="sm">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-secondary-text">
          <span>配置源：{overview.catalog.source_path}</span>
          <Badge variant="info">Catalog v{overview.catalog.version}</Badge>
        </div>
      </Card>

      <RuntimeCard overview={overview} />

      <Card padding="sm">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`rounded-xl px-4 py-2 text-sm font-medium transition ${activeTab === tab.key ? 'bg-primary text-white shadow-sm' : 'bg-elevated text-secondary-text hover:text-foreground'}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </Card>

      <Card title={activeTabMeta.label} subtitle={activeTabMeta.description} padding="lg">
        {activeTab === 'profiles' ? <ProfilesTab profiles={overview.profiles} agents={overview.agents} onApplyProfile={applyProfileConfig} /> : null}
        {activeTab === 'agents' ? <AgentsTab agents={overview.agents} tools={overview.tools} skills={overview.skills} onApplyAgent={applyAgentConfig} /> : null}
        {activeTab === 'tools' ? <ToolsTab tools={overview.tools} /> : null}
        {activeTab === 'skills' ? (
          <SkillsTab
            skills={overview.skills}
            editor={skillEditor}
            busy={saving || loading}
            onEditSkill={openSkillEditor}
            onChangeSkillContent={(content) => setSkillEditor((prev) => (prev ? { ...prev, content } : prev))}
            onCloseEditor={() => setSkillEditor(null)}
            onSaveSkill={saveSkill}
          />
        ) : null}
      </Card>

      <CatalogEditor
        value={catalogText}
        sourcePath={catalogPath}
        busy={saving || loading}
        message={message}
        onChange={setCatalogText}
        onReload={loadData}
        onSave={saveCatalog}
      />
    </AppPage>
  );
};

export default AgentManagementPage;
