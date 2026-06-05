import apiClient from './index';

export type AgentManagementRuntime = {
  agent_mode: boolean;
  agent_mode_explicit: boolean;
  agent_available: boolean;
  agent_arch: string;
  orchestrator_mode: string;
  max_steps: number;
  skill_routing: string;
  configured_skills: string[];
  skill_dir: string | null;
  effective_model: string;
  chat_entrypoint: string;
  analysis_entrypoint: string;
};

export type AgentManagementProfile = {
  id: string;
  name: string;
  asset_type: string;
  status: 'available' | 'planned';
  mode: string;
  workflow: string[];
  description: string;
};

export type AgentManagementAgent = {
  id: string;
  name: string;
  display_name: string;
  description: string;
  type: string;
  max_steps: number | null;
  tools: string[];
  skills: Record<string, unknown>;
  prompt: Record<string, string>;
  model: string;
};

export type AgentManagementSkill = {
  id: string;
  name: string;
  description: string;
  category: string;
  source: string;
  source_path: string;
  default_active: boolean;
  default_router: boolean;
  user_invocable: boolean;
  required_tools: string[];
  allowed_tools: string[];
};

export type AgentManagementTool = {
  id: string;
  name: string;
  description: string;
  category: string;
  parameters: Array<{
    name: string;
    type: string;
    description: string;
    required: boolean;
  }>;
};

export type AgentManagementSummary = {
  profile_count: number;
  agent_count: number;
  skill_count: number;
  tool_count: number;
  skill_category_counts: Record<string, number>;
  tool_category_counts: Record<string, number>;
};

export type AgentManagementOverview = {
  runtime: AgentManagementRuntime;
  profiles: AgentManagementProfile[];
  agents: AgentManagementAgent[];
  skills: AgentManagementSkill[];
  tools: AgentManagementTool[];
  catalog: {
    version: number;
    source_path: string;
  };
  summary: AgentManagementSummary;
};

export type AgentCatalogTextResponse = {
  content: string;
  source_path: string;
};

export type AgentCatalogUpdateResponse = {
  success: boolean;
  message: string;
  overview: AgentManagementOverview;
};

export type AgentSkillTextResponse = {
  id: string;
  content: string;
  source_path: string;
};

export type AgentSkillUpdateResponse = {
  success: boolean;
  message: string;
  overview: AgentManagementOverview;
};

export const agentManagementApi = {
  getOverview: async (): Promise<AgentManagementOverview> => {
    const response = await apiClient.get<AgentManagementOverview>('/api/v1/agent-management/overview');
    return response.data;
  },
  getCatalog: async (): Promise<AgentCatalogTextResponse> => {
    const response = await apiClient.get<AgentCatalogTextResponse>('/api/v1/agent-management/catalog');
    return response.data;
  },
  validateCatalog: async (content: string): Promise<void> => {
    await apiClient.post('/api/v1/agent-management/catalog/validate', { content });
  },
  saveCatalog: async (content: string): Promise<AgentCatalogUpdateResponse> => {
    const response = await apiClient.put<AgentCatalogUpdateResponse>('/api/v1/agent-management/catalog', { content });
    return response.data;
  },
  getSkill: async (skillId: string): Promise<AgentSkillTextResponse> => {
    const response = await apiClient.get<AgentSkillTextResponse>(`/api/v1/agent-management/skills/${encodeURIComponent(skillId)}`);
    return response.data;
  },
  saveSkill: async (skillId: string, content: string): Promise<AgentSkillUpdateResponse> => {
    const response = await apiClient.put<AgentSkillUpdateResponse>(`/api/v1/agent-management/skills/${encodeURIComponent(skillId)}`, { content });
    return response.data;
  },
};
